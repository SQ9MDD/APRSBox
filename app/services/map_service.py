from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.services.content import build_station_detail_href, get_station_settings, get_visible_station_snapshots, parse_tnc2_frame

DEFAULT_STATION_ZOOM = 10
DETAIL_STATION_ZOOM = 14
FALLBACK_CENTER = {"latitude": 52.1, "longitude": 19.4, "zoom": 6}
STALE_AFTER_SECONDS = 30 * 60
MOBILE_TRACK_SCAN_ROW_LIMIT = 8000
MOBILE_TRACK_MAX_POINTS_PER_STATION = 60
MAP_SOURCE_MIN_ZOOM_DEFAULT = 0
MAP_SOURCE_MAX_ZOOM_DEFAULT = 19
MAP_SOURCE_SORT_ORDER_DEFAULT = 0
MAP_SOURCE_ZOOM_MIN = 0
MAP_SOURCE_ZOOM_MAX = 30
MAP_SOURCE_REQUIRED_TILE_TOKENS = ("{z}", "{x}", "{y}")


def list_map_sources() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT
            id,
            name,
            url_template,
            attribution,
            min_zoom,
            max_zoom,
            subdomains,
            api_key,
            enabled,
            is_default,
            sort_order,
            notes,
            created_at,
            updated_at
        FROM map_sources
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC, id ASC
        """
    )
    return [_normalize_map_source_row(dict(row)) for row in rows]


def get_map_source(source_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT
            id,
            name,
            url_template,
            attribution,
            min_zoom,
            max_zoom,
            subdomains,
            api_key,
            enabled,
            is_default,
            sort_order,
            notes,
            created_at,
            updated_at
        FROM map_sources
        WHERE id = ?
        """,
        (int(source_id),),
    )
    if row is None:
        return None
    return _normalize_map_source_row(dict(row))


def safe_save_map_source(payload: dict[str, Any], *, source_id: int | None = None) -> tuple[bool, str | None, int | None]:
    try:
        saved_id = save_map_source(payload, source_id=source_id)
    except ValueError as exc:
        return False, str(exc), None
    return True, None, saved_id


def save_map_source(payload: dict[str, Any], *, source_id: int | None = None) -> int:
    values = normalize_map_source_payload(payload)
    timestamp = utc_now()
    with get_connection() as connection:
        if source_id is not None:
            existing = connection.execute("SELECT id FROM map_sources WHERE id = ?", (int(source_id),)).fetchone()
            if existing is None:
                raise ValueError("Map source not found.")
        row_count = connection.execute("SELECT COUNT(*) AS total FROM map_sources").fetchone()
        is_first_record = int(row_count["total"]) == 0 if row_count is not None else False
        if is_first_record:
            values["enabled"] = 1
            values["is_default"] = 1
        if values["is_default"] == 1:
            connection.execute(
                """
                UPDATE map_sources
                SET is_default = 0,
                    updated_at = ?
                WHERE is_default = 1
                  AND id != ?
                """,
                (timestamp, int(source_id or -1)),
            )

        if source_id is None:
            cursor = connection.execute(
                """
                INSERT INTO map_sources (
                    name,
                    url_template,
                    attribution,
                    min_zoom,
                    max_zoom,
                    subdomains,
                    api_key,
                    enabled,
                    is_default,
                    sort_order,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["name"],
                    values["url_template"],
                    values["attribution"],
                    values["min_zoom"],
                    values["max_zoom"],
                    values["subdomains"],
                    values["api_key"],
                    values["enabled"],
                    values["is_default"],
                    values["sort_order"],
                    values["notes"],
                    timestamp,
                    timestamp,
                ),
            )
            saved_id = int(cursor.lastrowid)
        else:
            saved_id = int(source_id)
            connection.execute(
                """
                UPDATE map_sources
                SET name = ?,
                    url_template = ?,
                    attribution = ?,
                    min_zoom = ?,
                    max_zoom = ?,
                    subdomains = ?,
                    api_key = ?,
                    enabled = ?,
                    is_default = ?,
                    sort_order = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    values["name"],
                    values["url_template"],
                    values["attribution"],
                    values["min_zoom"],
                    values["max_zoom"],
                    values["subdomains"],
                    values["api_key"],
                    values["enabled"],
                    values["is_default"],
                    values["sort_order"],
                    values["notes"],
                    timestamp,
                    saved_id,
                ),
            )
        _validate_map_sources_state(connection)

    log_event(
        "INFO",
        "config",
        f"Saved map source {saved_id} ({values['name']})",
    )
    return saved_id


