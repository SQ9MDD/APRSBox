import io
import json
import unittest
from unittest.mock import patch

from app.services.core_client import restart_core_traffic_monitor


class _DummyResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class CoreClientTests(unittest.TestCase):
    def test_restart_core_traffic_monitor_returns_ok_on_successful_response(self) -> None:
        with patch("app.services.core_client.urlopen", return_value=_DummyResponse(json.dumps({"ok": True}).encode("utf-8"))):
            result = restart_core_traffic_monitor()

        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()
