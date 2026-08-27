from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from app.db import fetch_all, fetch_one, get_app_setting, get_connection, log_event, set_app_setting, utc_now
from app.services.content import get_active_tnc_interfaces, get_station_settings
from app.services.outbound import build_wx_tnc2, enqueue_wx_job
from app.services.tx_scope import (
    ALL_ACTIVE_INTERFACE_OPTION_VALUE,
    TX_SCOPE_ALL_ACTIVE,
    TX_SCOPE_SINGLE,
    normalize_tx_scope,
)
from app.services.wx_definitions import (
    WX_AUTH_TYPES,
    WX_PARAMETER_DEFINITIONS,
    WX_SELECTOR_KINDS,
    WX_SOURCE_TYPES,
    get_wx_parameter_definition,
)
from app.services.wx_sources import WxSourceError, build_wx_source_adapter, parse_value_selector


WX_REFRESH_LAST_AT_KEY = "scheduler.wx.last_refresh_at"
WX_REFRESH_LAST_ERROR_KEY = "scheduler.wx.last_refresh_error"
WX_INTERVAL_OPTIONS_DIRECT_MINUTES = (5, 10, 15, 30, 45, 60)
WX_INTERVAL_OPTIONS_ROUTED_MINUTES = (15, 39, 45, 60)


class WxValidationError(ValueError):
    pass


class WxMissingValueError(WxValidationError):
    pass


def ensure_wx_defaults() -> None:
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO wx_config(
                id, enabled, callsign, ssid, refresh_interval_s,
                allow_cache_fallback, default_cache_max_age_s, created_at, updated_at
            )
            VALUES (1, 0, '', '', 300, 1, 900, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (timestamp, timestamp),
        )
        for definition in WX_PARAMETER_DEFINITIONS:
            connection.execute(
                """
                INSERT INTO wx_mappings(
                    parameter_name, required_flag, source_id, identifier, value_selector,
                    transform_config_json, cache_max_age_s, enabled, created_at, updated_at
                )
                VALUES (?, ?, NULL, '', '', '{}', NULL, 0, ?, ?)
                ON CONFLICT(parameter_name) DO NOTHING
                """,
                (definition.name, 1 if definition.required else 0, timestamp, timestamp),
            )


