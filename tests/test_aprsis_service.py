import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db, utc_now
from app.services.aprsis import get_aprsis_diagnostics, persist_aprsis_runtime_status


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
            flow_id = insert_tx_aprsis_flow(name="APRSIS-1", enabled=1)
            insert_tx_aprsis_flow(name="APRSIS-disabled", enabled=0)
            now = utc_now()
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

            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'frame_received', 'accepted', ?, ?)
                """,
                ("tx-1", flow_id, f"Frame accepted from receiver_rf:RF-APRSIS-1 | line={last_sent_line}", now),
            )
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'output_action', 'tx', 'APRS-IS TX queued.', ?)
                """,
                ("tx-1", flow_id, now),
            )
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'output_action', 'drop', 'APRS-IS TX dropped.', ?)
                """,
                ("drop-1", flow_id, now),
            )
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'strict_filter', 'rejected', 'Strict filter rejected frame because outer path contains blocked token TCPXX.', ?)
                """,
                ("strict-tcpxx", flow_id, now),
            )
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'strict_filter', 'rejected', 'Strict filter rejected frame because outer path contains blocked token NOGATE.', ?)
                """,
                ("strict-nogate", flow_id, now),
            )
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'strict_filter', 'rejected', 'Strict filter rejected frame because third-party encapsulation is malformed or invalid.', ?)
                """,
                ("strict-malformed", flow_id, now),
            )
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'frame_received', 'accepted', ?, ?)
                """,
                ("strict-other", flow_id, f"Frame accepted from receiver_rf:RF-APRSIS-1 | line={last_blocked_line}", now),
            )
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES (?, ?, NULL, 'strict_filter', 'rejected', 'Strict filter rejected frame because policy scope is blocked.', ?)
                """,
                ("strict-other", flow_id, now),
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

            self.assertEqual(diagnostics["tx"]["sent_total"], 1)
            self.assertEqual(diagnostics["tx"]["sent_1h"], 1)
            self.assertEqual(diagnostics["tx"]["sent_24h"], 1)
            self.assertEqual(diagnostics["tx"]["drop_total"], 1)
            self.assertEqual(diagnostics["tx"]["drop_1h"], 1)
            self.assertEqual(diagnostics["tx"]["drop_24h"], 1)
            self.assertEqual(diagnostics["tx"]["last_sent_frame_uid"], "tx-1")
            self.assertEqual(diagnostics["tx"]["last_drop_frame_uid"], "drop-1")
            self.assertEqual(diagnostics["tx"]["last_sent_frame_line"], last_sent_line)

            self.assertEqual(diagnostics["strict_rejects"]["total"], 4)
            self.assertEqual(diagnostics["strict_rejects"]["last_1h"], 4)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h"], 4)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_blocked_tcpip_tcpxx"], 1)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_blocked_nogate_rfonly"], 1)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_malformed_third_party"], 1)
            self.assertEqual(diagnostics["strict_rejects"]["last_24h_other"], 1)
            self.assertEqual(diagnostics["strict_rejects"]["last_rejected_frame_uid"], "strict-other")
            self.assertEqual(diagnostics["strict_rejects"]["last_rejected_frame_line"], last_blocked_line)
            self.assertEqual(diagnostics["strict_rejects"]["last_rejected_reason"], "Strict filter rejected frame because policy scope is blocked.")

            self.assertEqual(diagnostics["reconnects"]["total"], 1)
            self.assertEqual(diagnostics["reconnects"]["last_24h"], 1)
            self.assertIsNotNone(diagnostics["reconnects"]["last_connected_at"])
            self.assertEqual(diagnostics["reconnects"]["warning_total"], 1)
            self.assertEqual(diagnostics["reconnects"]["warning_24h"], 1)


if __name__ == "__main__":
    unittest.main()
