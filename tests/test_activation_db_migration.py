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


class ActivationScheduleMigrationTests(unittest.TestCase):
    def test_init_db_preserves_object_valid_until_when_rebuilding_interval_constraint(self) -> None:
        with temporary_database() as database_path:
            raw = sqlite3.connect(database_path)
            try:
                raw.executescript(
                    """
                    CREATE TABLE aprs_objects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        lifetime TEXT NOT NULL DEFAULT 'temporary',
                        state TEXT NOT NULL DEFAULT 'live',
                        is_enabled INTEGER NOT NULL DEFAULT 0,
                        interval_minutes INTEGER NOT NULL DEFAULT 30,
                        valid_until_utc TEXT,
                        latitude TEXT,
                        longitude TEXT,
                        symbol_table TEXT,
                        symbol_code TEXT,
                        path TEXT,
                        comment TEXT,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO aprs_objects(name, lifetime, state, is_enabled, interval_minutes, valid_until_utc, updated_at)
                    VALUES ('TESTOBJ', 'temporary', 'live', 1, 30, '2026-06-30 12:00', '2026-01-01T00:00:00+00:00');
                    """
                )
                raw.commit()
            finally:
                raw.close()

            init_db()

            connection = connect()
            try:
                row = connection.execute("SELECT valid_until_utc, activation_mode FROM aprs_objects").fetchone()
                assert row is not None
                self.assertEqual(row["valid_until_utc"], "2026-06-30 12:00")
                self.assertEqual(row["activation_mode"], "manual")
            finally:
                connection.close()

    def test_init_db_preserves_item_valid_until_when_rebuilding_interval_constraint(self) -> None:
        with temporary_database() as database_path:
            raw = sqlite3.connect(database_path)
            try:
                raw.executescript(
                    """
                    CREATE TABLE aprs_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        state TEXT NOT NULL DEFAULT 'live',
                        is_enabled INTEGER NOT NULL DEFAULT 0,
                        interval_minutes INTEGER NOT NULL DEFAULT 30,
                        valid_until_utc TEXT,
                        latitude TEXT,
                        longitude TEXT,
                        symbol_table TEXT,
                        symbol_code TEXT,
                        path TEXT,
                        comment TEXT,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO aprs_items(name, state, is_enabled, interval_minutes, valid_until_utc, updated_at)
                    VALUES ('TESTITEM', 'live', 1, 30, '2026-06-30 12:00', '2026-01-01T00:00:00+00:00');
                    """
                )
                raw.commit()
            finally:
                raw.close()

            init_db()

            connection = connect()
            try:
                row = connection.execute("SELECT valid_until_utc, activation_mode FROM aprs_items").fetchone()
                assert row is not None
                self.assertEqual(row["valid_until_utc"], "2026-06-30 12:00")
                self.assertEqual(row["activation_mode"], "manual")
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
