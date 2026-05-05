import unittest
from unittest.mock import patch

from app.services.traffic import KISS_FEND, _TrafficModemRuntime


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
        self.assertEqual(log_event_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
