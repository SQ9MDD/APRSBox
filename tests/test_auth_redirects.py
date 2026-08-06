from __future__ import annotations

import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import patch

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None

if FASTAPI_AVAILABLE:
    from starlette.requests import Request

    from app.routers.auth import login_page, login_submit


def build_request(*, session: dict[str, object] | None = None):
    app = SimpleNamespace(
        state=SimpleNamespace(
            templates=object(),
            get_client_ip=lambda _request: "127.0.0.1",
        )
    )
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/login",
            "root_path": "/aprsbox",
            "headers": [],
            "query_string": b"",
            "session": session or {},
            "app": app,
        }
    )


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
class AuthRedirectTests(unittest.TestCase):
    def test_authenticated_login_page_redirects_to_map(self) -> None:
        response = login_page(build_request(session={"user_id": 7}))

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/aprsbox/map")

    @patch("app.routers.auth.log_event")
    @patch("app.routers.auth.mark_user_login")
    @patch("app.routers.auth.authenticate_user")
    def test_successful_login_redirects_to_map(
        self,
        authenticate_user_mock,
        mark_user_login_mock,
        _log_event_mock,
    ) -> None:
        authenticate_user_mock.return_value = SimpleNamespace(
            id=7,
            username="tester",
            role="viewer",
        )
        request = build_request()

        response = login_submit(request, username="tester", password="secret")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/aprsbox/map")
        self.assertEqual(request.session["user_id"], 7)
        mark_user_login_mock.assert_called_once_with(7)


if __name__ == "__main__":
    unittest.main()
