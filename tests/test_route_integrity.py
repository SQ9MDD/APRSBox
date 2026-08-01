import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


class RouteIntegrityTests(unittest.TestCase):
    def test_map_page_route_is_declared_once(self) -> None:
        source = Path("app/routers/pages.py").read_text(encoding="utf-8")

        self.assertEqual(source.count('@router.get("/map")'), 1)
        self.assertIn('return templates.TemplateResponse("map.html", context)', source)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
    def test_map_page_route_is_registered_once(self) -> None:
        from app.routers.pages import router

        map_routes = [
            route
            for route in router.routes
            if getattr(route, "path", None) == "/map"
            and "GET" in (getattr(route, "methods", set()) or set())
        ]

        self.assertEqual(len(map_routes), 1)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
    def test_map_alert_area_endpoint_honors_matching_etag(self) -> None:
        from starlette.requests import Request

        from app.routers.pages import map_alert_areas

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/map/alert-areas",
                "headers": [
                    (b"if-none-match", b'"map-alert-areas-revision-1"'),
                ],
            }
        )
        with patch(
            "app.routers.pages.get_map_alert_areas_payload",
            return_value={
                "revision": "revision-1",
                "alert_areas": {"type": "FeatureCollection", "features": []},
            },
        ):
            response = map_alert_areas(request, None)

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.headers["etag"], '"map-alert-areas-revision-1"')
        self.assertEqual(response.headers["cache-control"], "private, no-cache")


if __name__ == "__main__":
    unittest.main()
