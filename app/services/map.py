from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.content import get_station_settings

DEFAULT_STATION_ZOOM = 10
FALLBACK_CENTER = {"latitude": 52.1, "longitude": 19.4, "zoom": 6}


def get_map_page_config() -> dict[str, Any]:
    station_settings = get_station_settings()
    default_view = _resolve_default_view(station_settings)
    return {
        "station_latitude": default_view["latitude"],
        "station_longitude": default_view["longitude"],
        "default_zoom": default_view["zoom"],
        # The default public OSM tiles are acceptable for development/testing.
        # Keep the URL in backend config so production can switch to a local
        # cache/proxy or another provider without touching the frontend code.
        "tile_url": settings.map_tile_url,
        "tile_attribution": settings.map_tile_attribution,
        "tile_source_name": settings.map_tile_source_name,
    }


def _resolve_default_view(station_settings: dict[str, Any]) -> dict[str, float | int]:
    latitude = _parse_coordinate(station_settings.get("latitude"))
    longitude = _parse_coordinate(station_settings.get("longitude"))
    if latitude is None or longitude is None:
        return dict(FALLBACK_CENTER)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "zoom": DEFAULT_STATION_ZOOM,
    }


def _parse_coordinate(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
