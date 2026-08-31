import contextlib
import asyncio
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import execute, fetch_one, init_db, utc_now
from app.services.aprsis import (
    APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY,
    APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX,
    APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY,
    APRSIS_STRICT_REASON_OTHER,
    AprsisClientService,
    get_aprsis_diagnostics,
    persist_aprsis_runtime_status,
    record_aprsis_strict_reject,
    record_aprsis_tx_result,
)


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


def insert_tx_aprsis_flow(*, name: str, enabled: int = 1) -> int:
    now = utc_now()
    execute(
        """
        INSERT INTO digi_flows (
            name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at
        )
        VALUES (?, '', 'receiver_rf', ?, 'tx_aprsis', 'aprsis', ?, ?, ?)
        """,
        (name, f"RF-{name}", int(enabled), now, now),
    )
    row = fetch_one("SELECT id FROM digi_flows WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


class AprsisDiagnosticsTests(unittest.TestCase):
    def test_get_aprsis_diagnostics_returns_zeroed_payload_without_events(self) -> None:
        with temporary_database():
            diagnostics = get_aprsis_diagnostics()
            self.assertEqual(diagnostics["active_flow_count"], 0)
            self.assertEqual(diagnostics["active_flow_names"], [])
            self.assertEqual(diagnostics["session_uptime"], "-")
            self.assertEqual(diagnostics["tx"]["sent_total"], 0)
            self.assertEqual(diagnostics["tx"]["drop_total"], 0)
            self.assertEqual(diagnostics["strict_rejects"]["total"], 0)
            self.assertEqual(diagnostics["reconnects"]["total"], 0)
            self.assertEqual(diagnostics["reconnects"]["warning_total"], 0)

    def test_get_aprsis_diagnostics_aggregates_tx_and_strict_guard_stats(self) -> None:
        with temporary_database():
            insert_tx_aprsis_flow(name="APRSIS-1", enabled=1)
            insert_tx_aprsis_flow(name="APRSIS-disabled", enabled=0)
            now_dt = datetime.now(timezone.utc).replace(microsecond=0)
            now = now_dt.isoformat()
            two_hours_ago = (now_dt - timedelta(hours=2)).isoformat()
            thirty_hours_ago = (now_dt - timedelta(hours=30)).isoformat()
            last_sent_line = "SQ9MDD-4>APRS,WIDE1-1:>TX SAMPLE"
            last_blocked_line = "SP8ABC-9>APRS,TCPIP*:>BLOCKED SAMPLE"

            persist_aprsis_runtime_status(
                status="connected",
                status_detail="Connected",
                server="rotate.aprs2.net",
                port=14580,
                login="SQ9MDD-4",
                connected_at=now,
                last_error=None,
            )

            record_aprsis_tx_result(sent=True, frame_line="SQ9MDD-4>APRS,WIDE1-1:>OLD TX", occurred_at=thirty_hours_ago)
            record_aprsis_tx_result(sent=True, frame_line="SQ9MDD-4>APRS,WIDE1-1:>24H TX", occurred_at=two_hours_ago)
            record_aprsis_tx_result(sent=True, frame_line=last_sent_line, occurred_at=now)
            record_aprsis_tx_result(sent=False, frame_line="SQ9MDD-4>APRS:>DROP OLD", occurred_at=thirty_hours_ago)
            record_aprsis_tx_result(sent=False, frame_line="SQ9MDD-4>APRS:>DROP NOW", occurred_at=now)

            record_aprsis_strict_reject(
                reason_key=APRSIS_STRICT_REASON_OTHER,
                frame_line="SP8ABC-9>APRS:>OLD STRICT",
                reason_message="Strict filter rejected frame because old policy scope is blocked.",
                occurred_at=thirty_hours_ago,
            )
            record_aprsis_strict_reject(
                reason_key=APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX,
                frame_line="SP8ABC-9>APRS,TCPXX*:>STRICT TCP",
                reason_message="Strict filter rejected frame because outer path contains blocked token TCPXX.",
                occurred_at=now,
            )
            record_aprsis_strict_reject(
                reason_key=APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY,
                frame_line="SP8ABC-9>APRS,NOGATE*:>STRICT NOGATE",
                reason_message="Strict filter rejected frame because outer path contains blocked token NOGATE.",
                occurred_at=now,
            )
            record_aprsis_strict_reject(
                reason_key=APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY,
                frame_line="SP8ABC-9>APRS:}INVALID THIRD PARTY",
                reason_message="Strict filter rejected frame because third-party encapsulation is malformed or invalid.",
                occurred_at=now,
            )
            record_aprsis_strict_reject(
                reason_key=APRSIS_STRICT_REASON_OTHER,
                frame_line=last_blocked_line,
                reason_message="Strict filter rejected frame because policy scope is blocked.",
                occurred_at=now,
            )

            execute(
                """
                INSERT INTO event_logs(level, category, message, created_at)
                VALUES ('INFO', 'aprsis', 'Connected APRS-IS uplink to rotate.aprs2.net:14580.', ?)
                """,
                (now,),
            )
            execute(
                """
                INSERT INTO event_logs(level, category, message, created_at)
                VALUES ('WARNING', 'aprsis', 'APRS-IS uplink retry scheduled.', ?)
                """,
                (now,),
            )

            diagnostics = get_aprsis_diagnostics()

            self.assertEqual(diagnostics["active_flow_count"], 1)
            self.assertEqual(diagnostics["active_flow_names"], ["APRSIS-1"])
            self.assertNotEqual(diagnostics["session_uptime"], "-")
            self.assertIsNotNone(diagnostics["last_activity_at"])

            self.assertEqual(diagnostics["tx"]["sent_total"], 3)
            self.assertEqual(diagnostics["tx"]["sent_1h"], 1)
            self.assertEqual(diagnostics["tx"]["sent_24h"], 2)
            self.assertEqual(diagnostics["tx"]["drop_total"], 2)
            self.assertEqual(diagnostics["tx"]["drop_1h"], 1)
            self.assertEqual(diagnostics["tx"]["drop_24h"], 1)
            self.assertIsNone(diagnostics["tx"]["last_sent_frame_uid"])
            self.assertIsNone(diagnostics["tx"]["last_drop_frame_uid"])
            self.assertEqual(diagnostics["tx"]["last_sent_frame_line"], last_sent_line)

            self.assertEqual(diagnostics["strict_rejects"]["total"], 5)
            self.assertEqual(diagnostics["strict_rejects"]["last_1h"], 4)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h"], 4)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_blocked_tcpip_tcpxx"], 1)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_blocked_nogate_rfonly"], 1)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_malformed_third_party"], 1)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_other"], 1)
            self.assertIsNone(diagnostics["strict_rejects"]["last_rejected_frame_uid"])
            self.assertEqual(diagnostics["strict_rejects"]["last_rejected_frame_line"], last_blocked_line)
            self.assertEqual(diagnostics["strict_rejects"]["last_rejected_reason"], "Strict filter rejected frame because policy scope is blocked.")

            self.assertEqual(diagnostics["reconnects"]["total"], 1)
            self.assertEqual(diagnostics["reconnects"]["last_24h"], 1)
            self.assertIsNotNone(diagnostics["reconnects"]["last_connected_at"])
            self.assertEqual(diagnostics["reconnects"]["warning_total"], 1)
            self.assertEqual(diagnostics["reconnects"]["warning_24h"], 1)


class AprsisClientRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_line_is_dropped_before_transport_write(self) -> None:
        class RecordingWriter:
            def __init__(self) -> None:
                self.writes: list[bytes] = []

            def is_closing(self) -> bool:
                return False

            def write(self, data: bytes) -> None:
                self.writes.append(data)

            async def drain(self) -> None:
                return None

        with temporary_database():
            service = AprsisClientService()
            writer = RecordingWriter()
            service._writer = writer  # type: ignore[assignment]

            success, detail = await service.send_tnc2_line(
                "SQ9MDD-9>APRS:>Stale packet",
                telemetry={"rx_received_monotonic": time.monotonic() - 6.0},
            )

            self.assertFalse(success)
            self.assertIn("frame is stale", detail)
            self.assertEqual(writer.writes, [])

    async def test_viscous_delay_extends_stale_line_limit_before_transport_write(self) -> None:
        class RecordingWriter:
            def __init__(self) -> None:
                self.writes: list[bytes] = []

            def is_closing(self) -> bool:
                return False

            def write(self, data: bytes) -> None:
                self.writes.append(data)

            async def drain(self) -> None:
                return None

        with temporary_database():
            service = AprsisClientService()
            writer = RecordingWriter()
            service._writer = writer  # type: ignore[assignment]

            success, detail = await service.send_tnc2_line(
                "SQ9MDD-9>APRS:>Viscous-delay packet",
                telemetry={
                    "rx_received_monotonic": time.monotonic() - 6.0,
                    "max_frame_age_seconds": 7.0,
                },
            )

            self.assertTrue(success)
            self.assertEqual(detail, "APRS-IS TX sent.")
            self.assertEqual(len(writer.writes), 1)

    async def test_existing_transport_backlog_is_aborted_without_appending_line(self) -> None:
        class BufferedTransport:
            def __init__(self) -> None:
                self.aborted = False

            def get_write_buffer_size(self) -> int:
                return 128

            def abort(self) -> None:
                self.aborted = True

        class BufferedWriter:
            def __init__(self) -> None:
                self.transport = BufferedTransport()
                self.write_called = False

            def is_closing(self) -> bool:
                return False

            def write(self, _data: bytes) -> None:
                self.write_called = True

        with temporary_database():
            service = AprsisClientService(reconnect_delay=0.1)
            writer = BufferedWriter()
            service._writer = writer  # type: ignore[assignment]
            service._connected_config = ("rotate.aprs2.net", 14580, "SQ9MDD-4", "12345")
            service._connected_since = utc_now()

            success, detail = await service.send_tnc2_line("SQ9MDD-9>APRS:>Do not append")

            self.assertFalse(success)
            self.assertIn("buffered bytes", detail)
            self.assertFalse(writer.write_called)
            self.assertTrue(writer.transport.aborted)
            self.assertIsNone(service._writer)

    async def test_transport_bytes_remaining_after_drain_abort_connection(self) -> None:
        class RetainingTransport:
            def __init__(self) -> None:
                self.pending_bytes = 0
                self.aborted = False

            def get_write_buffer_size(self) -> int:
                return self.pending_bytes

            def abort(self) -> None:
                self.aborted = True

        class RetainingWriter:
            def __init__(self) -> None:
                self.transport = RetainingTransport()

            def is_closing(self) -> bool:
                return False

            def write(self, data: bytes) -> None:
                self.transport.pending_bytes = len(data)

            async def drain(self) -> None:
                return None

        with temporary_database():
            service = AprsisClientService(reconnect_delay=0.1)
            writer = RetainingWriter()
            service._writer = writer  # type: ignore[assignment]
            service._connected_config = ("rotate.aprs2.net", 14580, "SQ9MDD-4", "12345")
            service._connected_since = utc_now()

            success, detail = await service.send_tnc2_line("SQ9MDD-9>APRS:>Retained after drain")

            self.assertFalse(success)
            self.assertIn("transport retained", detail)
            self.assertTrue(writer.transport.aborted)
            self.assertIsNone(service._writer)

    async def test_disconnected_line_is_dropped_and_not_replayed_after_reconnect(self) -> None:
        class RecordingWriter:
            def __init__(self) -> None:
                self.writes: list[bytes] = []

            def is_closing(self) -> bool:
                return False

            def write(self, data: bytes) -> None:
                self.writes.append(data)

            async def drain(self) -> None:
                return None

        with temporary_database():
            service = AprsisClientService()
            dropped_line = "SQ9MDD-9>APRS,WIDE1-1:>Must not be replayed"

            success, detail = await service.send_tnc2_line(dropped_line)

            self.assertFalse(success)
            self.assertEqual(detail, "APRS-IS TX dropped: uplink is not connected.")

            writer = RecordingWriter()
            service._writer = writer  # type: ignore[assignment]
            service._connected_config = ("rotate.aprs2.net", 14580, "SQ9MDD-4", "12345")
            service._connected_since = utc_now()

            # Establishing a later connection must not flush the dropped line.
            await asyncio.sleep(0)
            self.assertEqual(writer.writes, [])

            fresh_line = "SQ9MDD-9>APRS,WIDE1-1:>Fresh packet"
            sent, sent_detail = await service.send_tnc2_line(fresh_line)
            self.assertTrue(sent)
            self.assertEqual(sent_detail, "APRS-IS TX sent.")
            self.assertEqual(writer.writes, [fresh_line.encode("latin-1") + b"\r\n"])

    async def test_closing_transport_drops_line_without_write(self) -> None:
        class ClosingWriter:
            def __init__(self) -> None:
                self.write_called = False

            def is_closing(self) -> bool:
                return True

            def write(self, _data: bytes) -> None:
                self.write_called = True

        with temporary_database():
            service = AprsisClientService()
            writer = ClosingWriter()
            service._writer = writer  # type: ignore[assignment]

            success, detail = await service.send_tnc2_line("SQ9MDD-9>APRS:>Drop closing")

            self.assertFalse(success)
            self.assertEqual(detail, "APRS-IS TX dropped: uplink is not connected.")
            self.assertFalse(writer.write_called)

    async def test_send_tnc2_line_times_out_writer_drain_and_disconnects(self) -> None:
        class HangingWriter:
            def __init__(self) -> None:
                self.closed = False

            def write(self, _data: bytes) -> None:
                return None

            async def drain(self) -> None:
                await asyncio.sleep(10)

            def close(self) -> None:
                self.closed = True

            async def wait_closed(self) -> None:
                return None

        with temporary_database():
            service = AprsisClientService(reconnect_delay=0.1)
            service._writer = HangingWriter()  # type: ignore[assignment]
            service._connected_config = ("rotate.aprs2.net", 14580, "SQ9MDD-4", "12345")
            service._connected_since = utc_now()
            started = time.monotonic()
            success, detail = await service.send_tnc2_line("SQ9MDD-4>APRS,WIDE1-1:>Timeout test")
            elapsed = time.monotonic() - started

            self.assertFalse(success)
            self.assertIn("APRS-IS TX dropped: write failed", detail)
            self.assertLess(elapsed, 1.0)
            self.assertIsNone(service._writer)


if __name__ == "__main__":
    unittest.main()
