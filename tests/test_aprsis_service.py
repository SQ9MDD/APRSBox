import contextlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import execute, fetch_one, init_db, utc_now
from app.services.aprsis import (
    APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY,
    APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX,
    APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY,
    APRSIS_STRICT_REASON_OTHER,
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


if __name__ == "__main__":
    unittest.main()
