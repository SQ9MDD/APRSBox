from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, unquote

from app.db import fetch_all, fetch_one, get_app_setting, get_connection, log_event, set_app_setting, utc_now
from app.services.alert_areas import (
    build_alert_area_feature_collection,
    get_active_alert_area_feature_collection,
    get_active_alert_area_snapshot,
)
from app.services.content import (
    build_station_detail_href,
    format_decoded_data_for_display,
    get_aprs_symbol_icon_fallback_path,
    get_aprs_symbol_icon_path,
    get_configured_modem_interfaces,
    get_station_settings,
    get_visible_station_snapshot_revision,
    get_visible_station_snapshots,
    parse_tnc2_frame,
)
from app.services.traffic_source import RF_SOURCE_KIND
from app.services.map_station_state import read_map_station_state

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
MAP_TILE_PROXY_ENDPOINT = "/api/map/tiles"
COVERAGE_FILL_OPACITY_SETTING_KEY = "map_coverage_fill_opacity"
DEFAULT_COVERAGE_FILL_OPACITY_PERCENT = 5
MAP_MARKER_CLUSTERING_ENABLED_SETTING_KEY = "map_marker_clustering_enabled"


def normalize_coverage_fill_opacity_percent(value: Any) -> int:
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_COVERAGE_FILL_OPACITY_PERCENT
    if normalized < 0 or normalized > 20:
        return DEFAULT_COVERAGE_FILL_OPACITY_PERCENT
    return normalized


def get_coverage_fill_opacity_percent() -> int:
    return normalize_coverage_fill_opacity_percent(get_app_setting(COVERAGE_FILL_OPACITY_SETTING_KEY))


def get_map_marker_clustering_enabled() -> bool:
    return str(get_app_setting(MAP_MARKER_CLUSTERING_ENABLED_SETTING_KEY) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def save_map_marker_clustering_enabled(enabled: bool) -> bool:
    normalized = bool(enabled)
    set_app_setting(MAP_MARKER_CLUSTERING_ENABLED_SETTING_KEY, "1" if normalized else "0")
    return normalized


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
            local_cache_enabled,
            cache_tile_count,
            cache_size_bytes,
            enabled,
            is_default,
            sort_order,
            notes,
            created_at,
            updated_at
        FROM map_sources
        ORDER BY sort_order ASC, id ASC
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
            local_cache_enabled,
            cache_tile_count,
            cache_size_bytes,
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
    timestamp = utc_now()
    values_payload = dict(payload)
    with get_connection() as connection:
        existing_row = None
        if source_id is not None:
            existing_row = connection.execute(
                "SELECT id, subdomains, api_key, local_cache_enabled, sort_order FROM map_sources WHERE id = ?",
                (int(source_id),),
            ).fetchone()
            if existing_row is None:
                raise ValueError("Map source not found.")
            if "subdomains" not in values_payload:
                values_payload["subdomains"] = str(existing_row["subdomains"] or "")
            if "api_key" not in values_payload:
                values_payload["api_key"] = str(existing_row["api_key"] or "")
            if "local_cache_enabled" not in values_payload:
                values_payload["local_cache_enabled"] = int(existing_row["local_cache_enabled"] or 0)
            raw_sort_order = values_payload.get("sort_order")
            if "sort_order" not in values_payload or str(raw_sort_order or "").strip() == "":
                values_payload["sort_order"] = int(existing_row["sort_order"] or MAP_SOURCE_SORT_ORDER_DEFAULT)
        else:
            raw_sort_order = values_payload.get("sort_order")
            if "sort_order" not in values_payload or str(raw_sort_order or "").strip() == "":
                next_sort_order_row = connection.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_sort_order FROM map_sources"
                ).fetchone()
                values_payload["sort_order"] = (
                    int(next_sort_order_row["next_sort_order"])
                    if next_sort_order_row is not None
                    else MAP_SOURCE_SORT_ORDER_DEFAULT
                )

        values = normalize_map_source_payload(values_payload)
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
                    local_cache_enabled,
                    cache_tile_count,
                    cache_size_bytes,
                    enabled,
                    is_default,
                    sort_order,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["name"],
                    values["url_template"],
                    values["attribution"],
                    values["min_zoom"],
                    values["max_zoom"],
                    values["subdomains"],
                    values["api_key"],
                    values["local_cache_enabled"],
                    0,
                    0,
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
                    local_cache_enabled = ?,
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
                    values["local_cache_enabled"],
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


