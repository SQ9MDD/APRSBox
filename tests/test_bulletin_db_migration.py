import contextlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import connect, init_db


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


class BulletinMigrationTests(unittest.TestCase):
    def test_init_db_adds_path_column_to_existing_bulletin_table(self) -> None:
        with temporary_database() as database_path:
            raw = sqlite3.connect(database_path)
            try:
                raw.executescript(
                    """
                    CREATE TABLE bulletins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_kind TEXT NOT NULL DEFAULT 'bulletin' CHECK (message_kind IN ('bulletin', 'announcement', 'group_bulletin')),
                        addressee TEXT,
                        bulletin_code TEXT,
                        group_name TEXT,
                        is_enabled INTEGER NOT NULL DEFAULT 0 CHECK (is_enabled IN (0, 1)),
                        interval_minutes INTEGER NOT NULL DEFAULT 30 CHECK (interval_minutes IN (5, 10, 15, 30, 45, 60)),
                        message_text TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO bulletins(message_kind, addressee, bulletin_code, group_name, is_enabled, interval_minutes, message_text, updated_at)
                    VALUES ('announcement', NULL, 'A', '', 1, 30, 'Test bulletin', '2026-01-01T00:00:00+00:00');
                    """
                )
                raw.commit()
            finally:
                raw.close()

            init_db()

            connection = connect()
            try:
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(bulletins)").fetchall()}
                self.assertIn("path", columns)
                row = connection.execute("SELECT message_kind, bulletin_code, path, message_text FROM bulletins").fetchone()
                assert row is not None
                self.assertEqual(row["message_kind"], "announcement")
                self.assertEqual(row["bulletin_code"], "A")
                self.assertIsNone(row["path"])
                self.assertEqual(row["message_text"], "Test bulletin")
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