def safe_delete_map_source(source_id: int) -> tuple[bool, str | None]:
    try:
        delete_map_source(source_id)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def delete_map_source(source_id: int) -> None:
    with get_connection() as connection:
        rows = list(
            connection.execute(
                """
                SELECT id, name, enabled, is_default
                FROM map_sources
                ORDER BY sort_order ASC, id ASC
                """
            ).fetchall()
        )
        if not rows:
            raise ValueError("No map sources available.")
        if len(rows) <= 1:
            raise ValueError("Cannot delete the only map source.")

        target = next((row for row in rows if int(row["id"]) == int(source_id)), None)
        if target is None:
            raise ValueError("Map source not found.")
        if int(target["is_default"] or 0) == 1:
            raise ValueError("Select another default map source before deleting this source.")

        connection.execute("DELETE FROM map_sources WHERE id = ?", (int(source_id),))
        _validate_map_sources_state(connection)

    log_event("INFO", "config", f"Deleted map source {source_id}")


def safe_set_default_map_source(source_id: int) -> tuple[bool, str | None]:
    try:
        set_default_map_source(source_id)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def set_default_map_source(source_id: int) -> None:
    with get_connection() as connection:
        target = connection.execute(
            "SELECT id, enabled FROM map_sources WHERE id = ?",
            (int(source_id),),
        ).fetchone()
        if target is None:
            raise ValueError("Map source not found.")
        if int(target["enabled"] or 0) != 1:
            raise ValueError("Disabled map source cannot be set as default.")

        timestamp = utc_now()
        connection.execute(
            """
            UPDATE map_sources
            SET is_default = 0,
                updated_at = ?
            WHERE is_default = 1
            """,
            (timestamp,),
        )
        connection.execute(
            """
            UPDATE map_sources
            SET is_default = 1,
                updated_at = ?
            WHERE id = ?
            """,
            (timestamp, int(source_id)),
        )
        _validate_map_sources_state(connection)

    log_event("INFO", "config", f"Set default map source to {source_id}")


def normalize_map_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Map source name is required.")

    url_template = str(payload.get("url_template") or "").strip()
    if not url_template:
        raise ValueError("Map URL template is required.")
    if not _has_required_tile_tokens(url_template):
        raise ValueError("Map URL template must include {z}, {x}, and {y}.")

    min_zoom = _normalize_zoom(payload.get("min_zoom"), default=MAP_SOURCE_MIN_ZOOM_DEFAULT, label="Min zoom")
    max_zoom = _normalize_zoom(payload.get("max_zoom"), default=MAP_SOURCE_MAX_ZOOM_DEFAULT, label="Max zoom")
    if min_zoom > max_zoom:
        raise ValueError("Min zoom cannot be greater than max zoom.")

    enabled = _normalize_checkbox(payload.get("enabled"))
    is_default = _normalize_checkbox(payload.get("is_default"))
    if enabled == 0 and is_default == 1:
        raise ValueError("Disabled map source cannot be default.")

    return {
        "name": name,
        "url_template": url_template,
        "attribution": str(payload.get("attribution") or "").strip(),
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "subdomains": _normalize_subdomains(payload.get("subdomains")),
        "api_key": str(payload.get("api_key") or "").strip(),
        "enabled": enabled,
        "is_default": is_default,
        "sort_order": _normalize_sort_order(payload.get("sort_order")),
        "notes": str(payload.get("notes") or "").strip(),
    }