def safe_move_map_source(source_id: int, direction: str) -> tuple[bool, str | None]:
    try:
        move_map_source(source_id, direction)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def move_map_source(source_id: int, direction: str) -> None:
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"up", "down"}:
        raise ValueError("Invalid move direction.")

    with get_connection() as connection:
        rows = list(
            connection.execute(
                """
                SELECT id
                FROM map_sources
                ORDER BY sort_order ASC, id ASC
                """
            ).fetchall()
        )
        if not rows:
            raise ValueError("No map sources available.")

        ordered_ids = [int(row["id"]) for row in rows]
        if int(source_id) not in ordered_ids:
            raise ValueError("Map source not found.")

        index = ordered_ids.index(int(source_id))
        swap_index = index - 1 if normalized_direction == "up" else index + 1
        if swap_index < 0 or swap_index >= len(ordered_ids):
            return

        ordered_ids[index], ordered_ids[swap_index] = ordered_ids[swap_index], ordered_ids[index]

        timestamp = utc_now()
        for sort_order, current_source_id in enumerate(ordered_ids, start=1):
            connection.execute(
                """
                UPDATE map_sources
                SET sort_order = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (sort_order, timestamp, current_source_id),
            )
        _validate_map_sources_state(connection)

    log_event("INFO", "config", f"Moved map source {source_id} {normalized_direction}")


def increment_map_source_cache_stats(source_id: int, *, tile_size_bytes: int) -> None:
    safe_size = _safe_int(tile_size_bytes, default=0)
    if safe_size <= 0:
        return
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE map_sources
            SET cache_tile_count = cache_tile_count + 1,
                cache_size_bytes = cache_size_bytes + ?,
                updated_at = ?
            WHERE id = ?
            """,
            (safe_size, timestamp, int(source_id)),
        )


