import contextlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import init_db, utc_now
from app.services.traffic import KISS_FEND, _TrafficModemRuntime


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


class TrafficKissBufferGuardTests(unittest.TestCase):
    def test_rx_kiss_buffer_clears_oversized_unterminated_frame(self) -> None:
        runtime = _TrafficModemRuntime()
        runtime._consume_kiss_chunk(bytes([KISS_FEND, 0x00]))

        for _ in range(12):
            runtime._consume_kiss_chunk(b"A" * 700)

        self.assertEqual(len(runtime._kiss_buffer), 0)

    def test_proxy_uplink_buffer_clears_oversized_unterminated_frame(self) -> None:
        runtime = _TrafficModemRuntime()
        runtime._consume_proxy_uplink_chunk(bytes([KISS_FEND, 0x00]))

        for _ in range(12):
            runtime._consume_proxy_uplink_chunk(b"B" * 700)

        self.assertEqual(len(runtime._proxy_uplink_buffer), 0)


class TrafficKissRxParserTests(unittest.TestCase):
    def _runtime_with_capture(self) -> tuple[_TrafficModemRuntime, list[dict[str, str]]]:
        runtime = _TrafficModemRuntime()
        persisted: list[dict[str, str]] = []
        decode_map = {
            b"A": "A",
            b"B": "B",
            b"PAYLOAD": "PAYLOAD",
        }
        runtime._decode_ax25_to_tnc2 = lambda payload: decode_map.get(bytes(payload))  # type: ignore[method-assign]
        runtime._persist_frame = lambda entry, _timestamp: persisted.append(dict(entry))  # type: ignore[method-assign]
        return runtime, persisted

    def test_valid_data_frame_yields_single_rx_entry(self) -> None:
        runtime, persisted = self._runtime_with_capture()
        runtime._consume_kiss_chunk(bytes([KISS_FEND, 0x00]) + b"PAYLOAD" + bytes([KISS_FEND]))

        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["format"], "TNC2")
        self.assertEqual(persisted[0]["line"], "PAYLOAD")

    def test_valid_frame_with_trailing_crlf_does_not_create_extra_pseudo_frame(self) -> None:
        runtime, persisted = self._runtime_with_capture()
        runtime._consume_kiss_chunk(bytes([KISS_FEND, 0x00]) + b"PAYLOAD" + bytes([KISS_FEND, 0x0D, 0x0A]))

        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["line"], "PAYLOAD")

    def test_two_frames_with_crlf_between_them_produce_exactly_two_rx_entries(self) -> None:
        runtime, persisted = self._runtime_with_capture()
        stream = bytes([KISS_FEND, 0x00, 0x41, KISS_FEND, 0x0D, 0x0A, KISS_FEND, 0x00, 0x42, KISS_FEND])

        with patch("app.services.traffic.log_event"):
            runtime._consume_kiss_chunk(stream)

        self.assertEqual([entry["line"] for entry in persisted], ["A", "B"])
        stats = runtime.runtime_snapshot()["kiss_stats"]
        self.assertEqual(stats["ignored_kiss_non_data"] + stats["ignored_kiss_garbage"], 1)

    def test_back_to_back_fend_does_not_create_empty_frame_or_drop_data(self) -> None:
        runtime, persisted = self._runtime_with_capture()
        runtime._consume_kiss_chunk(bytes([KISS_FEND, KISS_FEND, 0x00, 0x41, KISS_FEND]))

        self.assertEqual([entry["line"] for entry in persisted], ["A"])

    def test_undecodable_ax25_data_frame_is_persisted_with_diagnostic_reason(self) -> None:
        runtime, persisted = self._runtime_with_capture()
        runtime._consume_kiss_chunk(bytes([KISS_FEND, 0x00, 0x01, 0x02, KISS_FEND]))

        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["format"], "KISS")
        self.assertIn("AX.25 decode failed", persisted[0]["line"])
        self.assertIn("payload too short", persisted[0]["line"])

    def test_welcome_text_before_frame_is_ignored(self) -> None:
        runtime, persisted = self._runtime_with_capture()
        runtime._consume_kiss_chunk(b"ARDUINO-TNC READY\r\n" + bytes([KISS_FEND, 0x00, 0x41, KISS_FEND]))

        self.assertEqual([entry["line"] for entry in persisted], ["A"])

    def test_unsupported_command_frame_is_ignored_without_reconnect(self) -> None:
        runtime, persisted = self._runtime_with_capture()

        with patch("app.services.traffic.log_event") as log_event_mock:
            runtime._consume_kiss_chunk(bytes([KISS_FEND, 0x0D, 0x0A, KISS_FEND]))

        self.assertEqual(persisted, [])
        self.assertEqual(runtime._status, "idle")
        self.assertIsNone(runtime._last_error)
        stats = runtime.runtime_snapshot()["kiss_stats"]
        self.assertEqual(stats["ignored_kiss_non_data"] + stats["ignored_kiss_garbage"], 1)
        self.assertGreaterEqual(log_event_mock.call_count, 1)
        self.assertIn("0D 0A", str(log_event_mock.call_args_list[0]))

    def test_unsupported_command_debug_log_is_rate_limited(self) -> None:
        runtime, persisted = self._runtime_with_capture()
        stream = bytes([KISS_FEND, 0x0D, 0x0A, KISS_FEND, 0x0D, 0x0A, KISS_FEND])

        with patch("app.services.traffic.log_event") as log_event_mock:
            runtime._consume_kiss_chunk(stream)

        self.assertEqual(persisted, [])
        stats = runtime.runtime_snapshot()["kiss_stats"]
        self.assertEqual(stats["ignored_kiss_non_data"] + stats["ignored_kiss_garbage"], 2)
        ignored_logs = [call for call in log_event_mock.call_args_list if "Ignored KISS" in str(call)]
        self.assertEqual(len(ignored_logs), 1)


