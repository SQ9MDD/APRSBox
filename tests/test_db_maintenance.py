import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db, log_event, prune_event_logs, vacuum_database


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


if __name__ == "__main__":
    unittest.main()
