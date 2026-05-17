import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import (
    database_maintenance_snapshot,
    connect,
    init_db,
    log_event,
    reset_runtime_operational_data,
    utc_now,
    prune_event_logs,
    vacuum_database,
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


class DatabaseMaintenanceTests(unittest.TestCase):
    def test_prune_event_logs_keeps_only_newest_rows(self) -> None:
        with temporary_database():
            for index in range(6):
                log_event("INFO", "test", f"message-{index}")

            deleted = prune_event_logs(keep_rows=2)
            self.assertEqual(deleted, 4)

            connection = connect()
            try:
                rows = connection.execute(
                    "SELECT message FROM event_logs ORDER BY created_at DESC, id DESC"
                ).fetchall()
            finally:
                connection.close()

            self.assertEqual([row["message"] for row in rows], ["message-5", "message-4"])

    def test_vacuum_database_runs_on_initialized_database(self) -> None:
        with temporary_database() as database_path:
            for index in range(3):
                log_event("INFO", "test", f"message-{index}")

            before_size = database_path.stat().st_size
            vacuum_database()
            after_size = database_path.stat().st_size

            self.assertGreater(before_size, 0)
            self.assertGreater(after_size, 0)

    def test_database_maintenance_snapshot_tracks_runtime_tables(self) -> None:
        with temporary_database():
            now = utc_now()
            connection = connect()
            try:
                connection.execute(
                    """
                    INSERT INTO traffic_frames(source, interface_id, direction, band, format, line, port, command, length, hex, created_at)
                    VALUES (?, NULL, ?, ?, ?, ?, '', '', ?, '', ?)
                    """,
                    ("TESTSRC", "RX", "2m", "TNC2", "TESTSRC>APRS:>snapshot", 22, now),
                )
                connection.commit()
            finally:
                connection.close()

            log_event("INFO", "test", "snapshot-message")

            snapshot = database_maintenance_snapshot(tracked_tables=("event_logs", "traffic_frames"))
            self.assertTrue(snapshot.get("database_exists"))
            self.assertGreater(int(snapshot.get("page_size") or 0), 0)
            self.assertGreater(int(snapshot.get("page_count") or 0), 0)
            self.assertIn("event_logs", snapshot.get("tracked_row_counts") or {})
            self.assertIn("traffic_frames", snapshot.get("tracked_row_counts") or {})
            self.assertEqual(1, int((snapshot.get("tracked_row_counts") or {}).get("event_logs") or 0))
            self.assertEqual(1, int((snapshot.get("tracked_row_counts") or {}).get("traffic_frames") or 0))

    def test_runtime_reset_clears_operational_tables_without_touching_configuration(self) -> None:
        with temporary_database():
            now = utc_now()
            connection = connect()
            try:
                connection.execute(
                    """
                    INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, NULL, 0, '', ?, ?)
                    """,
                    ("Config modem", "TCP", "2m", "127.0.0.1:8001", now, now),
                )
                connection.execute(
                    """
                    INSERT INTO traffic_frames(source, interface_id, direction, band, format, line, port, command, length, hex, created_at)
                    VALUES (?, NULL, ?, ?, ?, ?, '', '', ?, '', ?)
                    """,
                    ("TESTSRC", "RX", "2m", "TNC2", "TESTSRC>APRS:>reset", 19, now),
                )
                connection.commit()
            finally:
                connection.close()

            log_event("INFO", "test", "reset-message")

            deleted = reset_runtime_operational_data(table_names=("event_logs", "traffic_frames"))
            self.assertEqual(1, int(deleted.get("event_logs") or 0))
            self.assertEqual(1, int(deleted.get("traffic_frames") or 0))

            connection = connect()
            try:
                event_logs_total = connection.execute("SELECT COUNT(*) AS total FROM event_logs").fetchone()["total"]
                traffic_frames_total = connection.execute("SELECT COUNT(*) AS total FROM traffic_frames").fetchone()["total"]
                modems_total = connection.execute("SELECT COUNT(*) AS total FROM modems").fetchone()["total"]
            finally:
                connection.close()

            self.assertEqual(0, event_logs_total)
            self.assertEqual(0, traffic_frames_total)
            self.assertEqual(1, modems_total)


if __name__ == "__main__":
    unittest.main()