def get_default_map_source() -> dict[str, Any] | None:
    sources = list_map_sources()
    if not sources:
        return None
    preferred = next((item for item in sources if item["enabled"] and item["is_default"]), None)
    if preferred is None:
        preferred = next((item for item in sources if item["is_default"]), None)
    if preferred is None:
        preferred = next((item for item in sources if item["enabled"]), None)
    if preferred is None:
        preferred = sources[0]
    return dict(preferred)


def resolve_active_tile_layer() -> dict[str, Any]:
    source = get_default_map_source()
    if source is None:
        return {
            "tile_url": "",
            "tile_attribution": "",
            "tile_source_name": "",
            "tile_min_zoom": MAP_SOURCE_MIN_ZOOM_DEFAULT,
            "tile_max_zoom": MAP_SOURCE_MAX_ZOOM_DEFAULT,
            "tile_subdomains": "",
        }
    url_template = str(source.get("url_template") or "")
    api_key = str(source.get("api_key") or "")
    resolved_url = url_template.replace("{apiKey}", quote(api_key, safe=""))
    return {
        "tile_url": resolved_url,
        "tile_attribution": str(source.get("attribution") or ""),
        "tile_source_name": str(source.get("name") or ""),
        "tile_min_zoom": int(source.get("min_zoom") or MAP_SOURCE_MIN_ZOOM_DEFAULT),
        "tile_max_zoom": int(source.get("max_zoom") or MAP_SOURCE_MAX_ZOOM_DEFAULT),
        "tile_subdomains": str(source.get("subdomains") or ""),
    }


