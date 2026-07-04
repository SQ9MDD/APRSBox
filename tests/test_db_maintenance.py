import contextlib
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import (
    DATABASE_INDEX_REPAIR_SETTING_KEY,
    DATABASE_INDEX_REPAIR_VERSION,
    database_maintenance_snapshot,
    connect,
    get_app_setting,
    get_traffic_retention_minutes,
    init_db,
    log_event,
    prune_outbound_jobs_batch,
    set_app_setting,
    reset_runtime_operational_data,
    traffic_retention_cutoff,
    utc_now,
    prune_event_logs,
    vacuum_database,
    _is_reindex_repairable_check_messages,
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
    def test_traffic_retention_defaults_to_one_hour(self) -> None:
        with temporary_database(), patch("app.db.datetime", _FixedDatetime):
            self.assertEqual(60, get_traffic_retention_minutes())
            self.assertEqual("2026-01-01T11:00:00+00:00", traffic_retention_cutoff())

    def test_init_db_marks_clean_database_index_repair_version(self) -> None:
        with temporary_database():
            self.assertEqual(DATABASE_INDEX_REPAIR_VERSION, get_app_setting(DATABASE_INDEX_REPAIR_SETTING_KEY))

    def test_reindex_repairable_check_messages_are_index_only(self) -> None:
        self.assertTrue(
            _is_reindex_repairable_check_messages(
                [
                    "wrong # of entries in index idx_event_logs_created_at",
                    "row 521 missing from index idx_traffic_frames_created_at",
                ]
            )
        )
        self.assertFalse(_is_reindex_repairable_check_messages(["database disk image is malformed"]))

    def test_traffic_retention_uses_configured_minutes(self) -> None:
        with temporary_database(), patch("app.db.datetime", _FixedDatetime):
            set_app_setting("traffic_retention_minutes", "180")
            self.assertEqual(180, get_traffic_retention_minutes())
            self.assertEqual("2026-01-01T09:00:00+00:00", traffic_retention_cutoff())

    def test_traffic_retention_accepts_twenty_four_hours(self) -> None:
        with temporary_database(), patch("app.db.datetime", _FixedDatetime):
            set_app_setting("traffic_retention_minutes", "1440")
            self.assertEqual(1440, get_traffic_retention_minutes())
            self.assertEqual("2025-12-31T12:00:00+00:00", traffic_retention_cutoff())

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

    def test_prune_outbound_jobs_batch_keeps_pending_messages_and_recent_rows(self) -> None:
        with temporary_database(), patch("app.db.datetime", _FixedDatetime):
            connection = connect()
            try:
                for day in ("01", "02", "03"):
                    _insert_outbound_job(connection, "beacon", "sent", f"2025-12-{day}T00:00:00+00:00")
                _insert_outbound_job(connection, "beacon", "sent", "2025-12-31T00:00:00+00:00")
                _insert_outbound_job(connection, "beacon", "queued", "2025-12-01T00:00:00+00:00")
                _insert_outbound_job(connection, "wx", "processing", "2025-12-01T00:00:00+00:00")
                _insert_outbound_job(connection, "message", "sent", "2025-12-01T00:00:00+00:00", aprs_message_id=123)
                _insert_outbound_job(connection, "wx", "failed", "2025-11-01T00:00:00+00:00")
                _insert_outbound_job(connection, "wx", "failed", "2025-11-02T00:00:00+00:00")
                _insert_outbound_job(
                    connection,
                    "wx",
                    "failed",
                    "2025-11-01T00:00:00+00:00",
                    updated_at="2025-12-31T00:00:00+00:00",
                )
                connection.commit()
            finally:
                connection.close()

            deleted = prune_outbound_jobs_batch(
                limit=10,
                sent_retention_days=7,
                failure_retention_days=30,
                min_rows_per_group=1,
            )
            self.assertEqual(5, deleted)

            connection = connect()
            try:
                sent_beacons = connection.execute(
                    "SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'beacon' AND status = 'sent'"
                ).fetchone()
                queued_beacons = connection.execute(
                    "SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'beacon' AND status = 'queued'"
                ).fetchone()
                processing_wx = connection.execute(
                    "SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'wx' AND status = 'processing'"
                ).fetchone()
                message_jobs = connection.execute(
                    "SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'message'"
                ).fetchone()
                failed_wx = connection.execute(
                    "SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'wx' AND status = 'failed'"
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(1, int(sent_beacons["total"]))
            self.assertEqual(1, int(queued_beacons["total"]))
            self.assertEqual(1, int(processing_wx["total"]))
            self.assertEqual(1, int(message_jobs["total"]))
            self.assertEqual(1, int(failed_wx["total"]))

    def test_prune_outbound_jobs_batch_keeps_minimum_rows_per_group(self) -> None:
        with temporary_database(), patch("app.db.datetime", _FixedDatetime):
            connection = connect()
            try:
                for day in ("01", "02", "03"):
                    _insert_outbound_job(connection, "object", "sent", f"2025-12-{day}T00:00:00+00:00")
                connection.commit()
            finally:
                connection.close()

            deleted = prune_outbound_jobs_batch(
                limit=10,
                sent_retention_days=7,
                failure_retention_days=30,
                min_rows_per_group=1,
            )
            self.assertEqual(2, deleted)

            connection = connect()
            try:
                remaining = connection.execute(
                    "SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'object' AND status = 'sent'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(1, int(remaining["total"]))


def _insert_outbound_job(
    connection,
    kind: str,
    status: str,
    timestamp: str,
    *,
    updated_at: str | None = None,
    aprs_message_id: int | None = None,
) -> None:
    effective_updated_at = updated_at or timestamp
    sent_at = timestamp if status == "sent" else None
    connection.execute(
        """
        INSERT INTO outbound_jobs(
            kind, interface_id, aprs_message_id, payload_json, status,
            scheduled_at, locked_at, started_at, sent_at, attempt_count,
            last_error, created_at, updated_at
        )
        VALUES (?, NULL, ?, '{}', ?, ?, NULL, NULL, ?, 0, NULL, ?, ?)
        """,
        (kind, aprs_message_id, status, timestamp, sent_at, timestamp, effective_updated_at),
    )


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return cls(2026, 1, 1, 12, 0, 0, tzinfo=tz or timezone.utc)


if __name__ == "__main__":
    unittest.main()