def reset_map_source_cache_stats(source_id: int) -> None:
    timestamp = utc_now()
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM map_sources WHERE id = ?", (int(source_id),)).fetchone()
        if row is None:
            raise ValueError("Map source not found.")
        connection.execute(
            """
            UPDATE map_sources
            SET cache_tile_count = 0,
                cache_size_bytes = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (timestamp, int(source_id)),
        )


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
        "local_cache_enabled": _normalize_checkbox(payload.get("local_cache_enabled")),
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


def resolve_active_tile_layer(*, root_path: str = "") -> dict[str, Any]:
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
    if bool(source.get("local_cache_enabled")):
        resolved_url = build_local_tile_proxy_url_template(
            int(source.get("id") or 0),
            root_path=root_path,
            include_subdomain=_has_tile_token(url_template, "s"),
        )
    return {
        "tile_url": resolved_url,
        "tile_attribution": str(source.get("attribution") or ""),
        "tile_source_name": str(source.get("name") or ""),
        "tile_min_zoom": int(source.get("min_zoom") or MAP_SOURCE_MIN_ZOOM_DEFAULT),
        "tile_max_zoom": int(source.get("max_zoom") or MAP_SOURCE_MAX_ZOOM_DEFAULT),
        "tile_subdomains": str(source.get("subdomains") or ""),
    }


def _normalize_map_source_row(row: dict[str, Any]) -> dict[str, Any]:
    cache_tile_count = _normalize_cache_counter(row.get("cache_tile_count"))
    cache_size_bytes = _normalize_cache_counter(row.get("cache_size_bytes"))
    return {
        "id": int(row.get("id") or 0),
        "name": str(row.get("name") or "").strip(),
        "url_template": str(row.get("url_template") or "").strip(),
        "attribution": str(row.get("attribution") or "").strip(),
        "min_zoom": _coerce_zoom_value(row.get("min_zoom"), default=MAP_SOURCE_MIN_ZOOM_DEFAULT),
        "max_zoom": _coerce_zoom_value(row.get("max_zoom"), default=MAP_SOURCE_MAX_ZOOM_DEFAULT),
        "subdomains": _normalize_subdomains(row.get("subdomains")),
        "api_key": str(row.get("api_key") or "").strip(),
        "local_cache_enabled": bool(int(row.get("local_cache_enabled") or 0)),
        "cache_tile_count": cache_tile_count,
        "cache_size_bytes": cache_size_bytes,
        "cache_size_label": _format_size_bytes(cache_size_bytes),
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


def _normalize_cache_counter(value: Any) -> int:
    parsed = _safe_int(value, default=0)
    return parsed if parsed >= 0 else 0


def _normalize_root_path(root_path: str) -> str:
    text = str(root_path or "").strip()
    if not text:
        return ""
    if not text.startswith("/"):
        text = f"/{text}"
    return text.rstrip("/")


def build_local_tile_proxy_url_template(
    source_id: int,
    *,
    root_path: str = "",
    include_subdomain: bool = False,
) -> str:
    normalized_root_path = _normalize_root_path(root_path)
    suffix = "?s={s}" if include_subdomain else ""
    return f"{normalized_root_path}{MAP_TILE_PROXY_ENDPOINT}/{int(source_id)}/{{z}}/{{x}}/{{y}}{suffix}"


def _format_size_bytes(size_bytes: int) -> str:
    value = float(size_bytes if size_bytes >= 0 else 0)
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while value >= 1024.0 and unit_index < len(units) - 1:
        value /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"


def _has_tile_token(url_template: str, token: str) -> bool:
    normalized = str(url_template or "").strip()
    if not normalized:
        return False
    try:
        decoded = unquote(normalized)
    except Exception:
        decoded = normalized
    prepared = (
        decoded
        .replace("%7b", "{")
        .replace("%7d", "}")
        .replace("&#123;", "{")
        .replace("&#125;", "}")
    )
    prepared = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", prepared)
    return re.search(r"\{\s*" + re.escape(token) + r"\s*\}", prepared, flags=re.IGNORECASE) is not None


def _has_required_tile_tokens(url_template: str) -> bool:
    return all(_has_tile_token(url_template, token.strip("{}")) for token in MAP_SOURCE_REQUIRED_TILE_TOKENS)


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


def get_map_page_config(*, root_path: str = "") -> dict[str, Any]:
    station_settings = get_station_settings()
    default_view = _resolve_default_view(station_settings)
    tile_layer = resolve_active_tile_layer(root_path=root_path)
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
        "coverage_fill_opacity": get_coverage_fill_opacity_percent(),
        "marker_clustering_enabled": get_map_marker_clustering_enabled(),
    }


def _map_station_revision() -> int | None:
    return get_visible_station_snapshot_revision()


def _build_map_station_marker_rows(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stations: list[dict[str, Any]] = []
    for station in snapshots:
        latitude = _parse_coordinate(station.get("latitude"))
        longitude = _parse_coordinate(station.get("longitude"))
        if latitude is None or longitude is None:
            continue
        last_heard_rf_at = station.get("last_heard_rf_at")
        has_rf_source = bool(last_heard_rf_at)
        marker_source_kind = RF_SOURCE_KIND if has_rf_source else station.get("source_kind", RF_SOURCE_KIND)
        marker_source = (
            station.get("last_heard_rf_source")
            if has_rf_source
            else station.get("source")
        )
        marker_interface_id = (
            station.get("last_heard_rf_interface_id")
            if has_rf_source
            else station.get("interface_id")
        )
        stations.append(
            {
                "callsign": station["callsign"],
                "ssid": station["ssid"],
                "display_callsign": station["display_callsign"],
                "detail_href": build_station_detail_href(station["display_callsign"]),
                "origin": station.get("origin", "heard"),
                "source_kind": marker_source_kind,
                "is_rf": has_rf_source or bool(station.get("is_rf")),
                "last_seen_any_at": station.get("last_seen_any_at"),
                "last_heard_rf_at": last_heard_rf_at,
                "last_heard_rf_interface_id": _normalize_interface_id(
                    station.get("last_heard_rf_interface_id")
                ),
                "last_seen_aprsis_at": station.get("last_seen_aprsis_at"),
                "last_seen_aprsis_interface_id": _normalize_interface_id(
                    station.get("last_seen_aprsis_interface_id")
                ),
                "activity_label": station.get("activity_label", "Last heard"),
                "activity_age_label": station.get("activity_age_label", "Last heard age"),
                "latitude": latitude,
                "longitude": longitude,
                "position_ambiguity_digits": station.get("position_ambiguity_digits"),
                "position_ambiguous": bool(station.get("position_ambiguous")),
                "symbol_icon": station["symbol_icon"],
                "symbol_table": station["symbol_table"],
                "symbol_code": station["symbol_code"],
                "source": marker_source,
                "interface_id": _normalize_interface_id(marker_interface_id),
                "last_heard_at": station["last_heard_at"],
                "last_heard_age_s": station["last_heard_age_s"],
                "distance_km": station.get("distance_km"),
                "entity_class": station["entity_class"],
                "packet_type": station["frame_type"],
                "stale": bool((station["last_heard_age_s"] or 0) >= STALE_AFTER_SECONDS),
            }
        )
    return stations


def _build_map_station_detail_rows(
    snapshots: list[dict[str, Any]],
    *,
    unit_system: str,
) -> list[dict[str, Any]]:
    stations = _build_map_station_marker_rows(snapshots)
    details_by_callsign = {
        str(snapshot["display_callsign"]): snapshot
        for snapshot in snapshots
    }
    for station in stations:
        snapshot = details_by_callsign.get(str(station["display_callsign"]))
        if snapshot is None:
            continue
        station["comment"] = snapshot["comment"]
        station["data"] = format_decoded_data_for_display(snapshot["data_raw"], unit_system)
        station["path"] = snapshot["path"]
        station["aprs_device_short"] = snapshot.get("aprs_device_short", "")
        station["speed"] = _speed_kmh(snapshot["data_raw"])
        station["course"] = _integer_value(snapshot["data_raw"].get("course_deg"))
        station["altitude"] = _altitude_meters(snapshot["data_raw"])
        station["phg_power_w"] = _float_value(snapshot["data_raw"].get("phg_power_w"))
        station["phg_height_ft"] = _float_value(snapshot["data_raw"].get("phg_height_ft"))
        station["phg_gain_dbi"] = _float_value(snapshot["data_raw"].get("phg_gain_dbi"))
        station["phg_direction"] = snapshot["data_raw"].get("phg_direction")
        station["phg_range_km"] = _phg_range_km(snapshot["data_raw"])
        station["qsy_frequency_mhz"] = _float_value(snapshot["data_raw"].get("qsy_frequency_mhz"))
        station["qsy_tone"] = _string_or_none(snapshot["data_raw"].get("qsy_tone"))
        station["qsy_offset_khz"] = _integer_value(snapshot["data_raw"].get("qsy_offset_khz"))
        station["qsy_callsign"] = _string_or_none(snapshot["data_raw"].get("qsy_callsign"))
        station["destination"] = snapshot["destination"]
    return stations


def get_map_station_markers_payload(*, since_revision: int | None = None) -> dict[str, Any]:
    state = read_map_station_state(since_revision=since_revision)
    snapshots = state["snapshots"]
    revision = state["revision"]
    stations = _build_map_station_marker_rows(snapshots)
    interfaces = _build_map_interfaces(stations, [])
    return {
        "revision": revision,
        "full_snapshot": state["full_snapshot"],
        "removed_station_keys": state["removed_station_keys"],
        "station_count": len(stations),
        "stations": stations,
        "interfaces": interfaces,
    }


def get_map_alert_areas_payload() -> dict[str, Any]:
    revision, alert_areas = get_active_alert_area_snapshot()
    return {
        "revision": revision,
        "alert_areas": alert_areas,
    }


def get_map_station_details_payload() -> dict[str, Any]:
    station_settings = get_station_settings()
    unit_system = str(station_settings.get("default_units") or "metric")
    state = read_map_station_state()
    snapshots = state["snapshots"]
    revision = state["revision"]
    stations = _build_map_station_detail_rows(snapshots, unit_system=unit_system)
    return {
        "revision": revision,
        "station_count": len(stations),
        "stations": stations,
        "interfaces": _build_map_interfaces(stations, []),
    }


def get_map_mobile_tracks_payload() -> dict[str, Any]:
    state = read_map_station_state()
    snapshots = state["snapshots"]
    revision = state["revision"]
    stations = _build_map_station_marker_rows(snapshots)
    mobile_tracks = _build_mobile_station_tracks(stations)
    return {
        "revision": revision,
        "track_count": len(mobile_tracks),
        "mobile_tracks": mobile_tracks,
        "interfaces": _build_map_interfaces(stations, mobile_tracks),
    }


def get_map_station_payload() -> dict[str, Any]:
    station_settings = get_station_settings()
    unit_system = str(station_settings.get("default_units") or "metric")
    state = read_map_station_state()
    snapshots = state["snapshots"]
    revision = state["revision"]
    stations = _build_map_station_detail_rows(snapshots, unit_system=unit_system)
    mobile_tracks = _build_mobile_station_tracks(stations)
    return {
        "revision": revision,
        "station_count": len(stations),
        "stations": stations,
        "track_count": len(mobile_tracks),
        "mobile_tracks": mobile_tracks,
        "interfaces": _build_map_interfaces(stations, mobile_tracks),
        "alert_areas": get_active_alert_area_feature_collection(),
    }


def get_station_detail_map_config(station: dict[str, Any], *, root_path: str = "") -> dict[str, Any]:
    tile_layer = resolve_active_tile_layer(root_path=root_path)
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
        "symbol_icon": station.get("symbol_icon", get_aprs_symbol_icon_fallback_path()),
        "symbol_table": station.get("symbol_table", ""),
        "symbol_code": station.get("symbol_code", ""),
        "detail_href": station.get("detail_href", ""),
    }


def get_alert_detail_map_config(alert: dict[str, Any], *, root_path: str = "") -> dict[str, Any]:
    tile_layer = resolve_active_tile_layer(root_path=root_path)
    if not str(alert.get("alarm_group") or "").strip():
        parsed = parse_tnc2_frame(str(alert.get("last_frame_line") or ""))
        aprs_data = dict((parsed or {}).get("aprs_data") or {})
        latitude = _parse_coordinate(alert.get("latitude"))
        longitude = _parse_coordinate(alert.get("longitude"))
        if latitude is None:
            latitude = _parse_coordinate(aprs_data.get("latitude"))
        if longitude is None:
            longitude = _parse_coordinate(aprs_data.get("longitude"))

        symbol = str(aprs_data.get("symbol") or "")
        symbol_table = symbol[:1] if len(symbol) >= 2 else ""
        symbol_code = symbol[1:2] if len(symbol) >= 2 else ""
        related_entity = alert.get("related_entity")
        related_label = (
            str(related_entity.get("label") or "").strip()
            if isinstance(related_entity, dict)
            else ""
        )
        return {
            "map_mode": "station",
            "latitude": latitude,
            "longitude": longitude,
            "zoom": DETAIL_STATION_ZOOM,
            "tile_url": tile_layer["tile_url"],
            "tile_attribution": tile_layer["tile_attribution"],
            "tile_source_name": tile_layer["tile_source_name"],
            "tile_min_zoom": tile_layer["tile_min_zoom"],
            "tile_max_zoom": tile_layer["tile_max_zoom"],
            "tile_subdomains": tile_layer["tile_subdomains"],
            "display_callsign": related_label or str(alert.get("source_callsign") or "").strip(),
            "symbol_icon": (
                get_aprs_symbol_icon_path(symbol)
                if len(symbol) >= 2
                else get_aprs_symbol_icon_fallback_path()
            ),
            "symbol_table": symbol_table,
            "symbol_code": symbol_code,
            "track_points": [],
            "has_position": latitude is not None and longitude is not None,
        }

    feature_collection = build_alert_area_feature_collection([alert])
    return {
        "map_mode": "areas",
        "tile_url": tile_layer["tile_url"],
        "tile_attribution": tile_layer["tile_attribution"],
        "tile_source_name": tile_layer["tile_source_name"],
        "tile_min_zoom": tile_layer["tile_min_zoom"],
        "tile_max_zoom": tile_layer["tile_max_zoom"],
        "tile_subdomains": tile_layer["tile_subdomains"],
        "feature_collection": feature_collection,
        "has_area_definitions": bool(feature_collection["features"]),
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


def _normalize_interface_id(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _build_map_interfaces(stations: list[dict[str, Any]], mobile_tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interface_ids: set[int] = set()
    for station in stations:
        interface_id = _normalize_interface_id(station.get("interface_id"))
        if interface_id is not None:
            interface_ids.add(interface_id)
    for track in mobile_tracks:
        for point in track.get("points") or []:
            interface_id = _normalize_interface_id(point.get("interface_id"))
            if interface_id is not None:
                interface_ids.add(interface_id)

    if not interface_ids:
        return []

    configured_modems = get_configured_modem_interfaces()
    modem_by_id: dict[int, dict[str, Any]] = {}
    for row in configured_modems:
        modem_id = _normalize_interface_id(row.get("id"))
        if modem_id is None:
            continue
        modem_by_id[modem_id] = row

    interfaces: list[dict[str, Any]] = []
    for interface_id in sorted(interface_ids):
        modem = modem_by_id.get(interface_id)
        interfaces.append(
            {
                "modem_id": interface_id,
                "name": (
                    str(modem.get("name") or "").strip()
                    if modem is not None
                    else f"#{interface_id}"
                ),
                "band": str((modem or {}).get("band") or "").strip(),
                "enabled": bool((modem or {}).get("enabled", 1)),
            }
        )
    return interfaces


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


def _limit_mobile_track_points_by_interface(
    points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kept_reversed: list[dict[str, Any]] = []
    counts_by_interface: dict[int | None, int] = {}
    for point in reversed(points):
        interface_id = _normalize_interface_id(point.get("interface_id"))
        interface_count = counts_by_interface.get(interface_id, 0)
        if interface_count >= MOBILE_TRACK_MAX_POINTS_PER_STATION:
            continue
        counts_by_interface[interface_id] = interface_count + 1
        kept_reversed.append(point)
    kept_reversed.reverse()
    return kept_reversed


def _build_mobile_track_points_by_station_keys(
    station_keys: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    if not station_keys:
        return {}

    rows = fetch_all(
        """
        SELECT line, interface_id, created_at
        FROM (
            SELECT line, interface_id, created_at, id
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
    last_point_by_station_interface: dict[tuple[str, int | None], dict[str, Any]] = {}
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

        interface_id = _normalize_interface_id(row["interface_id"])
        points = points_by_station.setdefault(resolved_key, [])
        interface_point_key = (resolved_key.casefold(), interface_id)
        previous_interface_point = last_point_by_station_interface.get(interface_point_key)
        if previous_interface_point and _is_same_track_position(previous_interface_point, latitude, longitude):
            continue
        point = {
            "latitude": latitude,
            "longitude": longitude,
            "interface_id": interface_id,
            "heard_at": str(row["created_at"] or ""),
        }
        points.append(point)
        last_point_by_station_interface[interface_point_key] = point
    return {
        station_key: _limit_mobile_track_points_by_interface(points)
        for station_key, points in points_by_station.items()
    }
