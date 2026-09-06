import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db


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


class ObjectStatusTests(unittest.TestCase):
    def test_object_toggle_changes_only_enabled_flag_and_keeps_group_schedule(self) -> None:
        with temporary_database():
            try:
                import fastapi  # noqa: F401
            except ModuleNotFoundError:
                self.skipTest("fastapi is not installed in this environment")
            from app.models import UserIdentity
            from app.routers.pages import objects_toggle
            from starlette.requests import Request

            execute(
                """
                INSERT INTO aprs_objects(
                    name, group_name, lifetime, state, is_enabled, interval_minutes,
                    activation_mode, active_from_utc, active_until_utc,
                    symbol_table, symbol_code, comment, updated_at
                ) VALUES (?, ?, 'permanent', 'live', 1, 45, 'scheduled', ?, ?, '/', 'r', ?, ?)
                """,
                ("TOGGLE", "Network", "2026-09-07 10:00", "2026-09-08 10:00", "Scheduled repeater", "2026-09-06T00:00:00+00:00"),
            )
            request = Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/settings/objects/1/toggle",
                    "root_path": "",
                    "headers": [(b"x-requested-with", b"XMLHttpRequest")],
                    "query_string": b"",
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                    "scheme": "http",
                }
            )
            user = UserIdentity(id=1, username="admin", role="admin", is_active=True)
            response = objects_toggle(1, request, user, enabled=0, group="Network")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                json.loads(response.body),
                {
                    "ok": True,
                    "message": "Object status updated.",
                    "reload": True,
                    "redirect": "/objects?group=Network",
                },
            )
            row = fetch_one(
                "SELECT group_name, lifetime, is_enabled, interval_minutes, activation_mode, active_from_utc, active_until_utc FROM aprs_objects WHERE id = 1"
            )
            assert row is not None
            self.assertEqual(
                dict(row),
                {
                    "group_name": "Network",
                    "lifetime": "permanent",
                    "is_enabled": 0,
                    "interval_minutes": 45,
                    "activation_mode": "scheduled",
                    "active_from_utc": "2026-09-07 10:00",
                    "active_until_utc": "2026-09-08 10:00",
                },
            )
