from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.content import build_station_detail_href, get_heard_station_snapshots, get_station_settings

DEFAULT_STATION_ZOOM = 10
DETAIL_STATION_ZOOM = 14
FALLBACK_CENTER = {"latitude": 52.1, "longitude": 19.4, "zoom": 6}
STALE_AFTER_SECONDS = 30 * 60


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


def get_map_station_payload() -> dict[str, Any]:
    stations: list[dict[str, Any]] = []
    for station in get_heard_station_snapshots():
        latitude = _parse_coordinate(station.get("latitude"))
        longitude = _parse_coordinate(station.get("longitude"))
        if latitude is None or longitude is None:
            continue
        stations.append(
            {
                "callsign": station["callsign"],
                "ssid": station["ssid"],
                "display_callsign": station["display_callsign"],
                "latitude": latitude,
                "longitude": longitude,
                "symbol_icon": station["symbol_icon"],
                "symbol_table": station["symbol_table"],
                "symbol_code": station["symbol_code"],
                "comment": station["comment"],
                "path": station["path"],
                "source": station["source"],
                "last_heard_at": station["last_heard_at"],
                "last_heard_age_s": station["last_heard_age_s"],
                "aprs_device_short": station.get("aprs_device_short", ""),
                "speed": _speed_kmh(station["data_raw"]),
                "course": _integer_value(station["data_raw"].get("course_deg")),
                "altitude": _altitude_meters(station["data_raw"]),
                "destination": station["destination"],
                "packet_type": station["frame_type"],
                "stale": bool((station["last_heard_age_s"] or 0) >= STALE_AFTER_SECONDS),
                "detail_href": build_station_detail_href(station["display_callsign"]),
            }
        )
    return {"stations": stations}


def get_station_detail_map_config(station: dict[str, Any]) -> dict[str, Any]:
    return {
        "latitude": station.get("latitude_float"),
        "longitude": station.get("longitude_float"),
        "zoom": DETAIL_STATION_ZOOM,
        "tile_url": settings.map_tile_url,
        "tile_attribution": settings.map_tile_attribution,
        "tile_source_name": settings.map_tile_source_name,
        "display_callsign": station.get("display_callsign", ""),
        "symbol_icon": station.get("symbol_icon", "icons/verG/x.gif"),
        "detail_href": station.get("detail_href", ""),
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


def _speed_kmh(metrics: dict[str, Any]) -> int | None:
    speed_knots = metrics.get("speed_knots")
    if speed_knots is None:
        return None
    return int(round(float(speed_knots) * 1.852))


def _altitude_meters(metrics: dict[str, Any]) -> int | None:
    altitude_ft = metrics.get("altitude_ft")
    if altitude_ft is None:
        return None
    return int(round(float(altitude_ft) * 0.3048))


def _integer_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None
