import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, init_db
from app.services.content import recent_event_logs


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


class LogsFilteringTests(unittest.TestCase):
    def test_main_logs_hide_radio_runtime_categories(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO event_logs(level, category, message, created_at)
                VALUES ('INFO', 'digi_flow_runtime', 'Enqueued DIGI Flow frame abc', '2026-04-15T10:00:00+00:00')
                """
            )
            execute(
                """
                INSERT INTO event_logs(level, category, message, created_at)
                VALUES ('WARNING', 'digi_flow_runtime', 'Failed to process DIGI Flow frame abc', '2026-04-15T10:01:00+00:00')
                """
            )
            execute(
                """
                INSERT INTO event_logs(level, category, message, created_at)
                VALUES ('INFO', 'outbound', 'Sent object outbound job #15 via TNC-1', '2026-04-15T10:01:30+00:00')
                """
            )
            execute(
                """
                INSERT INTO event_logs(level, category, message, created_at)
                VALUES ('WARNING', 'auth', 'Failed login attempt for test from 127.0.0.1', '2026-04-15T10:02:00+00:00')
                """
            )

            rows = recent_event_logs(limit=20)
            categories_and_levels = {(str(row["category"]), str(row["level"])) for row in rows}
            messages = [str(row["message"]) for row in rows]

            self.assertIn(("auth", "WARNING"), categories_and_levels)
            self.assertFalse(any("Enqueued DIGI Flow frame" in message for message in messages))
            self.assertFalse(any(category == "digi_flow_runtime" for category, _level in categories_and_levels))
            self.assertFalse(any(category == "outbound" for category, _level in categories_and_levels))


if __name__ == "__main__":
    unittest.main()
