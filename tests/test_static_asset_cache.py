import asyncio
import unittest

from app.main import StaticAssetCacheControlMiddleware


async def _response_headers(path: str) -> dict[str, str]:
    async def inner_app(scope, receive, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/css"),
                    (b"etag", b'"asset-etag"'),
                    (b"last-modified", b"Thu, 27 Aug 2026 17:30:04 GMT"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"body"})

    messages: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    middleware = StaticAssetCacheControlMiddleware(inner_app)
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
        },
        receive,
        send,
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    return {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in start["headers"]
    }


class StaticAssetCacheControlMiddlewareTests(unittest.TestCase):
    def test_static_asset_gets_cache_header_and_preserves_validators(self) -> None:
        headers = asyncio.run(_response_headers("/static/css/style.css"))

        self.assertEqual(headers["cache-control"], "public, max-age=86400")
        self.assertEqual(headers["etag"], '"asset-etag"')
        self.assertEqual(headers["last-modified"], "Thu, 27 Aug 2026 17:30:04 GMT")
        self.assertEqual(headers["content-type"], "text/css")

    def test_dynamic_routes_do_not_get_static_cache_header(self) -> None:
        for path in ("/dashboard", "/api/alerts/stream", "/api/traffic", "/health"):
            with self.subTest(path=path):
                headers = asyncio.run(_response_headers(path))
                self.assertNotIn("cache-control", headers)
