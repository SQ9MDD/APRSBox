import contextlib
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import connect, get_app_setting, init_db, log_event
from app.services.maintenance_scheduler import LAST_EVENT_LOG_PRUNE_DATE_KEY, MaintenanceSchedulerService


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


class MaintenanceSchedulerTests(unittest.TestCase):
    def test_scheduler_prunes_event_logs_only_once_per_day(self) -> None:
        with temporary_database():
            for index in range(6):
                log_event("INFO", "test", f"message-{index}")

            scheduler = MaintenanceSchedulerService(event_log_keep_rows=2)
            scheduler._tick(now=datetime(2026, 4, 5, 0, 5, tzinfo=timezone.utc))

            connection = connect()
            try:
                rows = connection.execute("SELECT message FROM event_logs ORDER BY created_at DESC, id DESC").fetchall()
            finally:
                connection.close()
            self.assertEqual([row["message"] for row in rows], ["message-5", "message-4"])
            self.assertEqual(get_app_setting(LAST_EVENT_LOG_PRUNE_DATE_KEY), "2026-04-05")

            log_event("INFO", "test", "message-6")
            log_event("INFO", "test", "message-7")
            scheduler._tick(now=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc))

            connection = connect()
            try:
                same_day_total = connection.execute("SELECT COUNT(*) AS total FROM event_logs").fetchone()
            finally:
                connection.close()
            assert same_day_total is not None
            self.assertEqual(int(same_day_total["total"]), 4)

            scheduler._tick(now=datetime(2026, 4, 6, 0, 1, tzinfo=timezone.utc))

            connection = connect()
            try:
                next_day_rows = connection.execute("SELECT message FROM event_logs ORDER BY created_at DESC, id DESC").fetchall()
            finally:
                connection.close()
            self.assertEqual([row["message"] for row in next_day_rows], ["message-7", "message-6"])
            self.assertEqual(get_app_setting(LAST_EVENT_LOG_PRUNE_DATE_KEY), "2026-04-06")

    def test_scheduler_runs_outbound_job_pruning(self) -> None:
        with temporary_database(), patch("app.services.maintenance_scheduler.prune_outbound_jobs_batch") as prune_outbound:
            scheduler = MaintenanceSchedulerService(event_log_keep_rows=2)
            scheduler._tick(now=datetime(2026, 4, 5, 0, 5, tzinfo=timezone.utc))

            prune_outbound.assert_called_once()
            self.assertEqual({"limit": 500}, prune_outbound.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