def get_wx_page_data(*, edit_source_id: int | None = None, source_discovery: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_wx_defaults()
    config = get_wx_config()
    mappings = get_wx_mapping_rows()
    sources = list_wx_sources()
    source_form = _build_source_form(get_wx_source(edit_source_id) if edit_source_id is not None else None)
    return {
        "wx_config": config,
        "wx_refresh_interval_options": _build_wx_refresh_interval_options(
            path=str(config.get("path") or ""),
            selected_interval_s=int(config.get("refresh_interval_s") or 300),
        ),
        "wx_refresh_interval_options_direct": _interval_options_from_minutes(WX_INTERVAL_OPTIONS_DIRECT_MINUTES),
        "wx_refresh_interval_options_routed": _interval_options_from_minutes(WX_INTERVAL_OPTIONS_ROUTED_MINUTES),
        "wx_required_mappings": [row for row in mappings if row["required_flag"]],
        "wx_optional_mappings": [row for row in mappings if not row["required_flag"]],
        "wx_sources": sources,
        "wx_source_form": source_form,
        "wx_tx_log_rows": list_recent_sent_wx_frames(limit=20),
        "wx_source_type_options": [
            {"value": "home_assistant", "label": "Home Assistant"},
            {"value": "domoticz", "label": "Domoticz"},
        ],
        "wx_auth_type_options": [
            {"value": "none", "label": "None"},
            {"value": "bearer", "label": "Bearer token"},
            {"value": "basic", "label": "Basic auth"},
        ],
        "wx_selector_kind_options": [
            {"value": "state", "label": "state"},
            {"value": "attribute", "label": "attribute"},
            {"value": "field", "label": "field"},
            {"value": "key", "label": "key"},
        ],
        "wx_source_discovery": source_discovery,
        "wx_has_sources": bool(sources),
    }


def get_wx_config(*, station_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    # The schema initializer creates wx_config. A read must not open a write
    # transaction merely to repair defaults, especially on the dashboard path.
    resolved_station_settings = station_settings or get_station_settings()
    row = fetch_one("SELECT * FROM wx_config WHERE id = 1")
    result = dict(row) if row else {}
    callsign = str(resolved_station_settings.get("callsign") or "").strip().upper()
    result["callsign"] = callsign
    result.setdefault("ssid", "")
    result.setdefault("beacon_interface_id", None)
    result["beacon_tx_scope"] = normalize_tx_scope(result.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE)
    result.setdefault("path", "")
    result.setdefault("latitude", "")
    result.setdefault("longitude", "")
    result.setdefault("enabled", 0)
    result.setdefault("refresh_interval_s", 300)
    result.setdefault("allow_cache_fallback", 1)
    result.setdefault("default_cache_max_age_s", 900)
    result["full_callsign"] = _format_callsign(callsign, str(result.get("ssid") or "").strip())
    result["ssid_options"] = build_wx_ssid_options(
        selected_ssid=str(result.get("ssid") or "").strip(),
        station_settings=resolved_station_settings,
    )
    return result


def build_wx_ssid_options(
    *,
    selected_ssid: str = "",
    station_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    occupied = get_wx_occupied_ssids(station_settings=station_settings)
    options: list[dict[str, Any]] = [{"value": "", "label": "Select SSID", "disabled": False, "reason": ""}]
    for value in range(16):
        text = str(value)
        reason = occupied.get(text, "")
        disabled = bool(reason) and text != selected_ssid
        options.append(
            {
                "value": text,
                "label": text,
                "disabled": disabled,
                "reason": reason,
            }
        )
    return options


def get_wx_occupied_ssids(*, station_settings: dict[str, Any] | None = None) -> dict[str, str]:
    resolved_station_settings = station_settings or get_station_settings()
    occupied: dict[str, str] = {}
    station_ssid = str(resolved_station_settings.get("ssid") or "").strip()
    if station_ssid:
        occupied[station_ssid] = "Used by My Settings"
    return occupied


def save_wx_config(payload: dict[str, Any]) -> None:
    ensure_wx_defaults()
    normalized = _normalize_wx_config_payload(payload)
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE wx_config
            SET enabled = :enabled,
                callsign = :callsign,
                ssid = :ssid,
                beacon_interface_id = :beacon_interface_id,
                beacon_tx_scope = :beacon_tx_scope,
                path = :path,
                latitude = :latitude,
                longitude = :longitude,
                refresh_interval_s = :refresh_interval_s,
                allow_cache_fallback = :allow_cache_fallback,
                default_cache_max_age_s = :default_cache_max_age_s,
                updated_at = :updated_at
            WHERE id = 1
            """,
            normalized,
        )
    log_event(
        "INFO",
        "wx",
        f"Updated WX configuration (enabled={normalized['enabled']}, ssid={normalized['ssid']!r}, refresh_interval_s={normalized['refresh_interval_s']})",
    )


def safe_save_wx_config(payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        save_wx_config(payload)
    except WxValidationError as exc:
        return False, str(exc)
    return True, None


def list_wx_sources() -> list[dict[str, Any]]:
    ensure_wx_defaults()
    rows = fetch_all(
        """
        SELECT *
        FROM wx_sources
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    return [_serialize_wx_source_row(dict(row)) for row in rows]


def get_wx_source(source_id: int | None) -> dict[str, Any] | None:
    if source_id is None:
        return None
    row = fetch_one("SELECT * FROM wx_sources WHERE id = ?", (source_id,))
    if row is None:
        return None
    return _serialize_wx_source_row(dict(row))


def save_wx_source(payload: dict[str, Any], *, source_id: int | None = None) -> int:
    normalized = _normalize_wx_source_payload(payload)
    timestamp = utc_now()
    if source_id is None:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO wx_sources(
                    name, source_type, base_url, auth_type, auth_payload,
                    timeout_s, verify_tls, enabled, last_test_status,
                    last_test_error, last_test_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', NULL, ?, ?)
                """,
                (
                    normalized["name"],
                    normalized["source_type"],
                    normalized["base_url"],
                    normalized["auth_type"],
                    normalized["auth_payload_json"],
                    normalized["timeout_s"],
                    normalized["verify_tls"],
                    normalized["enabled"],
                    timestamp,
                    timestamp,
                ),
            )
            new_id = int(cursor.lastrowid)
        log_event("INFO", "wx", f"Created WX source {normalized['name']}")
        return new_id

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE wx_sources
            SET name = :name,
                source_type = :source_type,
                base_url = :base_url,
                auth_type = :auth_type,
                auth_payload = :auth_payload_json,
                timeout_s = :timeout_s,
                verify_tls = :verify_tls,
                enabled = :enabled,
                updated_at = :updated_at
            WHERE id = :id
            """,
            {**normalized, "id": source_id, "updated_at": timestamp},
        )
    log_event("INFO", "wx", f"Updated WX source {source_id}")
    return source_id


def safe_save_wx_source(payload: dict[str, Any], *, source_id: int | None = None) -> tuple[bool, str | None, int | None]:
    try:
        saved_id = save_wx_source(payload, source_id=source_id)
    except WxValidationError as exc:
        return False, str(exc), source_id
    except sqlite3.IntegrityError as exc:
        return False, str(exc), source_id
    return True, None, saved_id


def delete_wx_source(source_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM wx_sources WHERE id = ?", (source_id,))
    log_event("INFO", "wx", f"Deleted WX source {source_id}")


def test_wx_source_connection(source_id: int) -> dict[str, Any]:
    source = get_wx_source(source_id)
    if source is None:
        return {"ok": False, "error": "WX source not found."}
    timestamp = utc_now()
    try:
        result = build_wx_source_adapter(source).test_connection()
        ok = bool(result.get("ok"))
        if ok:
            error = ""
        else:
            details = result.get("details")
            detail_error = ""
            if isinstance(details, dict):
                for key in ("message", "error", "title"):
                    candidate = str(details.get(key) or "").strip()
                    if candidate:
                        detail_error = candidate
                        break
                if not detail_error:
                    status_text = str(details.get("status") or "").strip()
                    if status_text and status_text.upper() != "OK":
                        detail_error = f"Source status: {status_text}"
            error = detail_error or "Connection test failed."
    except WxSourceError as exc:
        ok = False
        error = str(exc)
        result = {"details": {}}
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE wx_sources
            SET last_test_status = ?,
                last_test_error = ?,
                last_test_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            ("ok" if ok else "error", error, timestamp, timestamp, source_id),
        )
    if ok:
        log_event("INFO", "wx", f"WX source {source['name']} connection test succeeded")
        return {"ok": True, "details": result.get("details", {})}
    log_event("WARNING", "wx", f"WX source {source['name']} connection test failed: {error}")
    return {"ok": False, "error": error, "details": result.get("details", {})}


def discover_wx_source_items(source_id: int) -> dict[str, Any]:
    source = get_wx_source(source_id)
    if source is None:
        return {"ok": False, "error": "WX source not found."}
    try:
        items = build_wx_source_adapter(source).discover_items()
    except WxSourceError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "items": items, "source": source}


def save_wx_mappings(payload_by_parameter: dict[str, dict[str, Any]]) -> None:
    ensure_wx_defaults()
    timestamp = utc_now()
    source_ids = {int(row["id"]) for row in fetch_all("SELECT id FROM wx_sources")}
    normalized_rows: list[dict[str, Any]] = []
    for definition in WX_PARAMETER_DEFINITIONS:
        raw_payload = payload_by_parameter.get(definition.name, {})
        normalized_rows.append(_normalize_wx_mapping_payload(definition.name, raw_payload, available_source_ids=source_ids))
    with get_connection() as connection:
        for row in normalized_rows:
            connection.execute(
                """
                UPDATE wx_mappings
                SET source_id = :source_id,
                    identifier = :identifier,
                    value_selector = :value_selector,
                    transform_config_json = :transform_config_json,
                    cache_max_age_s = :cache_max_age_s,
                    enabled = :enabled,
                    updated_at = :updated_at
                WHERE parameter_name = :parameter_name
                """,
                {**row, "updated_at": timestamp},
            )
    log_event("INFO", "wx", "Updated WX mapping rows")


def safe_save_wx_mappings(payload_by_parameter: dict[str, dict[str, Any]]) -> tuple[bool, str | None]:
    try:
        save_wx_mappings(payload_by_parameter)
    except WxValidationError as exc:
        return False, str(exc)
    return True, None


def get_wx_mapping_rows() -> list[dict[str, Any]]:
    ensure_wx_defaults()
    source_rows = list_wx_sources()
    sources_by_id = {int(item["id"]): item for item in source_rows}
    cache_rows = {
        str(row["parameter_name"]): dict(row)
        for row in fetch_all(
            """
            SELECT *
            FROM wx_runtime_cache
            ORDER BY parameter_name ASC
            """
        )
    }
    rows = fetch_all(
        """
        SELECT *
        FROM wx_mappings
        ORDER BY id ASC, parameter_name ASC
        """
    )
    mapping_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        definition = get_wx_parameter_definition(str(item["parameter_name"]))
        transform_config = _parse_json_object(item.get("transform_config_json"))
        selector_kind, selector_name = _split_selector_parts(str(item.get("value_selector") or ""))
        cache_row = cache_rows.get(definition.name)
        source_id = int(item["source_id"]) if item["source_id"] is not None else None
        cache_status = str((cache_row or {}).get("status") or "MISSING").upper()
        mapping_rows.append(
            {
                **item,
                "label": definition.label,
                "aprs_field": definition.aprs_field,
                "canonical_unit": definition.canonical_unit,
                "description": definition.description,
                "required_flag": bool(item.get("required_flag")),
                "source_id": source_id,
                "source": sources_by_id.get(source_id),
                "selector_kind": selector_kind,
                "selector_name": selector_name,
                "unit_override": str(transform_config.get("unit_override") or "").strip(),
                "source_options": [{"value": "", "label": "Select source"}]
                + [
                    {
                        "value": str(source["id"]),
                        "label": f"{source['name']} ({source['source_type_label']})" + (" [disabled]" if not source.get("enabled") else ""),
                    }
                    for source in source_rows
                ],
                "raw_value_preview": (cache_row or {}).get("raw_value") or "-",
                "normalized_value_preview": _format_normalized_preview(cache_row),
                "status": cache_status,
                "status_class": _status_class(cache_status),
                "status_label": cache_status.title(),
                "cache_origin_label": str((cache_row or {}).get("value_origin") or "").upper() or "-",
                "cache_last_success_at": (cache_row or {}).get("last_success_at"),
                "cache_last_attempt_at": (cache_row or {}).get("last_attempt_at"),
                "cache_last_success_at_label": _format_human_timestamp((cache_row or {}).get("last_success_at")),
                "cache_last_attempt_at_label": _format_human_timestamp((cache_row or {}).get("last_attempt_at")),
                "cache_info": _format_cache_info(cache_row),
                "cache_last_error": (cache_row or {}).get("last_error") or "",
            }
        )
    return mapping_rows


def refresh_wx_runtime(*, trigger: str = "manual", only_parameters: set[str] | None = None) -> dict[str, Any]:
    ensure_wx_defaults()
    config = get_wx_config()
    now = utc_now()
    rows = fetch_all(
        """
        SELECT *
        FROM wx_mappings
        ORDER BY id ASC, parameter_name ASC
        """
    )
    sources_by_id = {int(source["id"]): source for source in list_wx_sources()}
    cache_rows = {
        str(row["parameter_name"]): dict(row)
        for row in fetch_all("SELECT * FROM wx_runtime_cache ORDER BY parameter_name ASC")
    }
    refreshed: list[dict[str, Any]] = []
    for row in rows:
        parameter_name = str(row["parameter_name"])
        if only_parameters is not None and parameter_name not in only_parameters:
            continue
        refreshed.append(
            _refresh_wx_mapping_row(
                dict(row),
                source=sources_by_id.get(int(row["source_id"])) if row["source_id"] is not None else None,
                existing_cache=cache_rows.get(parameter_name),
                config=config,
                attempted_at=now,
            )
        )
    if only_parameters is None:
        set_app_setting(WX_REFRESH_LAST_AT_KEY, now)
        set_app_setting(WX_REFRESH_LAST_ERROR_KEY, "")
    diagnostics = build_wx_diagnostics(config=config)
    log_event("INFO", "wx", f"WX refresh finished ({trigger})")
    return {"ok": True, "rows": refreshed, "diagnostics": diagnostics, "refreshed_at": now}


def safe_refresh_wx_runtime(*, trigger: str = "manual", only_parameters: set[str] | None = None) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        result = refresh_wx_runtime(trigger=trigger, only_parameters=only_parameters)
    except WxValidationError as exc:
        return False, None, str(exc)
    except WxSourceError as exc:
        return False, None, str(exc)
    return True, result, None


def refresh_single_wx_mapping(parameter_name: str, *, trigger: str = "manual-test") -> dict[str, Any]:
    normalized = str(parameter_name or "").strip()
    if normalized not in {item.name for item in WX_PARAMETER_DEFINITIONS}:
        raise WxValidationError("Unsupported WX parameter.")
    return refresh_wx_runtime(trigger=trigger, only_parameters={normalized})


def build_wx_outbound_payload(*, mapping_rows: list[dict[str, Any]] | None = None, config: dict[str, Any] | None = None, trigger: str = "scheduled") -> dict[str, Any]:
    resolved_config = config or get_wx_config()
    rows = mapping_rows or get_wx_mapping_rows()
    encoder_input = build_wx_encoder_input(mapping_rows=rows, config=resolved_config)
    if not bool(resolved_config.get("enabled")):
        raise WxValidationError("WX is disabled.")
    if not str(resolved_config.get("callsign") or "").strip():
        raise WxValidationError("My Settings callsign is required before sending WX.")
    if not str(resolved_config.get("ssid") or "").strip():
        raise WxValidationError("WX SSID is required before sending WX.")
    beacon_tx_scope = normalize_tx_scope(resolved_config.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE)
    beacon_interface_id = resolved_config.get("beacon_interface_id")
    interface_ids: list[int] | None = None
    if beacon_tx_scope == TX_SCOPE_ALL_ACTIVE:
        interface_ids = []
        for interface in get_active_tnc_interfaces():
            try:
                interface_ids.append(int(interface["id"]))
            except (TypeError, ValueError):
                continue
        if not interface_ids:
            raise WxValidationError("At least one active RF interface is required before sending WX.")
    elif beacon_interface_id in {None, ""}:
        raise WxValidationError("WX interface is required before sending WX.")
    latitude = str(resolved_config.get("latitude") or "").strip()
    longitude = str(resolved_config.get("longitude") or "").strip()
    if not latitude or not longitude:
        raise WxValidationError("WX latitude and longitude are required before sending WX.")

    weather: dict[str, float] = {}
    for field in encoder_input["fields"]:
        if field["status"] not in {"LIVE", "CACHED"} or field["value"] is None:
            continue
        weather[str(field["name"])] = float(field["value"])

    payload: dict[str, Any] = {
        "callsign": str(resolved_config.get("callsign") or "").strip().upper(),
        "ssid": str(resolved_config.get("ssid") or "").strip(),
        "tx_scope": beacon_tx_scope,
        "path": str(resolved_config.get("path") or "").strip(),
        "latitude": latitude,
        "longitude": longitude,
        "weather": weather,
        "trigger": str(trigger or "scheduled").strip() or "scheduled",
        "generated_at": utc_now(),
    }
    if beacon_tx_scope == TX_SCOPE_ALL_ACTIVE:
        payload["interface_ids"] = interface_ids or []
    else:
        payload["interface_id"] = int(beacon_interface_id)
    return payload


def safe_enqueue_wx_outbound(*, trigger: str = "scheduled") -> tuple[bool, str]:
    try:
        payload = build_wx_outbound_payload(trigger=trigger)
    except WxValidationError as exc:
        return False, str(exc)
    return enqueue_wx_job(payload)


def list_recent_sent_wx_frames(limit: int = 10) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT j.id, j.status, j.scheduled_at, j.started_at, j.sent_at, j.attempt_count, j.last_error,
               j.kind, m.name AS interface_name, j.payload_json
        FROM outbound_jobs j
        LEFT JOIN modems m ON m.id = j.interface_id
        WHERE j.kind = 'wx'
        ORDER BY COALESCE(j.sent_at, j.started_at, j.scheduled_at, j.created_at) DESC, j.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload = _parse_json_object(item.pop("payload_json", "") or "{}")
        if payload:
            try:
                item["line"] = build_wx_tnc2(payload)
            except Exception:
                item["line"] = ""
        else:
            item["line"] = ""
        item["interface_name"] = item.get("interface_name") or "Unknown interface"
        skip_reason = str(item.get("last_error") or "").strip()
        item["is_tx_skipped"] = bool(skip_reason) and skip_reason.startswith("TX skipped:")
        display_time = item.get("sent_at") or item.get("started_at") or item.get("scheduled_at") or ""
        item["display_time"] = display_time
        item["display_time_label"] = _format_human_timestamp(display_time)
        result.append(item)
    return result


def build_wx_diagnostics(*, mapping_rows: list[dict[str, Any]] | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_config = config or get_wx_config()
    resolved_rows = mapping_rows or get_wx_mapping_rows()
    live_count = sum(1 for row in resolved_rows if row["status"] == "LIVE")
    cached_count = sum(1 for row in resolved_rows if row["status"] == "CACHED")
    invalid_count = sum(1 for row in resolved_rows if row["status"] in {"STALE", "MISSING", "ERROR"})
    encoder_input = build_wx_encoder_input(mapping_rows=resolved_rows, config=resolved_config)
    last_refresh_at = get_app_setting(WX_REFRESH_LAST_AT_KEY)
    if not last_refresh_at:
        last_refresh_at = max((str(row.get("cache_last_attempt_at") or "") for row in resolved_rows), default="") or None
    return {
        "last_refresh_at": last_refresh_at,
        "last_refresh_at_label": _format_human_timestamp(last_refresh_at),
        "live_count": live_count,
        "cached_count": cached_count,
        "invalid_count": invalid_count,
        "encoder_input": encoder_input,
        "preview_json": json.dumps(encoder_input, indent=2, ensure_ascii=True),
    }


def build_wx_encoder_input(*, mapping_rows: list[dict[str, Any]] | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved_config = config or get_wx_config()
    rows = mapping_rows or get_wx_mapping_rows()
    weather_fields: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for row in rows:
        normalized_value = _parse_normalized_numeric_value(row.get("normalized_value_preview"))
        is_ready = row["status"] in {"LIVE", "CACHED"} and normalized_value is not None
        if row["required_flag"] and not is_ready:
            missing_required.append(str(row["parameter_name"]))
        weather_fields.append(
            {
                "name": row["parameter_name"],
                "label": row["label"],
                "aprs_field": row["aprs_field"],
                "required": row["required_flag"],
                "value": normalized_value,
                "unit": row["canonical_unit"],
                "status": row["status"],
                "origin": row["cache_origin_label"],
                "last_success_at": row["cache_last_success_at"],
            }
        )
    return {
        "ready_for_encode": bool(resolved_config.get("enabled")) and bool(resolved_config.get("callsign")) and bool(resolved_config.get("ssid")),
        "enabled": bool(resolved_config.get("enabled")),
        "callsign": resolved_config.get("callsign") or "",
        "ssid": resolved_config.get("ssid") or "",
        "full_callsign": resolved_config.get("full_callsign") or "",
        "missing_required": missing_required,
        "fields": weather_fields,
    }


def _normalize_wx_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    station_settings = get_station_settings()
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    enabled = int(bool(payload.get("enabled")))
    ssid = str(payload.get("ssid") or "").strip()
    beacon_tx_scope = normalize_tx_scope(payload.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE)
    raw_beacon_interface = str(payload.get("beacon_interface_id") or "").strip()
    if raw_beacon_interface == ALL_ACTIVE_INTERFACE_OPTION_VALUE:
        beacon_tx_scope = TX_SCOPE_ALL_ACTIVE
        raw_beacon_interface = ""
    try:
        beacon_interface_id = int(raw_beacon_interface) if raw_beacon_interface else None
    except (TypeError, ValueError):
        beacon_interface_id = None
    if beacon_interface_id is not None and beacon_tx_scope == TX_SCOPE_SINGLE:
        interface_exists = fetch_one("SELECT id FROM modems WHERE id = ?", (beacon_interface_id,))
        if interface_exists is None:
            beacon_interface_id = None
    if beacon_tx_scope == TX_SCOPE_ALL_ACTIVE:
        beacon_interface_id = None
    path = _normalize_printable_ascii(str(payload.get("path") or "").strip().upper())
    if len(path) > 64:
        raise WxValidationError("WX path must be 64 printable ASCII characters or fewer.")
    latitude = str(payload.get("latitude") or "").strip()
    longitude = str(payload.get("longitude") or "").strip()
    if bool(latitude) != bool(longitude):
        raise WxValidationError("WX location requires both latitude and longitude, or neither.")
    if latitude:
        _validate_coordinate(latitude, minimum=-90.0, maximum=90.0, label="WX latitude")
        _validate_coordinate(longitude, minimum=-180.0, maximum=180.0, label="WX longitude")
    refresh_interval_s = _normalize_positive_int(payload.get("refresh_interval_s"), default=300, minimum=15, maximum=3600, label="Refresh interval")
    allowed_minutes = _allowed_wx_refresh_interval_minutes(path)
    allowed_seconds = {minutes * 60 for minutes in allowed_minutes}
    if refresh_interval_s not in allowed_seconds:
        allowed_labels = ", ".join(f"{minutes}m" for minutes in allowed_minutes)
        raise WxValidationError(f"Refresh interval for this path must be one of: {allowed_labels}.")
    default_cache_max_age_s = _normalize_positive_int(
        payload.get("default_cache_max_age_s"),
        default=900,
        minimum=1,
        maximum=86400,
        label="Default max cache age",
    )
    allow_cache_fallback = int(bool(payload.get("allow_cache_fallback")))
    if enabled and not callsign:
        raise WxValidationError("My Settings callsign is required before enabling WX.")
    if enabled and not ssid:
        raise WxValidationError("WX SSID is required when WX is enabled.")
    if enabled and beacon_tx_scope == TX_SCOPE_SINGLE and beacon_interface_id is None:
        raise WxValidationError("WX interface is required when WX is enabled.")
    if enabled and beacon_tx_scope == TX_SCOPE_ALL_ACTIVE and not get_active_tnc_interfaces():
        raise WxValidationError("At least one active RF interface is required when WX is enabled.")
    if enabled and (not latitude or not longitude):
        raise WxValidationError("WX latitude and longitude are required when WX is enabled.")
    if ssid and (not ssid.isdigit() or int(ssid) < 0 or int(ssid) > 15):
        raise WxValidationError("WX SSID must be between 0 and 15.")
    occupied_reason = get_wx_occupied_ssids().get(ssid)
    if enabled and occupied_reason:
        raise WxValidationError(f"WX SSID {ssid} is not available: {occupied_reason}.")
    return {
        "enabled": enabled,
        "callsign": callsign,
        "ssid": ssid,
        "beacon_interface_id": beacon_interface_id,
        "beacon_tx_scope": beacon_tx_scope,
        "path": path,
        "latitude": latitude,
        "longitude": longitude,
        "refresh_interval_s": refresh_interval_s,
        "allow_cache_fallback": allow_cache_fallback,
        "default_cache_max_age_s": default_cache_max_age_s,
        "updated_at": utc_now(),
    }


def _is_direct_wx_path(path: str) -> bool:
    normalized = str(path or "").strip().upper()
    return normalized in {"", "RFONLY"}


def _allowed_wx_refresh_interval_minutes(path: str) -> tuple[int, ...]:
    if _is_direct_wx_path(path):
        return WX_INTERVAL_OPTIONS_DIRECT_MINUTES
    return WX_INTERVAL_OPTIONS_ROUTED_MINUTES


def _interval_options_from_minutes(minutes_list: tuple[int, ...]) -> list[dict[str, Any]]:
    return [{"value": minutes * 60, "label": f"{minutes}m"} for minutes in minutes_list]


def _build_wx_refresh_interval_options(*, path: str, selected_interval_s: int) -> list[dict[str, Any]]:
    allowed_minutes = _allowed_wx_refresh_interval_minutes(path)
    options = _interval_options_from_minutes(allowed_minutes)
    allowed_seconds = {minutes * 60 for minutes in allowed_minutes}
    if selected_interval_s not in allowed_seconds and selected_interval_s > 0:
        minutes_float = selected_interval_s / 60
        if float(minutes_float).is_integer():
            label = f"{int(minutes_float)}m (current)"
        else:
            label = f"{minutes_float:.2f}m (current)"
        options.insert(0, {"value": selected_interval_s, "label": label})
    return options


def _normalize_wx_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise WxValidationError("WX source name is required.")
    source_type = str(payload.get("source_type") or "").strip().lower()
    if source_type not in WX_SOURCE_TYPES:
        raise WxValidationError("Unsupported WX source type.")
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    parsed_url = urlsplit(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise WxValidationError("Base URL must be a valid HTTP or HTTPS URL.")
    auth_type = str(payload.get("auth_type") or "none").strip().lower()
    if auth_type not in WX_AUTH_TYPES:
        raise WxValidationError("Unsupported WX auth type.")
    if source_type == "home_assistant" and auth_type != "bearer":
        raise WxValidationError("Home Assistant requires Bearer token authentication.")
    if source_type == "domoticz" and auth_type not in {"none", "basic"}:
        raise WxValidationError("Domoticz supports no auth or Basic auth.")
    token = str(payload.get("token") or "").strip()
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    if auth_type == "bearer" and not token:
        raise WxValidationError("Bearer token is required.")
    if auth_type == "basic" and not username:
        raise WxValidationError("Basic auth username is required.")
    timeout_s = _normalize_positive_int(payload.get("timeout_s"), default=5, minimum=1, maximum=60, label="Timeout")
    return {
        "name": name,
        "source_type": source_type,
        "base_url": base_url,
        "auth_type": auth_type,
        "auth_payload_json": json.dumps(
            {
                "token": token if auth_type == "bearer" else "",
                "username": username if auth_type == "basic" else "",
                "password": password if auth_type == "basic" else "",
            },
            separators=(",", ":"),
        ),
        "timeout_s": timeout_s,
        "verify_tls": 1 if payload.get("verify_tls") else 0,
        "enabled": 1 if payload.get("enabled") else 0,
    }


def _normalize_wx_mapping_payload(parameter_name: str, payload: dict[str, Any], *, available_source_ids: set[int]) -> dict[str, Any]:
    source_value = str(payload.get("source_id") or "").strip()
    identifier = str(payload.get("identifier") or "").strip()
    selector_kind = str(payload.get("selector_kind") or "state").strip().lower()
    selector_name = str(payload.get("selector_name") or "").strip()
    if selector_kind not in WX_SELECTOR_KINDS:
        raise WxValidationError(f"Unsupported selector kind for {parameter_name}.")
    if source_value and not identifier:
        raise WxValidationError(f"Identifier is required for {parameter_name}.")
    if identifier and not source_value:
        raise WxValidationError(f"Source is required for {parameter_name}.")
    source_id = None
    if source_value:
        try:
            source_id = int(source_value)
        except ValueError as exc:
            raise WxValidationError(f"Invalid source for {parameter_name}.") from exc
        if source_id not in available_source_ids:
            raise WxValidationError(f"Selected source for {parameter_name} does not exist.")
    selector_value = selector_kind if not selector_name else f"{selector_kind}:{selector_name}"
    try:
        parse_value_selector(selector_value)
    except WxSourceError as exc:
        raise WxValidationError(str(exc)) from exc
    cache_max_age_raw = str(payload.get("cache_max_age_s") or "").strip()
    cache_max_age_s = None
    if cache_max_age_raw:
        cache_max_age_s = _normalize_positive_int(
            cache_max_age_raw,
            default=900,
            minimum=1,
            maximum=86400,
            label=f"Cache max age for {parameter_name}",
        )
    unit_override = str(payload.get("unit_override") or "").strip()
    return {
        "parameter_name": parameter_name,
        "source_id": source_id,
        "identifier": identifier,
        "value_selector": selector_value if source_id is not None else "",
        "transform_config_json": json.dumps({"unit_override": unit_override}, separators=(",", ":")),
        "cache_max_age_s": cache_max_age_s,
        "enabled": 1 if source_id is not None and identifier else 0,
    }


def _assert_required_wx_mappings_complete() -> None:
    rows = fetch_all(
        """
        SELECT parameter_name, source_id, identifier
        FROM wx_mappings
        WHERE required_flag = 1
        ORDER BY id ASC
        """
    )
    missing = [str(row["parameter_name"]) for row in rows if row["source_id"] is None or not str(row["identifier"] or "").strip()]
    if missing:
        raise WxValidationError(f"Required WX mappings are incomplete: {', '.join(missing)}.")


def _serialize_wx_source_row(row: dict[str, Any]) -> dict[str, Any]:
    auth_payload = _parse_json_object(row.get("auth_payload"))
    source_type = str(row.get("source_type") or "").strip().lower()
    result = dict(row)
    result["auth_payload"] = auth_payload
    result["source_type_label"] = "Home Assistant" if source_type == "home_assistant" else "Domoticz"
    result["token"] = str(auth_payload.get("token") or "")
    result["username"] = str(auth_payload.get("username") or "")
    result["password"] = str(auth_payload.get("password") or "")
    result["last_test_status"] = str(result.get("last_test_status") or "").strip().lower()
    result["last_test_status_label"] = "OK" if result["last_test_status"] == "ok" else ("Error" if result["last_test_status"] == "error" else "-")
    result["last_test_status_class"] = _status_class("LIVE" if result["last_test_status"] == "ok" else ("ERROR" if result["last_test_status"] == "error" else "MISSING"))
    return result


def _build_source_form(source: dict[str, Any] | None) -> dict[str, Any]:
    if source is None:
        return {
            "id": None,
            "name": "",
            "source_type": "home_assistant",
            "base_url": "",
            "auth_type": "bearer",
            "token": "",
            "username": "",
            "password": "",
            "timeout_s": 5,
            "verify_tls": 1,
            "enabled": 1,
        }
    return {
        "id": source.get("id"),
        "name": source.get("name") or "",
        "source_type": source.get("source_type") or "home_assistant",
        "base_url": source.get("base_url") or "",
        "auth_type": source.get("auth_type") or "none",
        "token": source.get("token") or "",
        "username": source.get("username") or "",
        "password": source.get("password") or "",
        "timeout_s": int(source.get("timeout_s") or 5),
        "verify_tls": int(bool(source.get("verify_tls", 1))),
        "enabled": int(bool(source.get("enabled", 1))),
    }


def _refresh_wx_mapping_row(
    mapping_row: dict[str, Any],
    *,
    source: dict[str, Any] | None,
    existing_cache: dict[str, Any] | None,
    config: dict[str, Any],
    attempted_at: str,
) -> dict[str, Any]:
    parameter_name = str(mapping_row["parameter_name"])
    definition = get_wx_parameter_definition(parameter_name)
    cache_max_age_s = int(mapping_row["cache_max_age_s"]) if mapping_row.get("cache_max_age_s") is not None else int(config.get("default_cache_max_age_s") or 900)
    transform_config = _parse_json_object(mapping_row.get("transform_config_json"))
    unit_override = str(transform_config.get("unit_override") or "").strip()
    if source is None or not mapping_row.get("source_id") or not str(mapping_row.get("identifier") or "").strip():
        return _store_runtime_cache_row(
            parameter_name=parameter_name,
            source_id=int(mapping_row["source_id"]) if mapping_row.get("source_id") is not None else None,
            identifier=str(mapping_row.get("identifier") or "").strip(),
            raw_value=(existing_cache or {}).get("raw_value"),
            raw_unit=(existing_cache or {}).get("raw_unit"),
            normalized_value=(existing_cache or {}).get("normalized_value"),
            normalized_unit=(existing_cache or {}).get("normalized_unit"),
            value_origin="missing",
            status="MISSING",
            last_success_at=(existing_cache or {}).get("last_success_at"),
            last_attempt_at=attempted_at,
            last_error="Mapping is not configured.",
        )
    if not bool(source.get("enabled")):
        return _fallback_or_error_cache_row(
            mapping_row=mapping_row,
            existing_cache=existing_cache,
            config=config,
            attempted_at=attempted_at,
            error_message=f"WX source {source['name']} is disabled.",
            status_on_empty="ERROR",
        )

    try:
        read_result = build_wx_source_adapter(source).read_value(mapping_row)
        normalized_value, normalized_unit = _normalize_wx_value(
            definition.name,
            read_result.raw_value,
            raw_unit=read_result.raw_unit,
            unit_override=unit_override,
        )
    except WxMissingValueError as exc:
        return _fallback_or_error_cache_row(
            mapping_row=mapping_row,
            existing_cache=existing_cache,
            config=config,
            attempted_at=attempted_at,
            error_message=str(exc),
            status_on_empty="MISSING",
        )
    except (WxSourceError, WxValidationError) as exc:
        return _fallback_or_error_cache_row(
            mapping_row=mapping_row,
            existing_cache=existing_cache,
            config=config,
            attempted_at=attempted_at,
            error_message=str(exc),
            status_on_empty="ERROR" if not _looks_like_missing_error(str(exc)) else "MISSING",
        )

    return _store_runtime_cache_row(
        parameter_name=parameter_name,
        source_id=int(mapping_row["source_id"]) if mapping_row.get("source_id") is not None else None,
        identifier=str(mapping_row.get("identifier") or "").strip(),
        raw_value=_stringify_value(read_result.raw_value),
        raw_unit=read_result.raw_unit,
        normalized_value=_format_numeric(normalized_value),
        normalized_unit=normalized_unit,
        value_origin="live",
        status="LIVE",
        last_success_at=attempted_at,
        last_attempt_at=attempted_at,
        last_error="",
    )


def _fallback_or_error_cache_row(
    *,
    mapping_row: dict[str, Any],
    existing_cache: dict[str, Any] | None,
    config: dict[str, Any],
    attempted_at: str,
    error_message: str,
    status_on_empty: str,
) -> dict[str, Any]:
    cache_max_age_s = int(mapping_row["cache_max_age_s"]) if mapping_row.get("cache_max_age_s") is not None else int(config.get("default_cache_max_age_s") or 900)
    allow_cache_fallback = bool(config.get("allow_cache_fallback"))
    if existing_cache is not None and str(existing_cache.get("last_success_at") or "").strip():
        age_seconds = _cache_age_seconds(existing_cache.get("last_success_at"), attempted_at)
        if allow_cache_fallback and age_seconds is not None and age_seconds <= cache_max_age_s:
            return _store_runtime_cache_row(
                parameter_name=str(mapping_row["parameter_name"]),
                source_id=int(mapping_row["source_id"]) if mapping_row.get("source_id") is not None else None,
                identifier=str(mapping_row.get("identifier") or "").strip(),
                raw_value=existing_cache.get("raw_value"),
                raw_unit=existing_cache.get("raw_unit"),
                normalized_value=existing_cache.get("normalized_value"),
                normalized_unit=existing_cache.get("normalized_unit"),
                value_origin="cache",
                status="CACHED",
                last_success_at=existing_cache.get("last_success_at"),
                last_attempt_at=attempted_at,
                last_error=error_message,
            )
        return _store_runtime_cache_row(
            parameter_name=str(mapping_row["parameter_name"]),
            source_id=int(mapping_row["source_id"]) if mapping_row.get("source_id") is not None else None,
            identifier=str(mapping_row.get("identifier") or "").strip(),
            raw_value=existing_cache.get("raw_value"),
            raw_unit=existing_cache.get("raw_unit"),
            normalized_value=existing_cache.get("normalized_value"),
            normalized_unit=existing_cache.get("normalized_unit"),
            value_origin="cache",
            status="STALE",
            last_success_at=existing_cache.get("last_success_at"),
            last_attempt_at=attempted_at,
            last_error=error_message,
        )
    return _store_runtime_cache_row(
        parameter_name=str(mapping_row["parameter_name"]),
        source_id=int(mapping_row["source_id"]) if mapping_row.get("source_id") is not None else None,
        identifier=str(mapping_row.get("identifier") or "").strip(),
        raw_value=None,
        raw_unit=None,
        normalized_value=None,
        normalized_unit=get_wx_parameter_definition(str(mapping_row["parameter_name"])).canonical_unit,
        value_origin=status_on_empty.lower(),
        status=status_on_empty,
        last_success_at=None,
        last_attempt_at=attempted_at,
        last_error=error_message,
    )


def _store_runtime_cache_row(
    *,
    parameter_name: str,
    source_id: int | None,
    identifier: str,
    raw_value: Any,
    raw_unit: str | None,
    normalized_value: Any,
    normalized_unit: str | None,
    value_origin: str,
    status: str,
    last_success_at: str | None,
    last_attempt_at: str | None,
    last_error: str | None,
) -> dict[str, Any]:
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO wx_runtime_cache(
                parameter_name, source_id, identifier, raw_value, raw_unit,
                normalized_value, normalized_unit, value_origin, status,
                last_success_at, last_attempt_at, last_error, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(parameter_name) DO UPDATE SET
                source_id = excluded.source_id,
                identifier = excluded.identifier,
                raw_value = excluded.raw_value,
                raw_unit = excluded.raw_unit,
                normalized_value = excluded.normalized_value,
                normalized_unit = excluded.normalized_unit,
                value_origin = excluded.value_origin,
                status = excluded.status,
                last_success_at = excluded.last_success_at,
                last_attempt_at = excluded.last_attempt_at,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (
                parameter_name,
                source_id,
                identifier,
                raw_value,
                raw_unit,
                normalized_value,
                normalized_unit,
                value_origin,
                status,
                last_success_at,
                last_attempt_at,
                last_error,
                timestamp,
            ),
        )
    row = fetch_one("SELECT * FROM wx_runtime_cache WHERE parameter_name = ?", (parameter_name,))
    return dict(row) if row else {}


def _normalize_wx_value(parameter_name: str, raw_value: Any, *, raw_unit: str | None, unit_override: str = "") -> tuple[float, str]:
    definition = get_wx_parameter_definition(parameter_name)
    value_text = str(raw_value or "").strip()
    if raw_value is None or not value_text or value_text.lower() in {"unknown", "unavailable", "none", "null"}:
        raise WxMissingValueError(f"No usable value for {definition.label}.")
    number, detected_unit = _extract_number_and_unit(raw_value, raw_unit=raw_unit)
    effective_unit = str(unit_override or detected_unit or "").strip()
    if parameter_name == "wind_direction_deg":
        return _normalize_angle(number), definition.canonical_unit
    if parameter_name in {"humidity_pct", "raw_rain_counter", "battery_volts"} and not effective_unit:
        if parameter_name == "humidity_pct":
            effective_unit = "%"
        elif parameter_name == "raw_rain_counter":
            effective_unit = "count"
        elif parameter_name == "battery_volts":
            effective_unit = "V"
    if parameter_name == "temperature_f":
        return _convert_temperature_to_f(number, effective_unit), definition.canonical_unit
    if parameter_name in {"wind_speed_mph", "wind_gust_mph"}:
        return _convert_speed_to_mph(number, effective_unit), definition.canonical_unit
    if parameter_name in {"rain_last_hour_in", "rain_last_24h_in", "rain_since_midnight_in", "snow_last_24h_in"}:
        return _convert_length_to_inches(number, effective_unit), definition.canonical_unit
    if parameter_name == "humidity_pct":
        return _normalize_percent(number, effective_unit), definition.canonical_unit
    if parameter_name == "pressure_hpa":
        return _convert_pressure_to_hpa(number, effective_unit), definition.canonical_unit
    if parameter_name == "luminosity_w_m2":
        return _convert_luminosity_to_w_m2(number, effective_unit), definition.canonical_unit
    if parameter_name == "raw_rain_counter":
        return number, definition.canonical_unit
    if parameter_name == "water_height_ft":
        return _convert_height_to_ft(number, effective_unit), definition.canonical_unit
    if parameter_name == "water_height_m":
        return _convert_height_to_m(number, effective_unit), definition.canonical_unit
    if parameter_name == "battery_volts":
        return _convert_voltage_to_volts(number, effective_unit), definition.canonical_unit
    if parameter_name == "radiation_nsv_h":
        return _convert_radiation_to_nsv_h(number, effective_unit), definition.canonical_unit
    raise WxValidationError(f"Unsupported WX parameter: {parameter_name}")


def _extract_number_and_unit(raw_value: Any, *, raw_unit: str | None) -> tuple[float, str]:
    if isinstance(raw_value, bool):
        raise WxValidationError("Boolean values cannot be normalized as WX data.")
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        if math.isnan(float(raw_value)) or math.isinf(float(raw_value)):
            raise WxValidationError("Numeric WX value is not finite.")
        return float(raw_value), str(raw_unit or "").strip()
    if not isinstance(raw_value, str):
        raise WxValidationError("WX source returned a non-scalar value.")
    text = raw_value.strip()
    if not text:
        raise WxMissingValueError("WX source returned an empty value.")
    match = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*([A-Za-z%°/^\-]+.*)?$", text)
    if match is None:
        raise WxValidationError(f"Could not parse numeric WX value from: {text}")
    number_text = match.group(1).replace(",", ".")
    try:
        number = float(number_text)
    except ValueError as exc:
        raise WxValidationError(f"Could not parse numeric WX value from: {text}") from exc
    if math.isnan(number) or math.isinf(number):
        raise WxValidationError("Numeric WX value is not finite.")
    parsed_unit = str(match.group(2) or "").strip()
    return number, str(raw_unit or parsed_unit or "").strip()


def _convert_temperature_to_f(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace("°", "")
    if normalized in {"f", "fahrenheit"}:
        return value
    if normalized in {"c", "celsius"}:
        return (value * 9.0 / 5.0) + 32.0
    raise WxValidationError("Temperature unit is required and must be C or F.")


def _convert_speed_to_mph(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"mph"}:
        return value
    if normalized in {"km/h", "kph", "kmh"}:
        return value * 0.6213711922
    if normalized in {"m/s", "ms", "mps"}:
        return value * 2.2369362921
    if normalized in {"kt", "kts", "kn", "knot", "knots"}:
        return value * 1.150779448
    raise WxValidationError("Wind speed unit is required and must be mph, km/h, m/s or knots.")


def _convert_length_to_inches(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"in", "inch", "inches"}:
        return value
    if normalized in {"mm", "millimeter", "millimeters"}:
        return value / 25.4
    if normalized in {"cm", "centimeter", "centimeters"}:
        return value / 2.54
    raise WxValidationError("Rain or snow unit is required and must be in, mm or cm.")


def _convert_pressure_to_hpa(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"hpa", "mb", "mbar"}:
        return value
    if normalized in {"kpa"}:
        return value * 10.0
    if normalized in {"pa"}:
        return value / 100.0
    raise WxValidationError("Pressure unit is required and must be hPa, mb, mbar, kPa or Pa.")


def _convert_luminosity_to_w_m2(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"w/m2", "w/m^2", "wm2"}:
        return value
    raise WxValidationError("Luminosity unit is required and must be W/m2.")


def _convert_height_to_ft(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"ft", "feet"}:
        return value
    if normalized in {"m", "meter", "meters"}:
        return value * 3.280839895
    raise WxValidationError("Water height unit is required and must be ft or m.")


def _convert_height_to_m(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"m", "meter", "meters"}:
        return value
    if normalized in {"ft", "feet"}:
        return value / 3.280839895
    raise WxValidationError("Water height unit is required and must be ft or m.")


def _convert_voltage_to_volts(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"v", "volt", "volts"}:
        return value
    raise WxValidationError("Voltage unit is required and must be volts.")


def _convert_radiation_to_nsv_h(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "").replace("µ", "u")
    if normalized in {"nsv/h", "nsvh"}:
        return value
    if normalized in {"usv/h", "usvh"}:
        return value * 1000.0
    if normalized in {"msv/h", "msvh"}:
        return value * 1_000_000.0
    if normalized in {"sv/h", "svh"}:
        return value * 1_000_000_000.0
    raise WxValidationError("Radiation unit is required and must be nSv/h, uSv/h, mSv/h or Sv/h.")


def _normalize_percent(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"%", "percent", "pct"}:
        return max(0.0, min(value, 100.0))
    raise WxValidationError("Humidity unit is required and must be percent.")


def _normalize_angle(value: float) -> float:
    normalized = value % 360.0
    if normalized < 0:
        normalized += 360.0
    return normalized


def _format_cache_info(cache_row: dict[str, Any] | None) -> str:
    if not cache_row:
        return "-"
    last_success_at_label = _format_human_timestamp(cache_row.get("last_success_at"))
    last_attempt_at_label = _format_human_timestamp(cache_row.get("last_attempt_at"))
    if not last_success_at_label:
        return "No successful read yet"
    if last_attempt_at_label and last_attempt_at_label != last_success_at_label:
        return f"Last good: {last_success_at_label} | Last try: {last_attempt_at_label}"
    return f"Last good: {last_success_at_label}"


def _format_normalized_preview(cache_row: dict[str, Any] | None) -> str:
    if not cache_row or cache_row.get("normalized_value") in {None, ""}:
        return "-"
    unit = str(cache_row.get("normalized_unit") or "").strip()
    value = str(cache_row.get("normalized_value") or "").strip()
    return value if not unit else f"{value} {unit}"


def _status_class(status: str) -> str:
    normalized = str(status or "").strip().upper()
    if normalized in {"LIVE", "CACHED"}:
        return "status-running"
    if normalized in {"STALE", "MISSING"}:
        return "status-unknown"
    if normalized == "ERROR":
        return "status-stopped"
    return "status-unknown"


def _split_selector_parts(value: str) -> tuple[str, str]:
    try:
        return parse_value_selector(value)
    except WxSourceError:
        return "state", ""


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _normalize_positive_int(value: Any, *, default: int, minimum: int, maximum: int, label: str) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        normalized = int(text)
    except ValueError as exc:
        raise WxValidationError(f"{label} must be between {minimum} and {maximum}.") from exc
    if normalized < minimum or normalized > maximum:
        raise WxValidationError(f"{label} must be between {minimum} and {maximum}.")
    return normalized


def _normalize_printable_ascii(value: str) -> str:
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise WxValidationError("Only printable ASCII characters are allowed in WX path fields.")
    return value


def _validate_coordinate(value: str, *, minimum: float, maximum: float, label: str) -> None:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise WxValidationError(f"{label} must be a valid decimal coordinate.") from exc
    if parsed < minimum or parsed > maximum:
        raise WxValidationError(f"{label} is out of range.")


def _cache_age_seconds(last_success_at: Any, attempted_at: str) -> int | None:
    parsed_last = _parse_timestamp(last_success_at)
    parsed_attempt = _parse_timestamp(attempted_at)
    if parsed_last is None or parsed_attempt is None:
        return None
    return int((parsed_attempt - parsed_last).total_seconds())


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_human_timestamp(value: Any) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return ""
    return parsed.astimezone(timezone.utc).strftime("%Y.%m.%d %H:%M UTC")


def _format_callsign(callsign: str, ssid: str) -> str:
    return f"{callsign}-{ssid}" if callsign and ssid else callsign


def _format_numeric(value: float) -> str:
    rounded = round(float(value), 6)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.6f}".rstrip("0").rstrip(".")


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return str(value)


def _looks_like_missing_error(message: str) -> bool:
    normalized = str(message or "").strip().lower()
    return any(fragment in normalized for fragment in ("not found", "required", "empty value", "no usable value", "does not expose"))


def _parse_normalized_numeric_value(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    match = re.match(r"^-?\d+(?:\.\d+)?", text)
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
