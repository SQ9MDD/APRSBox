import contextlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.db import init_db

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None

if FASTAPI_AVAILABLE:
    from app.template_helpers import build_template_context
    from starlette.requests import Request


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


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class RoleAccessTests(unittest.TestCase):
    def test_viewer_navigation_is_limited_to_monitoring_pages(self) -> None:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/dashboard",
                "root_path": "",
                "headers": [],
                "query_string": b"",
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
                "scheme": "http",
            }
        )
        current_user = SimpleNamespace(role="viewer", username="viewer")

        context = build_template_context(request, page_title="Dashboard", current_user=current_user, active_nav="dashboard")
        navigation_order = [item["key"] for item in context["navigation"] if not item.get("separator")]
        navigation = {item["key"]: item for item in context["navigation"] if not item.get("separator")}

        self.assertEqual(
            navigation_order[:9],
            [
                "dashboard",
                "map",
                "stations",
                "traffic",
                "alerts",
                "band-condition",
                "statistics",
                "modems",
                "station",
            ],
        )
        primary_separator_index = next(
            index
            for index, item in enumerate(context["navigation"])
            if item.get("key") == "nav-separator-primary"
        )
        self.assertEqual(
            context["navigation"][primary_separator_index + 1]["key"],
            "modems",
        )

        for key in ("dashboard", "stations", "map", "band-condition", "modems", "traffic", "alerts", "statistics"):
            self.assertIn(key, navigation)
            self.assertFalse(bool(navigation[key].get("disabled")), key)

        for key in ("station", "wx", "messages", "notifications", "objects", "bulletins", "digi-flows", "igate", "logs", "users", "settings", "changelog"):
            self.assertIn(key, navigation)
            self.assertTrue(bool(navigation[key].get("disabled")), key)

    def test_viewer_can_open_allowed_pages_and_cannot_open_restricted_pages(self) -> None:
        with temporary_database():
            from fastapi.testclient import TestClient

            from app.dependencies import get_current_user
            from app.main import app
            from app.models import UserIdentity

            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=2,
                username="viewer",
                role="viewer",
                is_active=True,
            )
            try:
                client = TestClient(app)
                for path in (
                    "/dashboard",
                    "/stations",
                    "/map",
                    "/band-condition",
                    "/settings/modems",
                    "/traffic",
                    "/alerts",
                    "/statistics",
                ):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200, path)

                for path in ("/messages", "/settings", "/station", "/wx", "/objects", "/admin/users"):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 403, path)
            finally:
                app.dependency_overrides.pop(get_current_user, None)

    def test_operator_cannot_open_user_management(self) -> None:
        with temporary_database():
            from fastapi.testclient import TestClient

            from app.dependencies import get_current_user
            from app.main import app
            from app.models import UserIdentity

            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=3,
                username="operator",
                role="operator",
                is_active=True,
            )
            try:
                client = TestClient(app)
                self.assertEqual(client.get("/settings").status_code, 200)
                self.assertEqual(client.get("/admin/users").status_code, 403)
            finally:
                app.dependency_overrides.pop(get_current_user, None)


if __name__ == "__main__":
    unittest.main()
