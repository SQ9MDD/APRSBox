from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from app.config import settings


def unavailable_traffic_snapshot(detail: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "status_detail": detail,
        "active_modem": None,
        "last_error": detail,
        "updated_at": None,
        "frames": [],
    }


def get_core_traffic_snapshot() -> dict[str, Any]:
    try:
        with urlopen(f"{settings.core_base_url}/api/traffic", timeout=1.5) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        return unavailable_traffic_snapshot(f"aprs-core HTTP error: {exc.code}")
    except URLError as exc:
        return unavailable_traffic_snapshot(f"aprs-core unavailable: {exc.reason}")
    except OSError as exc:
        return unavailable_traffic_snapshot(f"aprs-core connection failed: {exc}")

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return unavailable_traffic_snapshot("aprs-core returned invalid JSON.")