class TrafficRxHotPathOrderingTests(unittest.TestCase):
    def test_frame_consumer_is_called_before_heavy_side_effects(self) -> None:
        with temporary_database():
            call_order: list[str] = []
            consumer_calls: list[dict[str, object]] = []

            def frame_consumer(line: str, **kwargs: object) -> None:
                call_order.append("consumer")
                consumer_calls.append({"line": line, **kwargs})

            runtime = _TrafficModemRuntime(frame_consumer=frame_consumer)
            timestamp = utc_now()
            entry = {
                "source": "TNC-A",
                "port": "0",
                "command": "0x0",
                "length": "12",
                "hex": "AA BB CC",
                "format": "TNC2",
                "line": "SP8ABC-9>APRS,WIDE1-1:>Hot path test",
                "_rx_monotonic": time.monotonic(),
            }

            with patch("app.services.traffic.record_traffic_device_station_observation", side_effect=lambda **_kwargs: call_order.append("device_stats")), patch(
                "app.services.traffic.process_incoming_frame",
                side_effect=lambda *_args, **_kwargs: call_order.append("band_condition"),
            ), patch(
                "app.services.traffic.process_incoming_tnc2_message",
                side_effect=lambda *_args, **_kwargs: call_order.append("messages"),
            ):
                runtime._persist_frame(entry, timestamp)

            self.assertTrue(call_order)
            self.assertEqual(call_order[0], "consumer")
            self.assertEqual(call_order[1:], ["device_stats", "band_condition", "messages"])
            self.assertEqual(len(consumer_calls), 1)
            self.assertEqual(consumer_calls[0]["line"], entry["line"])
            self.assertEqual(consumer_calls[0]["source_ref"], "TNC")
            self.assertEqual(consumer_calls[0]["rx_received_at"], timestamp)
            self.assertIsInstance(consumer_calls[0]["rx_received_monotonic"], float)


if __name__ == "__main__":
    unittest.main()