def _normalize_map_source_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "name": str(row.get("name") or "").strip(),
        "url_template": str(row.get("url_template") or "").strip(),
        "attribution": str(row.get("attribution") or "").strip(),
        "min_zoom": _coerce_zoom_value(row.get("min_zoom"), default=MAP_SOURCE_MIN_ZOOM_DEFAULT),
        "max_zoom": _coerce_zoom_value(row.get("max_zoom"), default=MAP_SOURCE_MAX_ZOOM_DEFAULT),
        "subdomains": _normalize_subdomains(row.get("subdomains")),
        "api_key": str(row.get("api_key") or "").strip(),
        "enabled": bool(int(row.get("enabled") or 0)),
        "is_default": bool(int(row.get("is_default") or 0)),
        "sort_order": _normalize_sort_order(row.get("sort_order")),
        "notes": str(row.get("notes") or "").strip(),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _normalize_zoom(value: Any, *, default: int, label: str) -> int:
    text = str(value or "").strip()
    if not text:
        parsed = default
    else:
        try:
            parsed = int(text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be an integer.") from exc
    if parsed < MAP_SOURCE_ZOOM_MIN or parsed > MAP_SOURCE_ZOOM_MAX:
        raise ValueError(f"{label} must be between {MAP_SOURCE_ZOOM_MIN} and {MAP_SOURCE_ZOOM_MAX}.")
    return parsed


def _coerce_zoom_value(value: Any, *, default: int) -> int:
    parsed = _safe_int(value, default=default)
    if parsed < MAP_SOURCE_ZOOM_MIN:
        return MAP_SOURCE_ZOOM_MIN
    if parsed > MAP_SOURCE_ZOOM_MAX:
        return MAP_SOURCE_ZOOM_MAX
    return parsed


def _normalize_sort_order(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return MAP_SOURCE_SORT_ORDER_DEFAULT
    try:
        return int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Sort order must be an integer.") from exc


def _safe_int(value: Any, *, default: int) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _normalize_checkbox(value: Any) -> int:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "on", "yes"}:
        return 1
    return 0


def _normalize_subdomains(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    tokens = [token for token in re.split(r"[,\s]+", text) if token]
    return ",".join(tokens)


def _has_required_tile_tokens(url_template: str) -> bool:
    normalized = str(url_template or "").strip().lower()
    if not normalized:
        return False
    encoded_normalized = normalized.replace("%7b", "{").replace("%7d", "}")
    return all(token in encoded_normalized for token in MAP_SOURCE_REQUIRED_TILE_TOKENS)


def _validate_map_sources_state(connection: Any) -> None:
    rows = list(
        connection.execute(
            """
            SELECT id, enabled, is_default
            FROM map_sources
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()
    )
    if not rows:
        raise ValueError("At least one map source must remain configured.")

    default_rows = [row for row in rows if int(row["is_default"] or 0) == 1]
    if len(default_rows) > 1:
        raise ValueError("Only one map source can be set as default.")
    if len(default_rows) == 0:
        raise ValueError("One enabled map source must be set as default.")
    if int(default_rows[0]["enabled"] or 0) != 1:
        raise ValueError("Default map source must be enabled.")


def get_map_page_config() -> dict[str, Any]:
    station_settings = get_station_settings()
    default_view = _resolve_default_view(station_settings)
    tile_layer = resolve_active_tile_layer()
    return {
        "station_latitude": default_view["latitude"],
        "station_longitude": default_view["longitude"],
        "default_zoom": default_view["zoom"],
        "tile_url": tile_layer["tile_url"],
        "tile_attribution": tile_layer["tile_attribution"],
        "tile_source_name": tile_layer["tile_source_name"],
        "tile_min_zoom": tile_layer["tile_min_zoom"],
        "tile_max_zoom": tile_layer["tile_max_zoom"],
        "tile_subdomains": tile_layer["tile_subdomains"],
    }


def get_map_station_payload() -> dict[str, Any]:
    stations: list[dict[str, Any]] = []
    for station in get_visible_station_snapshots():
        latitude = _parse_coordinate(station.get("latitude"))
        longitude = _parse_coordinate(station.get("longitude"))
        if latitude is None or longitude is None:
            continue
        stations.append(
            {
                "callsign": station["callsign"],
                "ssid": station["ssid"],
                "display_callsign": station["display_callsign"],
                "origin": station.get("origin", "heard"),
                "activity_label": station.get("activity_label", "Last heard"),
                "activity_age_label": station.get("activity_age_label", "Last heard age"),
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
                "distance_km": station.get("distance_km"),
                "aprs_device_short": station.get("aprs_device_short", ""),
                "speed": _speed_kmh(station["data_raw"]),
                "course": _integer_value(station["data_raw"].get("course_deg")),
                "altitude": _altitude_meters(station["data_raw"]),
                "phg_power_w": _float_value(station["data_raw"].get("phg_power_w")),
                "phg_height_ft": _float_value(station["data_raw"].get("phg_height_ft")),
                "phg_gain_dbi": _float_value(station["data_raw"].get("phg_gain_dbi")),
                "phg_direction": station["data_raw"].get("phg_direction"),
                "phg_range_km": _phg_range_km(station["data_raw"]),
                "qsy_frequency_mhz": _float_value(station["data_raw"].get("qsy_frequency_mhz")),
                "qsy_tone": _string_or_none(station["data_raw"].get("qsy_tone")),
                "qsy_offset_khz": _integer_value(station["data_raw"].get("qsy_offset_khz")),
                "qsy_callsign": _string_or_none(station["data_raw"].get("qsy_callsign")),
                "destination": station["destination"],
                "packet_type": station["frame_type"],
                "stale": bool((station["last_heard_age_s"] or 0) >= STALE_AFTER_SECONDS),
                "detail_href": build_station_detail_href(station["display_callsign"]),
            }
        )
    return {
        "stations": stations,
        "mobile_tracks": _build_mobile_station_tracks(stations),
    }


def get_station_detail_map_config(station: dict[str, Any]) -> dict[str, Any]:
    tile_layer = resolve_active_tile_layer()
    return {
        "latitude": station.get("latitude_float"),
        "longitude": station.get("longitude_float"),
        "zoom": DETAIL_STATION_ZOOM,
        "tile_url": tile_layer["tile_url"],
        "tile_attribution": tile_layer["tile_attribution"],
        "tile_source_name": tile_layer["tile_source_name"],
        "tile_min_zoom": tile_layer["tile_min_zoom"],
        "tile_max_zoom": tile_layer["tile_max_zoom"],
        "tile_subdomains": tile_layer["tile_subdomains"],
        "display_callsign": station.get("display_callsign", ""),
        "symbol_icon": station.get("symbol_icon", "icons/verG/x.gif"),
        "detail_href": station.get("detail_href", ""),
    }


def get_station_detail_track_payload(display_callsign: str) -> dict[str, Any]:
    normalized_callsign = str(display_callsign or "").strip()
    if not normalized_callsign:
        return {"display_callsign": "", "points": []}
    points = _build_mobile_track_points_by_station_keys({normalized_callsign.casefold(): normalized_callsign})
    return {
        "display_callsign": normalized_callsign,
        "points": points.get(normalized_callsign, []),
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


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _phg_range_km(metrics: dict[str, Any]) -> float | None:
    power_w = _float_value(metrics.get("phg_power_w"))
    height_ft = _float_value(metrics.get("phg_height_ft"))
    gain_dbi = _float_value(metrics.get("phg_gain_dbi"))
    if power_w is None or height_ft is None or gain_dbi is None:
        return None
    if power_w <= 0 or height_ft <= 0:
        return None

    # APRS-SPEC/PROTOCOL.TXT:
    # GAIN = 10^(g/10)
    # RANGE = sqrt(2*H*sqrt((P/10)*(GAIN/2)))  (miles)
    gain_linear = 10 ** (gain_dbi / 10.0)
    range_miles = (2.0 * height_ft * (((power_w / 10.0) * (gain_linear / 2.0)) ** 0.5)) ** 0.5
    return round(range_miles * 1.609344, 2)


def _build_mobile_station_tracks(stations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_station_keys: dict[str, str] = {}
    for station in stations:
        display_callsign = str(station.get("display_callsign") or "").strip()
        if display_callsign:
            visible_station_keys[display_callsign.casefold()] = display_callsign
    if not visible_station_keys:
        return []
    points_by_station = _build_mobile_track_points_by_station_keys(visible_station_keys)

    tracks: list[dict[str, Any]] = []
    for display_callsign, points in points_by_station.items():
        if len(points) < 2:
            continue
        tracks.append(
            {
                "display_callsign": display_callsign,
                "points": points,
            }
        )
    tracks.sort(key=lambda item: str(item.get("display_callsign") or ""))
    return tracks


def _is_null_island_point(latitude: float, longitude: float) -> bool:
    return abs(latitude) < 1e-6 and abs(longitude) < 1e-6


def _is_same_track_position(point: dict[str, Any], latitude: float, longitude: float) -> bool:
    point_latitude = _parse_coordinate(point.get("latitude"))
    point_longitude = _parse_coordinate(point.get("longitude"))
    if point_latitude is None or point_longitude is None:
        return False
    return abs(point_latitude - latitude) < 1e-6 and abs(point_longitude - longitude) < 1e-6


def _build_mobile_track_points_by_station_keys(
    station_keys: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    if not station_keys:
        return {}

    rows = fetch_all(
        """
        SELECT line, created_at
        FROM (
            SELECT line, created_at, id
            FROM traffic_frames
            WHERE format IN ('TNC2', 'TNC2-TX')
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ) AS recent
        ORDER BY created_at ASC, id ASC
        """,
        (MOBILE_TRACK_SCAN_ROW_LIMIT,),
    )

    points_by_station: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        parsed = parse_tnc2_frame(str(row["line"] or ""))
        if parsed is None:
            continue
        station_key = str(parsed.get("entity_name") or parsed.get("logical_source_key") or parsed.get("source_key") or "").strip()
        if not station_key:
            continue
        resolved_key = station_keys.get(station_key.casefold())
        if not resolved_key:
            continue

        aprs_data = dict(parsed.get("aprs_data") or {})
        latitude = _parse_coordinate(aprs_data.get("latitude"))
        longitude = _parse_coordinate(aprs_data.get("longitude"))
        if latitude is None or longitude is None:
            continue
        if _is_null_island_point(latitude, longitude):
            continue

        points = points_by_station.setdefault(resolved_key, [])
        if points and _is_same_track_position(points[-1], latitude, longitude):
            continue
        points.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "heard_at": str(row["created_at"] or ""),
            }
        )
        if len(points) > MOBILE_TRACK_MAX_POINTS_PER_STATION:
            points.pop(0)
    return points_by_station
