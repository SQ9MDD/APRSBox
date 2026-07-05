import importlib.util
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
