from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from html import escape
import ipaddress
import json
import math
import re
import sqlite3
import time
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.datetime_utils import format_display_datetime
from app.db import (
    event_log_levels_at_or_above,
    fetch_all,
    fetch_one,
    get_app_setting,
    get_connection,
    log_event,
    normalize_event_log_level,
    set_app_setting,
    utc_now,
)
from app.i18n import get_app_language, get_translator
from app.services.alarm_groups import (
    alarm_event_meets_category_threshold,
    get_aprs_alarm_enabled,
    get_aprs_alarm_category_thresholds,
)
from app.services.beacon_pathing import (
    BEACON_INTERVAL_MODE_FIXED,
    BEACON_INTERVAL_MODE_PROPORTIONAL,
    normalize_beacon_interval_mode,
)
from app.services.mqtt_url import (
    OPENWEBRX_MQTT_MODEM_TYPE,
    RX_CAPABLE_MODEM_TYPES,
    TX_CAPABLE_MODEM_TYPES,
    mask_mqtt_url,
    parse_mqtt_url,
)
from app.services.aprs_device_identification import (
    get_aprs_device_identification_database,
    lookup_aprs_device_identification,
)
from app.services.activation_schedule import (
    compute_activation_state,
    normalize_activation_schedule,
    schedule_short_label,
    schedule_summary,
    schedule_warnings,
)
from app.services.outbound import build_beacon_tnc2, build_message_tnc2, build_object_tnc2, build_status_tnc2, resolve_message_addressee
from app.services.serial_tnc import normalize_serial_baud_rate, normalize_serial_device_path
from app.services.traffic_source import (
    APRSIS_MODEM_TYPE,
    APRSIS_SOURCE_KIND,
    APRSIS_TO_RF_SOURCE_KIND,
    DEFAULT_APRSIS_FILTER,
    RF_SOURCE_KIND,
    STATISTICS_TRAFFIC_SQL_PREDICATE,
    normalize_aprsis_filter,
    normalize_source_kind,
)
from app.services.tx_scope import (
    ALL_ACTIVE_INTERFACE_OPTION_VALUE,
    INTERNAL_TX_INTERFACE_OPTION_VALUE,
    TX_SCOPE_ALL_ACTIVE,
    TX_SCOPE_SINGLE,
    normalize_tx_scope,
)
from app.sections import SECTION_DEFINITIONS


STATION_SNAPSHOT_ROW_LIMIT_FACTOR = 40
STATION_SNAPSHOT_ROW_LIMIT_MIN = 4000
_STATION_SNAPSHOT_CACHE: dict[tuple[str, int, int | None, str, str], list[dict[str, Any]]] = {}
_VISIBLE_STATION_SNAPSHOT_TTL_CACHE: dict[tuple[str, int, str, str], tuple[float, list[dict[str, Any]]]] = {}
_VISIBLE_STATION_SNAPSHOT_TTL_SECONDS = 2.0
_TRAFFIC_SNAPSHOT_CACHE: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
_TRAFFIC_SNAPSHOT_CACHE_TTL_SECONDS = 1.0
SERIAL_RX_SILENCE_TIMEOUT_DEFAULT_SECONDS = 150
SERIAL_RX_SILENCE_TIMEOUT_ALLOWED_SECONDS = set(range(0, 601, 30))
MODEM_TX_MIN_GAP_SECONDS_DEFAULT = 0.35
MODEM_TX_MIN_GAP_SECONDS_MIN = 0.2
MODEM_TX_MIN_GAP_SECONDS_MAX = 1.2
DASHBOARD_ACTIVITY_WINDOW_MINUTES = 60
DASHBOARD_ACTIVITY_BUCKET_MINUTES = 5
DASHBOARD_KPI_WINDOW_HOURS = 24
STATION_TX_INTERNAL_MODE_SETTING_KEY = "station.tx.internal_mode"
_STATION_DETAIL_URL_PATTERN = re.compile(r"https?://[^\s<>'\"`]+")
APRS_SYMBOL_SET_SETTING_KEY = "aprs_symbol_set"
APRS_SYMBOL_SET_LEGACY = "legacy"
APRS_SYMBOL_SET_MODERN = "modern"


def _normalize_aprs_symbol_set(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == APRS_SYMBOL_SET_MODERN:
        return APRS_SYMBOL_SET_MODERN
    return APRS_SYMBOL_SET_LEGACY


def _aprs_symbol_icon_set_parts(symbol_set: str) -> tuple[str, str]:
    if symbol_set == APRS_SYMBOL_SET_MODERN:
        return "aprs-symbols", "png"
    return "verG", "gif"


def get_aprs_symbol_set() -> str:
    return _normalize_aprs_symbol_set(get_app_setting(APRS_SYMBOL_SET_SETTING_KEY))


def _aprs_symbol_icon_path_for_set(symbol: str, symbol_set: str) -> str | None:
    icon_dir, extension = _aprs_symbol_icon_set_parts(symbol_set)

    if len(symbol) != 2:
        filename = f"x.{extension}"
    else:
        table, code = symbol[0], symbol[1]
        index = ord(code) - 33
        if index < 0 or index > 93:
            filename = f"x.{extension}"
        else:
            filename = f"{index:02d}.{extension}" if table == "/" else f"a{index:02d}.{extension}"

    candidate = settings.static_dir / "icons" / icon_dir / filename
    if candidate.exists():
        return f"icons/{icon_dir}/{filename}"
    return None


def _aprs_symbol_icon_path_for_resolved_set(symbol: str, symbol_set: str) -> str:
    alternate_set = APRS_SYMBOL_SET_LEGACY if symbol_set == APRS_SYMBOL_SET_MODERN else APRS_SYMBOL_SET_MODERN
    for candidate_set in (symbol_set, alternate_set):
        candidate = _aprs_symbol_icon_path_for_set(symbol, candidate_set)
        if candidate is not None:
            return candidate
    for candidate_set in (symbol_set, alternate_set):
        icon_dir, extension = _aprs_symbol_icon_set_parts(candidate_set)
        candidate = settings.static_dir / "icons" / icon_dir / f"x.{extension}"
        if candidate.exists():
            return f"icons/{icon_dir}/x.{extension}"
    return "icons/verG/x.gif"


def get_aprs_symbol_icon_fallback_path() -> str:
    current_set = get_aprs_symbol_set()
    for symbol_set in (current_set, APRS_SYMBOL_SET_LEGACY if current_set == APRS_SYMBOL_SET_MODERN else APRS_SYMBOL_SET_MODERN):
        icon_dir, extension = _aprs_symbol_icon_set_parts(symbol_set)
        candidate = settings.static_dir / "icons" / icon_dir / f"x.{extension}"
        if candidate.exists():
            return f"icons/{icon_dir}/x.{extension}"
    return "icons/verG/x.gif"


def _t(message: object) -> str:
    return get_translator(get_app_language())(message)


def _setting_flag(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _is_internal_tx_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("internal_tx_only"))


def get_section_rows(slug: str) -> list[dict[str, Any]]:
    definition = SECTION_DEFINITIONS[slug]
    rows = fetch_all(f"SELECT * FROM {definition.table_name} ORDER BY id DESC")
    result = [dict(row) for row in rows]
    if slug == "modems":
        return _decorate_modem_rows(result)
    if slug in {"objects", "items"}:
        return [_decorate_aprs_entity_row(slug, row) for row in result]
    if slug == "bulletins":
        return [_decorate_aprs_message_row(row) for row in result]
    return result


def get_section_row(slug: str, row_id: int) -> dict[str, Any] | None:
    definition = SECTION_DEFINITIONS[slug]
    row = fetch_one(f"SELECT * FROM {definition.table_name} WHERE id = ?", (row_id,))
    if not row:
        return None
    result = dict(row)
    if slug == "modems":
        decorated = _decorate_modem_rows([result])
        return decorated[0] if decorated else result
    if slug in {"objects", "items"}:
        return _decorate_aprs_entity_row(slug, result)
    if slug == "bulletins":
        return _decorate_aprs_message_row(result)
    return result


def _decorate_modem_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    aprsis_tx_enabled = fetch_one(
        """
        SELECT 1
        FROM digi_flows
        WHERE enabled = 1
          AND target_kind = 'tx_aprsis'
        LIMIT 1
        """
    ) is not None
    runtime_rows = fetch_all(
        """
        SELECT modem_id, status, status_detail, last_error
        FROM traffic_runtime_interfaces
        """
    )
    runtime_by_modem_id = {int(row["modem_id"]): dict(row) for row in runtime_rows if row["modem_id"] is not None}
    aprsis_runtime_row = fetch_one(
        "SELECT status, status_detail, last_error FROM aprsis_runtime_state WHERE id = 1"
    )
    for modem_row in rows:
        if str(modem_row.get("modem_type") or "").strip().upper() == APRSIS_MODEM_TYPE:
            modem_row["aprsis_rx_enabled"] = bool(modem_row.get("enabled"))
            modem_row["aprsis_tx_enabled"] = aprsis_tx_enabled
            if aprsis_runtime_row is not None:
                runtime_by_modem_id[int(modem_row["id"])] = dict(aprsis_runtime_row)
    return [_decorate_modem_row(row, runtime_by_modem_id.get(int(row["id"]))) for row in rows]


def _decorate_modem_row(row: dict[str, Any], runtime_row: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(row)
    modem_type = str(result.get("modem_type") or "").strip().upper()
    aprsis_tx_enabled = False
    if modem_type == OPENWEBRX_MQTT_MODEM_TYPE:
        result["device_path"] = mask_mqtt_url(result.get("device_path"))
    if modem_type == APRSIS_MODEM_TYPE:
        aprsis_connection_enabled = bool(result.get("aprsis_rx_enabled", result.get("enabled")))
        aprsis_tx_configured = bool(result.get("aprsis_tx_enabled"))
        aprsis_tx_enabled = aprsis_connection_enabled and aprsis_tx_configured
        result["aprsis_connection_enabled"] = aprsis_connection_enabled
        result["aprsis_tx_configured"] = aprsis_tx_configured
        result["aprsis_tx_enabled"] = aprsis_tx_enabled
        if aprsis_connection_enabled and aprsis_tx_configured:
            result["aprsis_direction_title"] = "APRS-IS RX and Packet Routing TX are active."
        elif aprsis_connection_enabled:
            result["aprsis_direction_title"] = "APRS-IS RX is active; no TX APRS-IS flow is enabled."
        elif aprsis_tx_configured:
            result["aprsis_direction_title"] = "APRS-IS connection is disabled; the TX flow is configured but cannot transmit."
        else:
            result["aprsis_direction_title"] = "APRS-IS connection is disabled; no TX APRS-IS flow is enabled."

    connection_required = bool(result.get("enabled"))
    if not connection_required:
        result["modem_runtime_status"] = "disabled"
        result["modem_runtime_label"] = "Disabled"
        result["modem_runtime_icon"] = "close-circle-outline.svg"
        result["modem_runtime_title"] = "Disabled in configuration."
        return result

    runtime_status = str((runtime_row or {}).get("status") or "").strip().lower()
    runtime_detail = str((runtime_row or {}).get("status_detail") or "").strip()
    runtime_error = str((runtime_row or {}).get("last_error") or "").strip()
    if runtime_error or runtime_status == "error":
        result["modem_runtime_status"] = "error"
        result["modem_runtime_label"] = "Error"
        result["modem_runtime_icon"] = "alert-circle-outline.svg"
        result["modem_runtime_title"] = runtime_error or runtime_detail or "Interface connection error."
        return result
    if runtime_status == "connecting":
        result["modem_runtime_status"] = "connecting"
        result["modem_runtime_label"] = "Connecting"
        result["modem_runtime_icon"] = "progress-clock.svg"
        result["modem_runtime_title"] = runtime_detail or "Connecting interface."
        return result
    if modem_type == APRSIS_MODEM_TYPE and runtime_status == "connected":
        result["modem_runtime_status"] = "enabled"
        result["modem_runtime_label"] = "Connected"
        result["modem_runtime_icon"] = "check-circle-outline.svg"
        result["modem_runtime_title"] = "APRS-IS connection is active."
        return result
    if modem_type == APRSIS_MODEM_TYPE:
        result["modem_runtime_status"] = "disabled"
        result["modem_runtime_label"] = "Inactive"
        result["modem_runtime_icon"] = "close-circle-outline.svg"
        result["modem_runtime_title"] = "APRS-IS connection is inactive."
        return result

    result["modem_runtime_status"] = "enabled"
    result["modem_runtime_label"] = "Enabled"
    result["modem_runtime_icon"] = "check-circle-outline.svg"
    result["modem_runtime_title"] = runtime_detail or "Enabled in configuration."
    return result


def create_section_row(slug: str, payload: dict[str, Any]) -> None:
    definition = SECTION_DEFINITIONS[slug]
    timestamp = utc_now()
    normalized_payload = _normalize_section_payload(slug, payload)
    if slug == "modems" and normalized_payload.get("modem_type") == APRSIS_MODEM_TYPE:
        _ensure_single_aprsis_interface()
    values: dict[str, Any] = {}
    for field in definition.fields:
        name = field["name"]
        if field["type"] == "checkbox":
            values[name] = int(bool(normalized_payload.get(name)))
        else:
            values[name] = normalized_payload.get(name)
    if slug == "modems" and values.get("modem_type") == "TCP":
        values["baud_rate"] = None
    if slug == "servers":
        values.setdefault("notes", "")
    if slug in {"modems", "servers"}:
        columns = list(values.keys()) + ["created_at", "updated_at"]
        params = list(values.values()) + [timestamp, timestamp]
    else:
        columns = list(values.keys()) + ["updated_at"]
        params = list(values.values()) + [timestamp]
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    with get_connection() as connection:
        connection.execute(
            f"INSERT INTO {definition.table_name} ({column_list}) VALUES ({placeholders})",
            tuple(params),
        )
    log_event("INFO", "config", f"Created record in {definition.table_name}")


def update_section_row(slug: str, row_id: int, payload: dict[str, Any]) -> None:
    definition = SECTION_DEFINITIONS[slug]
    normalized_payload = _normalize_section_payload(slug, payload)
    if slug == "modems" and normalized_payload.get("modem_type") == APRSIS_MODEM_TYPE:
        _ensure_single_aprsis_interface(exclude_id=row_id)
    previous_row: dict[str, Any] | None = None
    if slug == "modems":
        row = fetch_one(
            """
            SELECT id, name
            FROM modems
            WHERE id = ?
            """,
            (row_id,),
        )
        previous_row = dict(row) if row is not None else None
    values: dict[str, Any] = {}
    for field in definition.fields:
        name = field["name"]
        if field["type"] == "checkbox":
            values[name] = int(bool(normalized_payload.get(name)))
        else:
            values[name] = normalized_payload.get(name)
    if slug == "modems" and values.get("modem_type") == "TCP":
        values["baud_rate"] = None
    if slug == "servers":
        values.setdefault("notes", "")
    values["updated_at"] = utc_now()
    values["id"] = row_id
    assignments = ", ".join(f"{field['name']} = :{field['name']}" for field in definition.fields)
    with get_connection() as connection:
        connection.execute(
            f"""
            UPDATE {definition.table_name}
            SET {assignments},
                updated_at = :updated_at
            WHERE id = :id
            """,
            values,
        )
        if slug == "modems" and previous_row is not None:
            previous_name = str(previous_row.get("name") or "").strip()
            current_name = str(values.get("name") or "").strip()
            if previous_name and current_name and previous_name != current_name:
                _propagate_modem_rename_to_digi_flows(
                    connection=connection,
                    previous_name=previous_name,
                    current_name=current_name,
                )
    log_event("INFO", "config", f"Updated record {row_id} in {definition.table_name}")


def _propagate_modem_rename_to_digi_flows(
    *,
    connection: sqlite3.Connection,
    previous_name: str,
    current_name: str,
) -> None:
    timestamp = utc_now()
    connection.execute(
        """
        UPDATE digi_flows
        SET source_ref = ?, updated_at = ?
        WHERE source_kind IN ('receiver_rf', 'receiver_aprsis')
          AND source_ref = ?
        """,
        (current_name, timestamp, previous_name),
    )
    connection.execute(
        """
        UPDATE digi_flows
        SET target_ref = ?, updated_at = ?
        WHERE target_kind = 'tx_rf'
          AND target_ref = ?
        """,
        (current_name, timestamp, previous_name),
    )
    rows = connection.execute(
        """
        SELECT id, step_type, config_json
        FROM digi_flow_steps
        WHERE step_type IN ('receiver_rf', 'receiver_aprsis', 'tx_rf')
        """,
    ).fetchall()
    for row in rows:
        try:
            config = json.loads(str(row["config_json"] or "{}"))
        except json.JSONDecodeError:
            continue
        step_type = str(row["step_type"] or "")
        updated = False
        if step_type == "receiver_rf" and str(config.get("rf_port") or "").strip() == previous_name:
            config["rf_port"] = current_name
            updated = True
        elif step_type == "receiver_aprsis" and str(config.get("aprsis_source") or "").strip() == previous_name:
            config["aprsis_source"] = current_name
            updated = True
        elif step_type == "tx_rf" and str(config.get("rf_target") or "").strip() == previous_name:
            config["rf_target"] = current_name
            updated = True
        if updated:
            connection.execute(
                """
                UPDATE digi_flow_steps
                SET config_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(config, ensure_ascii=True, separators=(",", ":")), timestamp, int(row["id"])),
            )


def delete_section_row(slug: str, row_id: int) -> None:
    definition = SECTION_DEFINITIONS[slug]
    with get_connection() as connection:
        connection.execute(f"DELETE FROM {definition.table_name} WHERE id = ?", (row_id,))
    log_event("INFO", "config", f"Deleted record {row_id} from {definition.table_name}")


def set_modem_enabled(row_id: int, enabled: bool) -> None:
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE modems SET enabled = ?, updated_at = ? WHERE id = ?",
            (int(enabled), timestamp, row_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Interface not found.")
    state = "enabled" if enabled else "disabled"
    log_event("INFO", "config", f"Interface {row_id} {state}")


def get_station_settings() -> dict[str, Any]:
    row = fetch_one("SELECT * FROM station_settings WHERE id = 1")
    if not row:
        return {}
    result = dict(row)
    result.setdefault("beacon_interface_id", None)
    result["beacon_tx_scope"] = normalize_tx_scope(result.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE)
    result["beacon_internal_tx"] = _setting_flag(get_app_setting(STATION_TX_INTERNAL_MODE_SETTING_KEY))
    result.setdefault("default_units", "metric")
    result["beacon_interval_mode"] = normalize_beacon_interval_mode(
        result.get("beacon_interval_mode"),
        default=BEACON_INTERVAL_MODE_FIXED,
    )
    result.setdefault("beacon_interval_minutes", 30)
    result.setdefault("beacon_path", "")
    result.setdefault("status_enabled", 0)
    result.setdefault("status_text", "")
    result.setdefault("status_interval_minutes", 30)
    result.setdefault("symbol_overlay", None)
    return result


def get_configured_modem_interfaces() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    return [dict(row) for row in rows]


def get_active_tnc_interfaces() -> list[dict[str, Any]]:
    modem_type_filter = ", ".join(f"'{item}'" for item in TX_CAPABLE_MODEM_TYPES)
    rows = fetch_all(
        f"""
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE enabled = 1
          AND modem_type IN ({modem_type_filter})
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    return [dict(row) for row in rows]


def has_enabled_modem_interface() -> bool:
    modem_type_filter = ", ".join(f"'{item}'" for item in TX_CAPABLE_MODEM_TYPES)
    row = fetch_one(
        f"""
        SELECT 1
        FROM modems
        WHERE enabled = 1 AND modem_type IN ({modem_type_filter})
        LIMIT 1
        """
    )
    return row is not None


def update_station_settings(payload: dict[str, Any]) -> None:
    values = normalize_station_settings_payload(payload)
    internal_tx_enabled = bool(values.pop("beacon_internal_tx", False))
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE station_settings
            SET callsign = :callsign,
                ssid = :ssid,
                beacon_interface_id = :beacon_interface_id,
                beacon_tx_scope = :beacon_tx_scope,
                beacon_comment = :beacon_comment,
                beacon_interval_mode = :beacon_interval_mode,
                beacon_interval_minutes = :beacon_interval_minutes,
                beacon_path = :beacon_path,
                status_enabled = :status_enabled,
                status_text = :status_text,
                status_interval_minutes = :status_interval_minutes,
                latitude = :latitude,
                longitude = :longitude,
                symbol_table = :symbol_table,
                symbol_code = :symbol_code,
                symbol_overlay = :symbol_overlay,
                default_units = :default_units,
                tx_enabled = :tx_enabled,
                updated_at = :updated_at
            WHERE id = 1
            """,
            values,
        )
    set_app_setting(STATION_TX_INTERNAL_MODE_SETTING_KEY, "1" if internal_tx_enabled else "0")
    log_event(
        "INFO",
        "config",
        (
            "Updated station settings "
            f"(tx_enabled={values['tx_enabled']}, beacon_interval_minutes={values['beacon_interval_minutes']}, "
            f"status_enabled={values['status_enabled']}, status_interval_minutes={values['status_interval_minutes']}, "
            f"status_text={values['status_text']!r})"
        ),
    )


def safe_update_station_settings(payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        update_station_settings(payload)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def normalize_station_settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    default_units = payload.get("default_units", "metric")
    if default_units not in {"metric", "imperial"}:
        default_units = "metric"
    beacon_tx_scope = normalize_tx_scope(payload.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE)
    raw_beacon_interface = str(payload.get("beacon_interface_id") or "").strip()
    beacon_internal_tx = False
    if raw_beacon_interface == INTERNAL_TX_INTERFACE_OPTION_VALUE or (
        bool(payload.get("beacon_internal_tx")) and raw_beacon_interface in {"", None}
    ):
        beacon_internal_tx = True
        raw_beacon_interface = ""
    if raw_beacon_interface == ALL_ACTIVE_INTERFACE_OPTION_VALUE:
        beacon_tx_scope = TX_SCOPE_ALL_ACTIVE
        raw_beacon_interface = ""
        beacon_internal_tx = False
    try:
        beacon_interface_id = int(raw_beacon_interface) if raw_beacon_interface not in {"", None} else None
    except (TypeError, ValueError):
        beacon_interface_id = None
    if beacon_interface_id is not None and beacon_tx_scope == TX_SCOPE_SINGLE:
        interface_exists = fetch_one("SELECT id FROM modems WHERE id = ?", (beacon_interface_id,))
        if interface_exists is None:
            beacon_interface_id = None
    if beacon_tx_scope == TX_SCOPE_ALL_ACTIVE:
        beacon_interface_id = None
    beacon_interval_mode, beacon_interval_minutes = _normalize_station_beacon_interval_config(payload)
    status_interval_minutes = _normalize_station_interval(payload.get("status_interval_minutes"), label="Status interval")
    status_enabled = int(bool(payload.get("status_enabled")))
    beacon_comment = _normalize_station_text_field(
        payload.get("beacon_comment", ""), max_length=43, label="Beacon comment"
    )
    status_text = _normalize_station_text_field(
        payload.get("status_text", ""), max_length=62, label="Status text"
    )
    if status_enabled and not status_text:
        raise ValueError("Status text is required when APRS Status is enabled.")
    symbol_table = str(payload.get("symbol_table", "/") or "/").strip()
    if symbol_table not in {"/", "\\"}:
        symbol_table = "/"
    symbol_code = str(payload.get("symbol_code", ">") or ">").strip()[:1]
    if len(symbol_code) != 1 or not (33 <= ord(symbol_code) <= 126):
        symbol_code = ">"
    symbol_overlay = _normalize_station_symbol_overlay_value(payload.get("symbol_overlay"), symbol_table=symbol_table)
    return {
        "callsign": _normalize_station_callsign(payload.get("callsign", "")),
        "ssid": payload.get("ssid", ""),
        "beacon_interface_id": beacon_interface_id,
        "beacon_tx_scope": beacon_tx_scope,
        "beacon_internal_tx": beacon_internal_tx,
        "beacon_comment": beacon_comment,
        "beacon_interval_mode": beacon_interval_mode,
        "beacon_interval_minutes": beacon_interval_minutes,
        "beacon_path": str(payload.get("beacon_path", "") or "").strip().upper(),
        "status_enabled": status_enabled,
        "status_text": status_text,
        "status_interval_minutes": status_interval_minutes,
        "latitude": payload.get("latitude", ""),
        "longitude": payload.get("longitude", ""),
        "symbol_table": symbol_table,
        "symbol_code": symbol_code,
        "symbol_overlay": symbol_overlay,
        "default_units": default_units,
        "tx_enabled": int(bool(payload.get("tx_enabled"))),
        "updated_at": utc_now(),
    }


def station_has_tx_target(station_settings: dict[str, Any] | None = None) -> bool:
    resolved_settings = station_settings or get_station_settings()
    if bool(resolved_settings.get("beacon_internal_tx")):
        return True
    scope = normalize_tx_scope(resolved_settings.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE)
    if scope == TX_SCOPE_ALL_ACTIVE:
        return bool(get_active_tnc_interfaces())
    return resolved_settings.get("beacon_interface_id") not in {None, ""}


def _normalize_station_symbol_overlay_value(value: Any, *, symbol_table: str) -> str | None:
    if symbol_table != "\\":
        return None
    text = str(value or "").strip().upper()
    if len(text) == 1 and ("0" <= text <= "9" or "A" <= text <= "Z"):
        return text
    return None


def recent_event_logs(limit: int = 100, *, min_level: str = "DEBUG") -> list[dict[str, Any]]:
    levels = event_log_levels_at_or_above(normalize_event_log_level(min_level, default="DEBUG"))
    level_placeholders = ", ".join("?" for _ in levels)
    rows = fetch_all(
        f"""
        SELECT id, level, category, message, created_at
        FROM event_logs
        WHERE category NOT IN ('outbound', 'digi_flow_runtime', 'aprsis', 'aprs', 'messages', 'notifications_radar')
          AND level IN ({level_placeholders})
        ORDER BY id DESC
        LIMIT ?
        """,
        (*levels, limit),
    )
    return [dict(row) for row in rows]


def recent_station_outbound_jobs(limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = fetch_all(
            """
            SELECT j.id, j.status, j.scheduled_at, j.started_at, j.sent_at, j.attempt_count, j.last_error,
                   j.kind, m.name AS interface_name, j.payload_json
            FROM outbound_jobs j
            LEFT JOIN modems m ON m.id = j.interface_id
            WHERE j.kind IN ('beacon', 'status')
            ORDER BY COALESCE(j.sent_at, j.started_at, j.scheduled_at, j.created_at) DESC, j.id DESC
            LIMIT ?
            """,
            (limit,),
        )
    except sqlite3.OperationalError:
        return []
    jobs: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload_json = item.pop("payload_json", "") or "{}"
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            payload = {}
        kind = str(item.get("kind") or "").strip()
        if payload and kind == "beacon":
            item["line"] = build_beacon_tnc2(payload)
        elif payload and kind == "status":
            item["line"] = build_status_tnc2(payload)
        else:
            item["line"] = ""
        item["interface_name"] = item.get("interface_name") or ("Internal TX" if _is_internal_tx_payload(payload) else "Unknown interface")
        skip_reason = str(item.get("last_error") or "").strip()
        item["is_tx_skipped"] = bool(skip_reason) and skip_reason.startswith("TX skipped:")
        item["display_time"] = item.get("sent_at") or item.get("started_at") or item.get("scheduled_at") or ""
        jobs.append(item)
    return jobs


def recent_object_outbound_jobs(limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = fetch_all(
            """
            SELECT j.id, j.status, j.scheduled_at, j.started_at, j.sent_at, j.attempt_count, j.last_error,
                   j.kind, m.name AS interface_name, j.payload_json
            FROM outbound_jobs j
            LEFT JOIN modems m ON m.id = j.interface_id
            WHERE j.kind = 'object'
            ORDER BY COALESCE(j.sent_at, j.started_at, j.scheduled_at, j.created_at) DESC, j.id DESC
            LIMIT ?
            """,
            (limit,),
        )
    except sqlite3.OperationalError:
        return []
    jobs: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload_json = item.pop("payload_json", "") or "{}"
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            payload = {}
        if payload:
            try:
                item["line"] = build_object_tnc2(payload)
            except Exception:
                item["line"] = ""
        else:
            item["line"] = ""
        item["display_kind"] = "Object"
        item["interface_name"] = item.get("interface_name") or ("Internal TX" if _is_internal_tx_payload(payload) else "Unknown interface")
        skip_reason = str(item.get("last_error") or "").strip()
        item["is_tx_skipped"] = bool(skip_reason) and skip_reason.startswith("TX skipped:")
        item["display_time"] = item.get("sent_at") or item.get("started_at") or item.get("scheduled_at") or ""
        jobs.append(item)
    return jobs


def recent_bulletin_outbound_jobs(limit: int = 20) -> list[dict[str, Any]]:
    try:
        rows = fetch_all(
            """
            SELECT j.id, j.status, j.scheduled_at, j.started_at, j.sent_at, j.attempt_count, j.last_error,
                   j.kind, m.name AS interface_name, j.payload_json
            FROM outbound_jobs j
            LEFT JOIN modems m ON m.id = j.interface_id
            WHERE j.kind = 'message'
              AND j.payload_json LIKE '%"message_id"%'
            ORDER BY COALESCE(j.sent_at, j.started_at, j.scheduled_at, j.created_at) DESC, j.id DESC
            LIMIT ?
            """,
            (limit,),
        )
    except sqlite3.OperationalError:
        return []
    jobs: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload_json = item.pop("payload_json", "") or "{}"
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict) or payload.get("message_id") is None:
            continue
        if payload:
            try:
                item["line"] = build_message_tnc2(payload)
            except Exception:
                item["line"] = ""
        else:
            item["line"] = ""
        message_kind = str(payload.get("message_kind") or "").strip().lower()
        item["display_kind"] = {
            "bulletin": "Bulletin",
            "announcement": "Announcement",
            "group_bulletin": "Group Bulletin",
        }.get(message_kind, "Bulletin")
        item["interface_name"] = item.get("interface_name") or ("Internal TX" if _is_internal_tx_payload(payload) else "Unknown interface")
        skip_reason = str(item.get("last_error") or "").strip()
        item["is_tx_skipped"] = bool(skip_reason) and skip_reason.startswith("TX skipped:")
        item["display_time"] = item.get("sent_at") or item.get("started_at") or item.get("scheduled_at") or ""
        jobs.append(item)
    return jobs


def traffic_snapshot(limit: int = 400) -> dict[str, Any]:
    cache_key = (str(settings.database_path), int(limit))
    cached_snapshot = _TRAFFIC_SNAPSHOT_CACHE.get(cache_key)
    current_time = time.monotonic()
    if cached_snapshot is not None and current_time - cached_snapshot[0] < _TRAFFIC_SNAPSHOT_CACHE_TTL_SECONDS:
        return copy.deepcopy(cached_snapshot[1])

    station_settings = get_station_settings()

    from app.services.wx import get_wx_config

    wx_config = get_wx_config()
    station_source_key = _station_source_key(station_settings)
    wx_source_key = _build_source_key(
        wx_config.get("callsign"),
        wx_config.get("ssid"),
    )
    interface_rows = fetch_all(
        """
        SELECT
            modem_id,
            modem_name,
            modem_endpoint,
            band,
            status,
            status_detail,
            expose_port_enabled,
            expose_bind_address,
            expose_port,
            expose_active_clients,
            mqtt_connected,
            mqtt_subscribed_topic,
            mqtt_broker_host,
            mqtt_broker_port,
            mqtt_last_frame_at,
            mqtt_frames_received,
            mqtt_duplicates_dropped,
            mqtt_invalid_json_dropped,
            last_error,
            updated_at
        FROM traffic_runtime_interfaces
        ORDER BY modem_id ASC
        """
    )
    state_row = fetch_one(
        """
        SELECT
            status,
            status_detail,
            active_modem_name,
            active_modem_endpoint,
            expose_port_enabled,
            expose_bind_address,
            expose_port,
            expose_active_clients,
            last_error,
            updated_at
        FROM traffic_runtime_state
        WHERE id = 1
        """
    )
    frame_rows = fetch_all(
        """
        SELECT
            frames.id,
            frames.source,
            frames.source_kind,
            frames.interface_id,
            frames.direction,
            frames.band,
            frames.format,
            frames.line,
            frames.port,
            frames.command,
            frames.length,
            frames.hex,
            frames.created_at,
            relations.alert_id,
            alerts.source_callsign AS alert_source_callsign,
            alerts.alarm_group AS alert_alarm_group,
            alerts.event_code AS alert_event_code,
            alerts.logical_alert_id AS alert_logical_alert_id,
            alerts.severity_level AS alert_severity_level,
            alerts.is_active AS alert_is_active,
            alerts.expires_at AS alert_expires_at,
            alerts.valid_until_utc AS alert_valid_until_utc,
            alerts.superseded_by_alert_id AS alert_superseded_by_alert_id,
            alerts.initial_frame_id AS alert_initial_frame_id,
            alerts.last_frame_id AS alert_last_frame_id,
            alerts.muted_until AS alert_muted_until,
            alerts.muted_indefinitely AS alert_muted_indefinitely
        FROM traffic_frames AS frames
        LEFT JOIN aprs_alert_frames AS relations ON relations.frame_id = frames.id
        LEFT JOIN aprs_alerts AS alerts ON alerts.id = relations.alert_id
        ORDER BY frames.created_at DESC, frames.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    interfaces = []
    for row in interface_rows:
        expose = {
            "enabled": bool(row["expose_port_enabled"]),
            "bind_address": row["expose_bind_address"],
            "port": int(row["expose_port"]) if row["expose_port"] is not None else None,
            "active_clients": int(row["expose_active_clients"]) if row["expose_active_clients"] is not None else 0,
        }
        expose["listen_endpoint"] = (
            f"{expose['bind_address']}:{expose['port']}"
            if expose["enabled"] and expose["bind_address"] and expose["port"] is not None
            else None
        )
        interfaces.append(
            {
                "modem_id": int(row["modem_id"]),
                "name": row["modem_name"] or "",
                "modem_type": "",
                "device_path": row["modem_endpoint"] or "",
                "band": row["band"] or "",
                "status": row["status"] or "idle",
                "status_detail": row["status_detail"] or "",
                "last_error": row["last_error"],
                "updated_at": _format_monitor_timestamp(row["updated_at"]),
                "connected": bool(row["mqtt_connected"]) if row["mqtt_connected"] is not None else str(row["status"] or "").strip().lower() == "connected",
                "subscribed_topic": str(row["mqtt_subscribed_topic"] or "").strip(),
                "broker_host": str(row["mqtt_broker_host"] or "").strip(),
                "broker_port": int(row["mqtt_broker_port"]) if row["mqtt_broker_port"] is not None else None,
                "last_frame_time": _format_monitor_timestamp(row["mqtt_last_frame_at"]),
                "frames_received": int(row["mqtt_frames_received"]) if row["mqtt_frames_received"] is not None else 0,
                "duplicates_dropped": int(row["mqtt_duplicates_dropped"]) if row["mqtt_duplicates_dropped"] is not None else 0,
                "invalid_json_dropped": int(row["mqtt_invalid_json_dropped"]) if row["mqtt_invalid_json_dropped"] is not None else 0,
                "expose": expose,
            }
        )
    aprsis_interface_row = fetch_one(
        """
        SELECT id, name, device_path
        FROM modems
        WHERE enabled = 1 AND UPPER(modem_type) = 'APRSIS'
        ORDER BY id ASC
        LIMIT 1
        """
    )
    if aprsis_interface_row is not None:
        from app.services.aprsis import get_aprsis_runtime_status

        aprsis_runtime = get_aprsis_runtime_status()
        interfaces.append(
            {
                "modem_id": int(aprsis_interface_row["id"]),
                "name": str(aprsis_interface_row["name"] or "APRSIS"),
                "modem_type": APRSIS_MODEM_TYPE,
                "device_path": str(aprsis_interface_row["device_path"] or DEFAULT_APRSIS_FILTER),
                "band": "APRS-IS",
                "status": str(aprsis_runtime.get("status") or "inactive"),
                "status_detail": str(aprsis_runtime.get("status_detail") or ""),
                "last_error": aprsis_runtime.get("last_error"),
                "updated_at": _format_monitor_timestamp(aprsis_runtime.get("updated_at")),
                "connected": str(aprsis_runtime.get("status") or "").lower() == "connected",
                "subscribed_topic": "",
                "broker_host": str(aprsis_runtime.get("server") or ""),
                "broker_port": aprsis_runtime.get("port"),
                "last_frame_time": None,
                "frames_received": 0,
                "duplicates_dropped": 0,
                "invalid_json_dropped": 0,
                "expose": {
                    "enabled": False,
                    "bind_address": None,
                    "port": None,
                    "active_clients": 0,
                    "listen_endpoint": None,
                },
            }
        )
    active_modem = None
    if interfaces:
        preferred = next((item for item in interfaces if item["status"] == "connected"), interfaces[0])
        if preferred["name"] or preferred["device_path"]:
            active_modem = {
                "id": preferred["modem_id"],
                "name": preferred["name"],
                "device_path": preferred["device_path"],
                "band": preferred["band"],
            }
    elif state_row and (state_row["active_modem_name"] or state_row["active_modem_endpoint"]):
        active_modem = {
            "name": state_row["active_modem_name"] or "",
            "device_path": state_row["active_modem_endpoint"] or "",
        }
    if len(interfaces) == 1:
        expose = dict(interfaces[0]["expose"])
    else:
        expose = {
            "enabled": any(bool(item["expose"]["enabled"]) for item in interfaces),
            "bind_address": None,
            "port": None,
            "active_clients": sum(int(item["expose"]["active_clients"]) for item in interfaces),
            "listen_endpoint": None,
        }
    status = state_row["status"] if state_row else "idle"
    status_detail = state_row["status_detail"] if state_row else "Traffic monitor state unavailable."
    updated_at = _format_monitor_timestamp(state_row["updated_at"]) if state_row else None
    if len(interfaces) == 1 and interfaces[0].get("modem_type") == APRSIS_MODEM_TYPE:
        status = str(interfaces[0].get("status") or "inactive")
        status_detail = str(interfaces[0].get("status_detail") or "")
        updated_at = interfaces[0].get("updated_at")
    if interfaces and len(interfaces) > 1:
        connected = [item for item in interfaces if item["status"] == "connected"]
        connecting = [item for item in interfaces if item["status"] == "connecting"]
        if connected:
            status = "connected"
            status_detail = f"{len(connected)}/{len(interfaces)} interfaces connected."
        elif connecting:
            status = "connecting"
            status_detail = f"Connecting {len(connecting)} interface(s)."
        else:
            status = "error" if any(item["last_error"] for item in interfaces) else interfaces[0]["status"]
            status_detail = (
                next((str(item["last_error"]) for item in interfaces if item["last_error"]), None)
                or interfaces[0]["status_detail"]
            )
        updated_at = max((item["updated_at"] for item in interfaces if item["updated_at"]), default=updated_at)
    last_error = next((item["last_error"] for item in interfaces if item["last_error"]), None)
    if last_error is None and state_row:
        last_error = state_row["last_error"]
    frames: list[dict[str, Any]] = []
    snapshot_now = datetime.now(timezone.utc)
    aprs_alarm_enabled = get_aprs_alarm_enabled()
    alarm_popup_thresholds = get_aprs_alarm_category_thresholds()
    for row in frame_rows:
        direction = str(row["direction"] or "").upper() or ("TX" if str(row["format"] or "").endswith("-TX") else "RX")
        line = str(row["line"] or "")
        parsed = parse_tnc2_frame(line)
        aprs_data = parsed.get("aprs_data") if parsed else {}
        packet_group = str((aprs_data or {}).get("packet_group") or "").strip().lower()
        symbol = str((aprs_data or {}).get("symbol") or "").strip()
        display_callsign = str((aprs_data or {}).get("entity_name") or "").strip()
        if packet_group not in {"object", "item"} or not display_callsign:
            display_callsign = str(
                (parsed or {}).get("logical_source_key")
                or (parsed or {}).get("source_key")
                or row["source"]
                or ""
            ).strip()
        display_icon_path = get_aprs_symbol_icon_path(symbol) if packet_group in {"object", "item"} else ""
        emergency_data = build_emergency_frame_data(parsed=parsed, row=row, line=line) if parsed else None
        source_kind = normalize_source_kind(row["source_kind"])
        row_class = _traffic_frame_row_class(
            direction=direction,
            line=line,
            command=str(row["command"] or ""),
            station_source_key=station_source_key,
            wx_source_key=wx_source_key,
            source_kind=source_kind,
        )
        alert_id = int(row["alert_id"]) if row["alert_id"] is not None else None
        alert_muted_until = _parse_iso_timestamp_utc(str(row["alert_muted_until"] or ""))
        alert_muted = bool(int(row["alert_muted_indefinitely"] or 0)) or (
            alert_muted_until is not None and alert_muted_until > snapshot_now
        )
        alarm_group = str(row["alert_alarm_group"] or "").strip().upper()
        alert_expires_at = _parse_iso_timestamp_utc(str(row["alert_expires_at"] or ""))
        alert_valid_until = _parse_iso_timestamp_utc(
            str(row["alert_valid_until_utc"] or "")
        )
        alert_active = bool(int(row["alert_is_active"] or 0)) and (
            row["alert_superseded_by_alert_id"] is None
        ) and (
            alert_expires_at is None or alert_expires_at > snapshot_now
        ) and (
            alert_valid_until is None or alert_valid_until > snapshot_now
        )
        alarm_group_popup = bool(
            aprs_alarm_enabled
            and alert_id is not None
            and alarm_group
            and alert_active
            and alarm_event_meets_category_threshold(
                row["alert_event_code"],
                row["alert_severity_level"],
                target="popup",
                thresholds=alarm_popup_thresholds,
            )
        )
        alarm_group_popup_data = None
        if alarm_group_popup:
            popup_summary = " · ".join(
                value
                for value in (
                    str(row["alert_event_code"] or "").strip().upper(),
                    alarm_group,
                    str(row["alert_logical_alert_id"] or "").strip().upper(),
                )
                if value
            )
            alarm_group_popup_data = {
                "callsign": str(row["alert_source_callsign"] or "").strip(),
                "summary": popup_summary,
                "timestamp_utc": row["created_at"],
                "raw_frame": line,
                "source_interface": row["source"],
                "source_port": row["port"],
                "path": str(
                    (parsed or {}).get("logical_path")
                    or (parsed or {}).get("path")
                    or ""
                ).strip(),
                "latitude": (aprs_data or {}).get("latitude"),
                "longitude": (aprs_data or {}).get("longitude"),
                "destination_group": alarm_group,
                "event_code": str(row["alert_event_code"] or "").strip().upper(),
                "logical_alert_id": str(
                    row["alert_logical_alert_id"] or ""
                ).strip().upper(),
                "severity_level": row["alert_severity_level"],
            }
        alert_popup_data = emergency_data or alarm_group_popup_data
        alert_popup_kind = (
            "emergency"
            if emergency_data is not None
            else ("alarm_group" if alarm_group_popup else "")
        )
        if emergency_data:
            row_class = f"{row_class} traffic-log-row-emergency".strip()
        frames.append(
            {
                "id": int(row["id"]),
                "timestamp": _format_monitor_timestamp(row["created_at"]),
                "source": row["source"],
                "source_kind": source_kind,
                "is_rf": source_kind == RF_SOURCE_KIND,
                "interface_id": int(row["interface_id"]) if row["interface_id"] is not None else None,
                "direction": direction,
                "band": row["band"] or "",
                "format": row["format"],
                "line": row["line"],
                "port": row["port"] or "",
                "command": row["command"] or "",
                "length": str(row["length"]),
                "hex": row["hex"] or "",
                "row_class": row_class,
                "display_callsign": display_callsign,
                "display_packet_group": packet_group,
                "display_icon_path": display_icon_path,
                "emergency": bool(emergency_data),
                "emergency_data": emergency_data,
                "alert_popup": bool(alert_popup_data),
                "alert_popup_kind": alert_popup_kind,
                "alert_popup_data": alert_popup_data,
                "detail_href": f"/traffic/frames/{int(row['id'])}",
                "alert_id": alert_id,
                "alert_callsign": str(row["alert_source_callsign"] or "").strip(),
                "alert_href": f"/alerts/{alert_id}" if alert_id is not None else "",
                "alert_muted": alert_muted,
                "alert_should_notify": bool(
                    alert_id is not None
                    and not alert_muted
                    and (
                        (
                            emergency_data is not None
                            and row["alert_last_frame_id"] is not None
                            and int(row["alert_last_frame_id"]) == int(row["id"])
                        )
                        or (
                            alarm_group_popup
                            and row["alert_initial_frame_id"] is not None
                            and int(row["alert_initial_frame_id"]) == int(row["id"])
                        )
                    )
                ),
                "alert_record_deleted": bool(emergency_data and alert_id is None),
            }
        )
    result = {
        "status": status,
        "status_detail": status_detail,
        "active_modem": active_modem,
        "expose": expose,
        "interfaces": interfaces,
        "last_error": last_error,
        "updated_at": updated_at,
        "frames": frames,
    }
    _TRAFFIC_SNAPSHOT_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(result))
    return result


_EMERGENCY_COMMENT_PREFIX_RE = re.compile(
    r"^!?((?:TESTALARM|EMERGENCY|ALARM|ALERT|WARNING|WXALARM|EM))!",
    re.IGNORECASE,
)
_MIC_E_MESSAGE_LABELS = {
    0: "OFF-DUTY",
    1: "ENROUTE",
    2: "IN SERVICE",
    3: "RETURNING",
    4: "COMMITTED",
    5: "SPECIAL",
    6: "PRIORITY",
    7: "EMERGENCY",
}
_MIC_E_STATUS_LABELS = {
    0: "Off Duty",
    1: "En Route",
    2: "In Service",
    3: "Returning",
    4: "Committed",
    5: "Special",
    6: "Priority",
    7: "Emergency",
}


def _strip_emergency_comment_prefix(text: str) -> str:
    comment = str(text or "").strip()
    match = _EMERGENCY_COMMENT_PREFIX_RE.match(comment)
    if not match:
        return comment
    return comment[match.end():].lstrip(" /,;:-")


def _extract_emergency_comment_token(text: str) -> str | None:
    comment = str(text or "").strip()
    match = _EMERGENCY_COMMENT_PREFIX_RE.match(comment)
    if not match:
        return None
    token = match.group(1)
    return token.upper() if token else None


def build_emergency_frame_data(*, parsed: dict[str, Any], row: Any, line: str) -> dict[str, Any] | None:
    aprs_data = dict(parsed.get("aprs_data") or {})
    if not bool(aprs_data.get("emergency")):
        return None

    comment = str(
        aprs_data.get("emergency_comment")
        or aprs_data.get("comment")
        or ""
    ).strip()
    summary = _strip_emergency_comment_prefix(comment)
    if not summary and aprs_data.get("data"):
        decoded_items = _format_decoded_data_for_display(dict(aprs_data["data"]), "metric")
        summary = ", ".join(
            str(item.get("value") or "").strip()
            for item in decoded_items[:4]
            if str(item.get("value") or "").strip()
        )

    callsign = str(
        (aprs_data.get("entity_name") or "")
        or (parsed.get("logical_source_key") or "")
        or (parsed.get("source_key") or "")
        or (row["source"] or "")
    ).strip()

    return {
        "callsign": callsign,
        "source_interface": str(row["source"] or "").strip(),
        "source_port": str(row["port"] or "").strip(),
        "path": str(parsed.get("logical_path") or parsed.get("path") or "").strip(),
        "timestamp_utc": str(row["created_at"] or "").strip(),
        "comment": comment,
        "summary": summary,
        "latitude": aprs_data.get("latitude"),
        "longitude": aprs_data.get("longitude"),
        "raw_frame": line,
        "emergency_code": str(aprs_data.get("emergency_code") or "").strip(),
        "emergency_source": str(aprs_data.get("emergency_source") or "").strip(),
        "mice_message": str(aprs_data.get("mice_message") or "").strip(),
        "interface_id": int(row["interface_id"]) if row["interface_id"] is not None else None,
    }


def monitoring_public_snapshot() -> dict[str, Any]:
    station_settings = get_station_settings()
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    normalized_ssid = "" if ssid == "0" else ssid
    full_callsign = callsign if not (callsign and normalized_ssid) else f"{callsign}-{normalized_ssid}"

    traffic = traffic_snapshot(limit=0)
    runtime_by_modem_id: dict[int, dict[str, Any]] = {}
    for interface in traffic.get("interfaces") or []:
        modem_id = interface.get("modem_id")
        if isinstance(modem_id, int):
            runtime_by_modem_id[modem_id] = interface

    modem_rows = get_section_rows("modems")
    tnc_items: list[dict[str, Any]] = []
    for row in modem_rows:
        modem_id = int(row["id"])
        runtime = runtime_by_modem_id.get(modem_id)
        runtime_status = str((runtime or {}).get("status") or "").strip().lower()
        runtime_detail = str((runtime or {}).get("status_detail") or "").strip()
        if not runtime_status:
            runtime_status = "disabled" if not bool(row.get("enabled")) else "unknown"
        if not runtime_detail:
            runtime_detail = str(row.get("modem_runtime_title") or "").strip()
        tnc_items.append(
            {
                "id": modem_id,
                "name": str(row.get("name") or ""),
                "enabled": bool(row.get("enabled")),
                "modem_type": str(row.get("modem_type") or ""),
                "band": str(row.get("band") or ""),
                "device_path": str(row.get("device_path") or ""),
                "tx_blocked": bool(row.get("tx_blocked")),
                "runtime_status": runtime_status,
                "runtime_detail": runtime_detail,
                "runtime_last_error": str((runtime or {}).get("last_error") or "").strip() or None,
                "expose": {
                    "enabled": bool(row.get("expose_port_enabled")),
                    "bind_address": str(row.get("expose_bind_address") or ""),
                    "port": int(row["expose_port"]) if row.get("expose_port") is not None else None,
                    "active_clients": int(((runtime or {}).get("expose") or {}).get("active_clients") or 0),
                },
            }
        )

    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    hour_window_start_utc = (now_utc - timedelta(hours=1)).isoformat()
    hourly_rows = fetch_all(
        """
        SELECT
            COALESCE(modems.band, '') AS band,
            SUM(radio_activity_5m.rx_total) AS total_frames,
            SUM(radio_activity_5m.mobile_total) AS mobile_frames,
            SUM(radio_activity_5m.fixed_total) AS fixed_frames
        FROM radio_activity_5m
        LEFT JOIN modems ON modems.id = radio_activity_5m.interface_id
        WHERE radio_activity_5m.bucket_start_utc >= ?
          AND LOWER(TRIM(COALESCE(modems.band, ''))) IN ('2m', '70cm')
        GROUP BY modems.band
        ORDER BY modems.band ASC
        """,
        (hour_window_start_utc,),
    )
    hourly_by_band: list[dict[str, Any]] = []
    for row in hourly_rows:
        hourly_by_band.append(
            {
                "band": str(row["band"] or ""),
                "total_frames": int(row["total_frames"] or 0),
                "mobile_frames": int(row["mobile_frames"] or 0),
                "fixed_frames": int(row["fixed_frames"] or 0),
            }
        )
    hourly_total_frames = sum(item["total_frames"] for item in hourly_by_band)
    hourly_mobile_frames = sum(item["mobile_frames"] for item in hourly_by_band)
    hourly_fixed_frames = sum(item["fixed_frames"] for item in hourly_by_band)
    raw_hourly_row = fetch_one(
        f"""
        SELECT COUNT(*) AS total
        FROM traffic_frames
        WHERE created_at >= ?
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
        """,
        (hour_window_start_utc,),
    )
    raw_hourly_frames = int(raw_hourly_row["total"]) if raw_hourly_row else 0

    digi_total_row = fetch_one("SELECT COUNT(*) AS total FROM digi_rules")
    digi_enabled_row = fetch_one("SELECT COUNT(*) AS total FROM digi_rules WHERE is_enabled = 1")
    igate_total_row = fetch_one("SELECT COUNT(*) AS total FROM igate_rules")
    igate_enabled_row = fetch_one("SELECT COUNT(*) AS total FROM igate_rules WHERE is_enabled = 1")
    digi_total = int(digi_total_row["total"]) if digi_total_row else 0
    digi_enabled = int(digi_enabled_row["total"]) if digi_enabled_row else 0
    igate_total = int(igate_total_row["total"]) if igate_total_row else 0
    igate_enabled = int(igate_enabled_row["total"]) if igate_enabled_row else 0

    from app.services.wx import get_wx_config, get_wx_mapping_rows, list_wx_sources

    wx_config = get_wx_config()
    wx_sources = list_wx_sources()
    wx_mappings = get_wx_mapping_rows()
    wx_status_counts = {
        "live": sum(1 for row in wx_mappings if str(row.get("status") or "").upper() == "LIVE"),
        "cached": sum(1 for row in wx_mappings if str(row.get("status") or "").upper() == "CACHED"),
        "stale": sum(1 for row in wx_mappings if str(row.get("status") or "").upper() == "STALE"),
        "missing": sum(1 for row in wx_mappings if str(row.get("status") or "").upper() == "MISSING"),
        "error": sum(1 for row in wx_mappings if str(row.get("status") or "").upper() == "ERROR"),
    }

    station_unit_system = str(station_settings.get("default_units") or "metric") or "metric"
    stations = heard_stations(unit_system=station_unit_system)
    stations_summary = station_summary(get_rf_heard_station_snapshots())
    traffic_monitor_status = str(traffic.get("status") or "").strip().lower()
    traffic_monitor_detail = str(traffic.get("status_detail") or "").strip()
    runtime_interfaces = list(runtime_by_modem_id.values())
    if runtime_interfaces and traffic_monitor_status in {"", "idle"}:
        runtime_connected = [item for item in runtime_interfaces if str(item.get("status") or "").strip().lower() in {"connected", "running", "idle"}]
        runtime_connecting = [item for item in runtime_interfaces if str(item.get("status") or "").strip().lower() == "connecting"]
        runtime_error = [item for item in runtime_interfaces if str(item.get("status") or "").strip().lower() == "error"]
        if runtime_connected:
            traffic_monitor_status = "connected"
            traffic_monitor_detail = f"{len(runtime_connected)}/{len(runtime_interfaces)} interfaces connected."
        elif runtime_connecting:
            traffic_monitor_status = "connecting"
            traffic_monitor_detail = f"Connecting {len(runtime_connecting)} interface(s)."
        elif runtime_error:
            traffic_monitor_status = "error"
            traffic_monitor_detail = str(runtime_error[0].get("last_error") or runtime_error[0].get("status_detail") or "Interface runtime error.")
        elif not traffic_monitor_status:
            traffic_monitor_status = "idle"

    return {
        "generated_at": utc_now(),
        "station": {
            "callsign": callsign,
            "ssid": normalized_ssid,
            "full_callsign": full_callsign,
            "beacon_interface_id": station_settings.get("beacon_interface_id"),
            "beacon_tx_scope": normalize_tx_scope(station_settings.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE),
            "tx_enabled": bool(station_settings.get("tx_enabled")),
            "status_enabled": bool(station_settings.get("status_enabled")),
        },
        "tnc": {
            "total": len(tnc_items),
            "enabled": sum(1 for item in tnc_items if item["enabled"]),
            "runtime_connected": sum(1 for item in tnc_items if item["runtime_status"] in {"connected", "running", "idle"}),
            "runtime_connecting": sum(1 for item in tnc_items if item["runtime_status"] == "connecting"),
            "runtime_error": sum(1 for item in tnc_items if item["runtime_status"] == "error"),
            "items": tnc_items,
        },
        "services": {
            "traffic_monitor": {
                "status": traffic_monitor_status,
                "status_detail": traffic_monitor_detail,
                "updated_at": traffic.get("updated_at"),
                "active_modem": traffic.get("active_modem"),
            },
            "digi": {
                "configured_rules": digi_total,
                "enabled_rules": digi_enabled,
            },
            "igate": {
                "configured_rules": igate_total,
                "enabled_rules": igate_enabled,
            },
        },
        "wx": {
            "enabled": bool(wx_config.get("enabled")),
            "ssid": str(wx_config.get("ssid") or "").strip(),
            "beacon_interface_id": wx_config.get("beacon_interface_id"),
            "beacon_tx_scope": normalize_tx_scope(wx_config.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE),
            "path": str(wx_config.get("path") or "").strip(),
            "latitude": str(wx_config.get("latitude") or "").strip(),
            "longitude": str(wx_config.get("longitude") or "").strip(),
            "configured": bool(
                str(wx_config.get("ssid") or "").strip()
                or wx_config.get("beacon_interface_id") not in {None, ""}
                or str(wx_config.get("latitude") or "").strip()
                or str(wx_config.get("longitude") or "").strip()
                or str(wx_config.get("path") or "").strip()
            ),
            "sources_total": len(wx_sources),
            "sources_enabled": sum(1 for source in wx_sources if bool(source.get("enabled"))),
            "mappings_total": len(wx_mappings),
            "mappings_enabled": sum(1 for row in wx_mappings if bool(row.get("enabled"))),
            "mapping_status": wx_status_counts,
        },
        "stats": {
            "stations": {
                "total": int(stations_summary.get("total") or 0),
                "stationary": int(stations_summary.get("stationary") or 0),
                "mobile": int(stations_summary.get("mobile") or 0),
                "objects": int(stations_summary.get("objects") or 0),
            },
            "frames_last_hour": {
                "window_start_utc": hour_window_start_utc,
                "window_end_utc": now_utc.isoformat(),
                "total_frames": hourly_total_frames,
                "mobile_frames": hourly_mobile_frames,
                "fixed_frames": hourly_fixed_frames,
                "raw_frames": raw_hourly_frames,
                "by_band": hourly_by_band,
            },
        },
    }


def _build_source_key(callsign: Any, ssid: Any) -> str:
    callsign_text = str(callsign or "").strip().upper()
    ssid_text = str(ssid or "").strip()
    if ssid_text == "0":
        ssid_text = ""
    if not callsign_text:
        return ""
    return f"{callsign_text}-{ssid_text}" if ssid_text else callsign_text


def _station_source_key(station_settings: dict[str, Any]) -> str:
    return _build_source_key(
        station_settings.get("callsign"),
        station_settings.get("ssid"),
    )


def _traffic_frame_row_class(
    *,
    direction: str,
    line: str,
    command: str,
    station_source_key: str,
    wx_source_key: str = "",
    source_kind: str = RF_SOURCE_KIND,
) -> str:
    classes: list[str] = []
    normalized_direction = str(direction or "").strip().upper()
    normalized_command = str(command or "").strip().upper()
    normalized_source_kind = normalize_source_kind(source_kind)
    is_skipped_tx = normalized_direction == "TX" and normalized_command.startswith("TX-SKIP")
    is_proxy_tx = normalized_direction == "TX" and normalized_command.startswith("TX-PROXY")
    if is_skipped_tx:
        classes.append("traffic-log-row-skipped")

    parsed = parse_tnc2_frame(line)
    if parsed is None:
        return " ".join(classes)

    source_key = str(parsed.get("source_key") or "").strip().upper()
    if not source_key:
        return " ".join(classes)

    station_source_key = str(station_source_key or "").strip().upper()
    wx_source_key = str(wx_source_key or "").strip().upper()
    station_callsign = station_source_key.partition("-")[0]
    source_callsign = str(parsed.get("source_callsign") or "").strip().upper()

    aprs_data = parsed.get("aprs_data") or {}
    info_field = str(parsed.get("logical_info") or parsed.get("info") or "")
    packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
    symbol = str(aprs_data.get("symbol") or "").strip()
    is_weather = packet_group == "weather" or symbol.endswith("_")
    is_position_like = packet_group in {"position", "status", "object", "item"} and not is_weather
    is_message_like = packet_group in {"message", "query", "telemetry"} or (not packet_group and info_field.startswith("?"))
    is_own_station_source = bool(station_source_key) and source_key == station_source_key
    is_own_wx_source = bool(wx_source_key) and source_key == wx_source_key
    is_own_callsign = bool(station_callsign) and source_callsign == station_callsign

    if normalized_direction == "TX":
        if is_proxy_tx:
            classes.append("traffic-log-row-proxy-tx")
        elif normalized_source_kind == APRSIS_TO_RF_SOURCE_KIND:
            classes.append("traffic-log-row-aprsis-to-rf-tx")
        elif (is_own_wx_source or is_own_callsign) and is_weather:
            classes.append("traffic-log-row-own-wx-tx")
        elif is_own_station_source:
            if is_position_like:
                classes.append("traffic-log-row-own-beacon-tx")
            elif is_message_like:
                classes.append("traffic-log-row-own-message-tx")
            else:
                classes.append("traffic-log-row-own-beacon-tx")
        elif source_key:
            classes.append("traffic-log-row-repeated-tx")
    elif normalized_direction == "RX":
        if normalized_source_kind == APRSIS_SOURCE_KIND:
            classes.append("traffic-log-row-aprsis-rx")
        elif (is_own_wx_source or is_own_callsign) and is_weather:
            classes.append("traffic-log-row-own-wx-rx")
        elif is_own_station_source:
            if is_position_like:
                classes.append("traffic-log-row-own-beacon-rx")
            elif is_message_like:
                classes.append("traffic-log-row-own-message-rx")
            else:
                classes.append("traffic-log-row-own-beacon-rx")

    return " ".join(classes)


def _format_monitor_timestamp(timestamp: str | None) -> str:
    if not timestamp:
        return "-"
    formatted = format_display_datetime(timestamp)
    return formatted or "-"


def dashboard_traffic_summary(*, heard_snapshots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=DASHBOARD_KPI_WINDOW_HOURS)
    cutoff_iso = cutoff_utc.isoformat()
    traffic_row = fetch_one(
        f"""
        SELECT
            COUNT(*) AS total_frames,
            COALESCE(SUM(CASE WHEN format = 'TNC2' THEN 1 ELSE 0 END), 0) AS decoded_frames,
            COUNT(DISTINCT CASE WHEN COALESCE(source, '') <> '' THEN source END) AS unique_sources
        FROM traffic_frames
        WHERE {STATISTICS_TRAFFIC_SQL_PREDICATE}
          AND created_at >= ?
        """,
        (cutoff_iso,),
    )
    snapshots = heard_snapshots if heard_snapshots is not None else get_rf_heard_station_snapshots()
    heard_stations = 0
    for snapshot in snapshots:
        last_heard_at = _parse_iso_timestamp_utc(
            str(snapshot.get("last_heard_rf_at") or snapshot.get("last_heard_at") or "")
        )
        if last_heard_at is not None and last_heard_at >= cutoff_utc:
            heard_stations += 1

    return {
        "received_frames": traffic_row["total_frames"] if traffic_row else 0,
        "decoded_aprs": traffic_row["decoded_frames"] if traffic_row else 0,
        "unique_sources": traffic_row["unique_sources"] if traffic_row else 0,
        "heard_stations": heard_stations,
        "window_hours": DASHBOARD_KPI_WINDOW_HOURS,
    }


def dashboard_activity_series(
    *,
    window_minutes: int = DASHBOARD_ACTIVITY_WINDOW_MINUTES,
    bucket_minutes: int = DASHBOARD_ACTIVITY_BUCKET_MINUTES,
) -> dict[str, Any]:
    normalized_bucket_minutes = max(1, int(bucket_minutes or DASHBOARD_ACTIVITY_BUCKET_MINUTES))
    normalized_window_minutes = max(normalized_bucket_minutes, int(window_minutes or DASHBOARD_ACTIVITY_WINDOW_MINUTES))
    bucket_count = max(1, math.ceil(normalized_window_minutes / normalized_bucket_minutes))

    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    rounded_minute = (now_utc.minute // normalized_bucket_minutes) * normalized_bucket_minutes
    current_bucket_start = now_utc.replace(minute=rounded_minute)
    first_bucket_start = current_bucket_start - timedelta(minutes=normalized_bucket_minutes * (bucket_count - 1))

    bucket_starts = [first_bucket_start + timedelta(minutes=normalized_bucket_minutes * index) for index in range(bucket_count)]
    labels = [bucket_start.strftime("%H:%M") for bucket_start in bucket_starts]
    series = {
        "total": [0] * bucket_count,
        "mobile": [0] * bucket_count,
        "message": [0] * bucket_count,
        "query": [0] * bucket_count,
        "rx": [0] * bucket_count,
        "tx": [0] * bucket_count,
        "repeated_tx": [0] * bucket_count,
    }

    station_settings = get_station_settings()
    station_source_key = _station_source_key(station_settings)
    from app.services.wx import get_wx_config

    wx_config = get_wx_config()
    wx_source_key = _build_source_key(wx_config.get("callsign"), wx_config.get("ssid"))

    frame_rows = fetch_all(
        f"""
        SELECT created_at, direction, format, line, command
        FROM traffic_frames
        WHERE created_at >= ?
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
        ORDER BY created_at ASC, id ASC
        """,
        (first_bucket_start.isoformat(),),
    )
    bucket_size_seconds = normalized_bucket_minutes * 60

    for row in frame_rows:
        created_at_raw = str(row["created_at"] or "").strip()
        created_at = _parse_iso_timestamp_utc(created_at_raw)
        if created_at is None:
            continue
        delta_seconds = (created_at - first_bucket_start).total_seconds()
        if delta_seconds < 0:
            continue
        bucket_index = int(delta_seconds // bucket_size_seconds)
        if bucket_index < 0 or bucket_index >= bucket_count:
            continue

        direction = str(row["direction"] or "").strip().upper()
        frame_format = str(row["format"] or "").strip().upper()
        if direction not in {"RX", "TX"}:
            direction = "TX" if frame_format.endswith("-TX") else "RX"

        series["total"][bucket_index] += 1
        if direction == "RX":
            series["rx"][bucket_index] += 1
        elif direction == "TX":
            series["tx"][bucket_index] += 1

        line = str(row["line"] or "")
        command = str(row["command"] or "")
        parsed = parse_tnc2_frame(line)
        aprs_data = parsed.get("aprs_data") if parsed else {}
        packet_group = str((aprs_data or {}).get("packet_group") or "").strip().lower()
        frame_type = str((aprs_data or {}).get("frame_type") or "").strip().upper()

        if frame_type == "M":
            series["mobile"][bucket_index] += 1
        if packet_group == "message":
            series["message"][bucket_index] += 1
        elif packet_group == "query":
            series["query"][bucket_index] += 1

        if direction == "TX":
            row_class = _traffic_frame_row_class(
                direction=direction,
                line=line,
                command=command,
                station_source_key=station_source_key,
                wx_source_key=wx_source_key,
            )
            if "traffic-log-row-repeated-tx" in row_class.split():
                series["repeated_tx"][bucket_index] += 1

    return {
        "bucket_minutes": normalized_bucket_minutes,
        "window_minutes": normalized_bucket_minutes * bucket_count,
        "window_start_utc": first_bucket_start.isoformat(),
        "window_end_utc": (current_bucket_start + timedelta(minutes=normalized_bucket_minutes)).isoformat(),
        "labels": labels,
        "series": series,
        "totals": {key: int(sum(values)) for key, values in series.items()},
    }


def _dashboard_activity_series_from_aggregated(activity: dict[str, Any]) -> dict[str, Any]:
    """Adapt the persisted radio-activity projection to the legacy dashboard chart contract."""
    labels = list(activity.get("labels") or [])
    source_series = dict(activity.get("series") or {})
    point_count = len(labels)

    def values(key: str) -> list[int]:
        raw_values = list(source_series.get(key) or [])
        return [int(raw_values[index] or 0) if index < len(raw_values) else 0 for index in range(point_count)]

    rx_values = values("rx_total")
    tx_values = values("tx_total")
    series = {
        "total": [rx_values[index] + tx_values[index] for index in range(point_count)],
        "mobile": values("mobile_total"),
        "message": values("messages_total"),
        "query": values("queries_total"),
        "rx": rx_values,
        "tx": tx_values,
        "repeated_tx": values("digipeated_total"),
    }
    bucket_minutes = max(1, int(activity.get("output_bucket_minutes") or DASHBOARD_ACTIVITY_BUCKET_MINUTES))
    return {
        "bucket_minutes": bucket_minutes,
        "window_minutes": int(activity.get("range_minutes") or bucket_minutes * point_count),
        "window_start_utc": str(activity.get("window_start_utc") or ""),
        "window_end_utc": str(activity.get("window_end_utc") or ""),
        "labels": labels,
        "series": series,
        "totals": {key: int(sum(series_values)) for key, series_values in series.items()},
    }


def recent_alert_logs(limit: int = 5) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, level, category, message, created_at
        FROM event_logs
        WHERE level IN ('WARNING', 'ERROR')
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(row) for row in rows]


def has_enabled_digi_rf_to_rf_flow() -> bool:
    row = fetch_one(
        """
        SELECT 1
        FROM digi_flows
        WHERE enabled = 1
          AND source_kind = 'receiver_rf'
          AND target_kind = 'tx_rf'
        LIMIT 1
        """
    )
    return row is not None


def _dashboard_age_seconds(timestamp: str | None) -> int | None:
    parsed = _parse_iso_timestamp_utc(str(timestamp or "").strip())
    if parsed is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def _dashboard_last_rf_rx_at() -> str | None:
    row = fetch_one(
        f"""
        SELECT MAX(rx_at) AS created_at
        FROM (
            SELECT rx_at
            FROM (
                SELECT created_at AS rx_at
                FROM traffic_frames
                WHERE CASE
                        WHEN UPPER(TRIM(COALESCE(direction, ''))) IN ('RX', 'TX')
                            THEN UPPER(TRIM(direction))
                        WHEN UPPER(TRIM(COALESCE(format, ''))) LIKE '%-TX'
                            THEN 'TX'
                        ELSE 'RX'
                    END = 'RX'
                  AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            )

            UNION ALL

            SELECT rx_at
            FROM (
                SELECT bucket_end_utc AS rx_at
                FROM radio_activity_5m
                WHERE rx_total > 0
                ORDER BY bucket_start_utc DESC
                LIMIT 1
            )
        )
        """
    )
    if row is None:
        return None
    return str(row["created_at"] or "").strip() or None


def _dashboard_last_rf_tx_at() -> str | None:
    row = fetch_one(
        f"""
        SELECT created_at
        FROM traffic_frames
        WHERE (
            UPPER(COALESCE(direction, '')) = 'TX'
            OR UPPER(COALESCE(format, '')) LIKE '%-TX'
        )
          AND UPPER(COALESCE(command, '')) NOT LIKE 'TX-SKIP%'
          AND {STATISTICS_TRAFFIC_SQL_PREDICATE}
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    )
    if row is None:
        return None
    return str(row["created_at"] or "").strip() or None


def _dashboard_recent_important_events(limit: int = 6) -> list[dict[str, str]]:
    rows = fetch_all(
        """
        SELECT level, category, message, created_at
        FROM event_logs
        WHERE category IN ('traffic', 'outbound', 'aprsis', 'wx')
        ORDER BY id DESC
        LIMIT 180
        """
    )
    events: list[dict[str, str]] = []
    for row in rows:
        level = str(row["level"] or "").strip().upper()
        category = str(row["category"] or "").strip().lower()
        message = str(row["message"] or "").strip()
        if not message:
            continue
        lower_message = message.lower()
        is_relevant = False
        if level in {"WARNING", "ERROR"}:
            is_relevant = True
        elif category == "aprsis":
            is_relevant = "connected aprs-is uplink" in lower_message or "aprs-is" in lower_message
        elif category == "outbound":
            is_relevant = (
                "scheduler" in lower_message
                or ("sent" in lower_message and "outbound job" in lower_message)
                or "skipped" in lower_message
                or "failed" in lower_message
                or "queued" in lower_message
            )
        elif category == "wx":
            is_relevant = "scheduler" in lower_message or "sent wx" in lower_message or "skipped wx" in lower_message
        elif category == "traffic":
            is_relevant = "connect" in lower_message or "error" in lower_message or "failed" in lower_message
        if not is_relevant:
            continue
        if level == "ERROR":
            tone = "error"
            level_label = "Error"
        elif level == "WARNING":
            tone = "warn"
            level_label = "Warning"
        else:
            tone = "ok"
            level_label = "Info"
        events.append(
            {
                "level": level_label,
                "tone": tone,
                "message": message,
                "timestamp": _format_monitor_timestamp(str(row["created_at"] or "")),
            }
        )
        if len(events) >= limit:
            break
    return events


def dashboard_home_data(
    dashboard_band: dict[str, Any] | None = None,
    dashboard_activity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.aprsis import get_aprsis_runtime_status, has_enabled_aprsis_target_flow
    from app.services.map_station_state import read_map_station_rf_snapshots
    from app.services.wx import get_wx_config

    station_settings = get_station_settings()
    heard_snapshots = prepare_station_snapshots_for_display(
        read_map_station_rf_snapshots(),
        station_settings=station_settings,
    )
    traffic = dashboard_traffic_summary(heard_snapshots=heard_snapshots)
    interfaces = get_configured_modem_interfaces()
    enabled_interfaces = [item for item in interfaces if item.get("enabled")]
    disabled_interfaces_count = max(0, len(interfaces) - len(enabled_interfaces))

    runtime_rows = fetch_all(
        """
        SELECT modem_id, status, status_detail, last_error
        FROM traffic_runtime_interfaces
        """
    )
    runtime_by_modem_id: dict[int, dict[str, Any]] = {}
    for row in runtime_rows:
        if row["modem_id"] is None:
            continue
        try:
            runtime_by_modem_id[int(row["modem_id"])] = dict(row)
        except (TypeError, ValueError):
            continue

    recent_tx_jobs = recent_station_outbound_jobs(limit=5)
    latest_station_tx_at = None
    latest_station_tx_display = "No RF TX yet"
    if recent_tx_jobs:
        latest_tx = recent_tx_jobs[0]
        latest_station_tx_at = str(latest_tx.get("display_time") or "").strip() or None
        latest_tx_time = _format_monitor_timestamp(str(latest_tx.get("display_time") or ""))
        if latest_tx_time and latest_tx_time != "-":
            latest_station_tx_display = latest_tx_time

    callsign = str(station_settings.get("callsign") or "").strip().upper()
    station_ssid = str(station_settings.get("ssid") or "").strip()
    normalized_station_ssid = "" if station_ssid == "0" else station_ssid
    main_callsign = callsign if not (callsign and normalized_station_ssid) else f"{callsign}-{normalized_station_ssid}"

    wx_config = get_wx_config()
    wx_callsign = str(wx_config.get("full_callsign") or "").strip().upper()
    digi_routine_enabled = has_enabled_digi_rf_to_rf_flow()
    igate_enabled = has_enabled_aprsis_target_flow()
    aprsis_interfaces = [
        item
        for item in interfaces
        if str(item.get("modem_type") or "").strip().upper() == APRSIS_MODEM_TYPE
    ]
    enabled_aprsis_interfaces = [item for item in aprsis_interfaces if item.get("enabled")]
    aprsis_runtime = get_aprsis_runtime_status() if enabled_aprsis_interfaces else {}
    aprsis_runtime_status = str((aprsis_runtime or {}).get("status") or "").strip().lower()
    location_configured = bool(station_settings.get("latitude")) and bool(station_settings.get("longitude"))

    interface_entries: list[dict[str, str]] = []
    any_interface_error = False
    interface_connecting = 0
    for interface in interfaces:
        try:
            interface_id = int(interface.get("id"))
        except (TypeError, ValueError):
            continue
        interface_name = str(interface.get("name") or "").strip() or f"#{interface_id}"
        runtime = runtime_by_modem_id.get(interface_id)
        runtime_status = str((runtime or {}).get("status") or "").strip().lower()
        runtime_error = str((runtime or {}).get("last_error") or "").strip()
        enabled = bool(interface.get("enabled"))
        if not enabled:
            status_label = "Disabled"
            status_tone = "neutral"
        elif runtime_error or runtime_status == "error":
            status_label = "Error"
            status_tone = "error"
            any_interface_error = True
        elif runtime_status == "connecting":
            status_label = "Connecting"
            status_tone = "warn"
            interface_connecting += 1
        elif runtime_status in {"connected", "running", "idle"}:
            status_label = "Enabled"
            status_tone = "ok"
        elif runtime_status in {"disabled", "stopped"}:
            status_label = "Disabled"
            status_tone = "neutral"
        elif runtime_status:
            status_label = "Unknown"
            status_tone = "warn"
        else:
            status_label = "Unknown"
            status_tone = "warn"
        interface_entries.append(
            {
                "name": interface_name,
                "status": status_label,
                "tone": status_tone,
                "enabled": "1" if enabled else "0",
            }
        )
    interface_entries.sort(key=lambda item: (item.get("enabled") != "1", str(item.get("name") or "").casefold()))

    if not interfaces:
        interface_summary = "No interfaces configured"
    else:
        interface_summary = f"{len(enabled_interfaces)} enabled / {disabled_interfaces_count} disabled"
        if any_interface_error:
            interface_summary = f"{interface_summary} • runtime error detected"
        elif interface_connecting > 0:
            interface_summary = f"{interface_summary} • connecting {interface_connecting}"

    last_rf_rx_at = _dashboard_last_rf_rx_at()
    last_rf_tx_at = _dashboard_last_rf_tx_at()
    if last_rf_tx_at is None and latest_station_tx_at:
        last_rf_tx_at = latest_station_tx_at
    last_rf_rx_display = _format_monitor_timestamp(last_rf_rx_at) if last_rf_rx_at else "No RF RX yet"
    last_rf_tx_display = _format_monitor_timestamp(last_rf_tx_at) if last_rf_tx_at else "No RF TX yet"
    last_rf_rx_age_s = _dashboard_age_seconds(last_rf_rx_at)
    last_rf_tx_age_s = _dashboard_age_seconds(last_rf_tx_at)

    if not enabled_interfaces:
        rx_runtime_status = "No enabled interfaces"
        rx_runtime_tone = "neutral"
    elif last_rf_rx_age_s is None:
        rx_runtime_status = "No RF RX yet"
        rx_runtime_tone = "warn"
    elif last_rf_rx_age_s <= 15 * 60:
        rx_runtime_status = "Fresh"
        rx_runtime_tone = "ok"
    else:
        rx_runtime_status = "Stale"
        rx_runtime_tone = "warn"

    tx_enabled_flag = bool(station_settings.get("tx_enabled"))
    if not tx_enabled_flag:
        tx_runtime_status = "TX disabled"
        tx_runtime_tone = "neutral"
    elif not enabled_interfaces:
        tx_runtime_status = "No enabled interfaces"
        tx_runtime_tone = "neutral"
    elif last_rf_tx_age_s is None:
        tx_runtime_status = "No RF TX yet"
        tx_runtime_tone = "warn"
    elif last_rf_tx_age_s <= 60 * 60:
        tx_runtime_status = "Fresh"
        tx_runtime_tone = "ok"
    else:
        tx_runtime_status = "Stale"
        tx_runtime_tone = "warn"

    aprsis_last_sent_row = fetch_one("SELECT last_sent_at FROM aprsis_uplink_stats WHERE id = 1")
    aprsis_last_sent_at = str(aprsis_last_sent_row["last_sent_at"] or "").strip() if aprsis_last_sent_row is not None else ""
    aprsis_last_sent_at = aprsis_last_sent_at or None
    aprsis_last_sent_display = _format_monitor_timestamp(aprsis_last_sent_at) if aprsis_last_sent_at else "No APRS-IS uplink yet"
    aprsis_last_sent_age_s = _dashboard_age_seconds(aprsis_last_sent_at)
    if not igate_enabled:
        aprsis_runtime_label = "Not configured"
        aprsis_runtime_tone = "neutral"
    elif aprsis_runtime_status == "connected" and aprsis_last_sent_age_s is not None and aprsis_last_sent_age_s <= 60 * 60:
        aprsis_runtime_label = "Connected"
        aprsis_runtime_tone = "ok"
    elif aprsis_runtime_status == "connecting":
        aprsis_runtime_label = "Connecting"
        aprsis_runtime_tone = "warn"
    elif aprsis_runtime_status == "error":
        aprsis_runtime_label = "Error"
        aprsis_runtime_tone = "error"
    elif aprsis_last_sent_age_s is None:
        aprsis_runtime_label = "No APRS-IS uplink yet"
        aprsis_runtime_tone = "warn"
    else:
        aprsis_runtime_label = "Stale"
        aprsis_runtime_tone = "warn"

    queue_row = fetch_one(
        """
        SELECT
            COALESCE(SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END), 0) AS queued_total,
            COALESCE(SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END), 0) AS processing_total
        FROM outbound_jobs
        WHERE status IN ('queued', 'processing')
        """
    )
    queued_total = int(queue_row["queued_total"] or 0) if queue_row is not None else 0
    processing_total = int(queue_row["processing_total"] or 0) if queue_row is not None else 0
    if processing_total > 0:
        queue_status_label = f"Processing ({processing_total})"
        queue_status_key = "Processing ({count})"
        queue_status_params: dict[str, object] = {"count": processing_total}
        queue_status_tone = "ok"
    elif queued_total == 0:
        queue_status_label = "Idle"
        queue_status_key = "Idle"
        queue_status_params = {}
        queue_status_tone = "ok"
    elif queued_total <= 3:
        queue_status_label = f"Queued ({queued_total})"
        queue_status_key = "Queued ({count})"
        queue_status_params = {"count": queued_total}
        queue_status_tone = "ok"
    else:
        queue_status_label = f"Backlog ({queued_total})"
        queue_status_key = "Backlog ({count})"
        queue_status_params = {"count": queued_total}
        queue_status_tone = "warn"

    scheduler_row = fetch_one(
        """
        SELECT level, created_at
        FROM event_logs
        WHERE category IN ('outbound', 'wx')
          AND message LIKE '%scheduler%'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    if scheduler_row is None:
        scheduler_status_label = "No scheduler events yet"
        scheduler_status_key = "No scheduler events yet"
        scheduler_status_params: dict[str, object] = {}
        scheduler_status_tone = "neutral"
    else:
        scheduler_level = str(scheduler_row["level"] or "").strip().upper()
        scheduler_time = _format_monitor_timestamp(str(scheduler_row["created_at"] or ""))
        if scheduler_level == "ERROR":
            scheduler_status_label = f"Error at {scheduler_time}"
            scheduler_status_key = "Error at {time}"
            scheduler_status_params = {"time": scheduler_time}
            scheduler_status_tone = "error"
        elif scheduler_level == "WARNING":
            scheduler_status_label = f"Warning at {scheduler_time}"
            scheduler_status_key = "Warning at {time}"
            scheduler_status_params = {"time": scheduler_time}
            scheduler_status_tone = "warn"
        else:
            scheduler_status_label = f"Active at {scheduler_time}"
            scheduler_status_key = "Active at {time}"
            scheduler_status_params = {"time": scheduler_time}
            scheduler_status_tone = "ok"

    database_ready = fetch_one("SELECT 1 AS ok") is not None
    database_status_label = "Available" if database_ready else "Unavailable"
    database_status_tone = "ok" if database_ready else "error"

    runtime_entries = [
        {"name": "RF RX freshness", "status": rx_runtime_status, "tone": rx_runtime_tone},
        {"name": "RF TX freshness", "status": tx_runtime_status, "tone": tx_runtime_tone},
        {"name": "APRS-IS/iGate uplink", "status": aprsis_runtime_label, "tone": aprsis_runtime_tone},
        {
            "name": "TX queue",
            "status": queue_status_label,
            "status_key": queue_status_key,
            "status_params": queue_status_params,
            "tone": queue_status_tone,
        },
        {
            "name": "Schedulers",
            "status": scheduler_status_label,
            "status_key": scheduler_status_key,
            "status_params": scheduler_status_params,
            "tone": scheduler_status_tone,
        },
        {"name": "Database", "status": database_status_label, "tone": database_status_tone},
    ]
    runtime_check_state = "ok"
    if any(item["tone"] == "error" for item in runtime_entries):
        runtime_check_state = "error"
    elif any(item["tone"] == "warn" for item in runtime_entries):
        runtime_check_state = "warn"

    config_entries = [
        {
            "name": "Main callsign",
            "status": "Configured" if main_callsign else "Not set",
            "tone": "ok" if main_callsign else "warn",
        },
        {
            "name": "WX callsign",
            "status": "Configured" if wx_callsign else "Not set",
            "tone": "ok" if wx_callsign else "neutral",
        },
        {
            "name": "Location",
            "status": "Configured" if location_configured else "Missing coordinates",
            "tone": "ok" if location_configured else "warn",
        },
    ]
    configuration_ready = bool(main_callsign) and location_configured
    configuration_state = "ok" if configuration_ready else "warn"

    service_entries = [
        {
            "name": "Beacon enabled",
            "status": "Enabled" if tx_enabled_flag else "Disabled",
            "tone": "ok" if tx_enabled_flag else "neutral",
        },
        {
            "name": "Status enabled",
            "status": "Enabled" if bool(station_settings.get("status_enabled")) else "Disabled",
            "tone": "ok" if bool(station_settings.get("status_enabled")) else "neutral",
        },
        {
            "name": "WX enabled",
            "status": "Enabled" if bool(wx_config.get("enabled")) else "Disabled",
            "tone": "ok" if bool(wx_config.get("enabled")) else "neutral",
        },
        {
            "name": "Digi routine",
            "status": "Enabled" if digi_routine_enabled else "Disabled",
            "tone": "ok" if digi_routine_enabled else "neutral",
        },
        {
            "name": "iGate enabled",
            "status": "Enabled" if igate_enabled else "Disabled",
            "tone": "ok" if igate_enabled else "neutral",
        },
    ]

    enabled_flow_rows = [dict(row) for row in fetch_all(
        """
        SELECT id, source_kind, source_ref, target_kind, target_ref
        FROM digi_flows
        WHERE enabled = 1
        """
    )]
    radio_interfaces = [
        item
        for item in interfaces
        if str(item.get("modem_type") or "").strip().upper() in RX_CAPABLE_MODEM_TYPES
    ]
    active_radio_interfaces = [item for item in radio_interfaces if item.get("enabled")]
    active_tx_interface_names = {
        str(item.get("name") or "").strip()
        for item in active_radio_interfaces
        if str(item.get("modem_type") or "").strip().upper() in TX_CAPABLE_MODEM_TYPES
        and str(item.get("name") or "").strip()
    }
    enabled_aprsis_interface_names = {
        str(item.get("name") or "").strip()
        for item in enabled_aprsis_interfaces
        if str(item.get("name") or "").strip()
    }

    def has_flow(
        *,
        source_kind: str,
        source_ref: str | None = None,
        target_kind: str,
        target_ref: str | None = None,
    ) -> bool:
        return any(
            str(flow.get("source_kind") or "") == source_kind
            and (source_ref is None or str(flow.get("source_ref") or "") == source_ref)
            and str(flow.get("target_kind") or "") == target_kind
            and (target_ref is None or str(flow.get("target_ref") or "") == target_ref)
            for flow in enabled_flow_rows
        )

    local_tx_aprsis_ready = has_flow(
        source_kind="receiver_local_tx",
        source_ref="local_tx",
        target_kind="tx_aprsis",
    )
    beacon_defined = bool(tx_enabled_flag and main_callsign and location_configured)
    aprsis_connection_tone = "warn"
    aprsis_connection_status = "Not configured"
    if enabled_aprsis_interfaces:
        if aprsis_runtime_status == "connected":
            aprsis_connection_tone = "ok"
            aprsis_connection_status = "Connected"
        elif aprsis_runtime_status == "error":
            aprsis_connection_tone = "error"
            aprsis_connection_status = "Error"
        elif aprsis_runtime_status == "connecting":
            aprsis_connection_status = "Connecting"
        else:
            aprsis_connection_status = "Needs attention"

    readiness_interfaces: list[dict[str, Any]] = []
    for interface in radio_interfaces:
        interface_name = str(interface.get("name") or "").strip()
        is_active = bool(interface.get("enabled"))
        is_tx_capable = str(interface.get("modem_type") or "").strip().upper() in TX_CAPABLE_MODEM_TYPES
        to_aprsis = is_active and has_flow(
            source_kind="receiver_rf",
            source_ref=interface_name,
            target_kind="tx_aprsis",
        )
        from_aprsis = is_active and is_tx_capable and any(
            has_flow(
                source_kind="receiver_aprsis",
                source_ref=aprsis_name,
                target_kind="tx_rf",
                target_ref=interface_name,
            )
            for aprsis_name in enabled_aprsis_interface_names
        )
        rf_target_count = sum(
            1
            for target_name in active_tx_interface_names
            if has_flow(
                source_kind="receiver_rf",
                source_ref=interface_name,
                target_kind="tx_rf",
                target_ref=target_name,
            )
        ) if is_active else 0
        rf_target_total = len(active_tx_interface_names) if is_active else 0
        readiness_interfaces.append(
            {
                "name": interface_name,
                "enabled": is_active,
                "tx_capable": is_tx_capable,
                "to_aprsis": to_aprsis,
                "from_aprsis": from_aprsis,
                "rf_target_count": rf_target_count,
                "rf_target_total": rf_target_total,
                "rf_ready": bool(rf_target_total and rf_target_count == rf_target_total),
            }
        )

    readiness_required_states = [
        aprsis_connection_tone == "ok",
        local_tx_aprsis_ready,
        bool(active_radio_interfaces),
        beacon_defined,
    ]
    for interface in readiness_interfaces:
        if not interface["enabled"]:
            continue
        readiness_required_states.extend([bool(interface["to_aprsis"]), bool(interface["rf_ready"])])
        if interface["tx_capable"]:
            readiness_required_states.append(bool(interface["from_aprsis"]))
    if len(active_radio_interfaces) == len(radio_interfaces) and radio_interfaces:
        radio_interfaces_tone = "ok"
    elif active_radio_interfaces:
        radio_interfaces_tone = "partial"
    else:
        radio_interfaces_tone = "error"
    readiness_tone = "ok" if all(readiness_required_states) and radio_interfaces_tone == "ok" else "warn"
    if aprsis_connection_tone == "error" or radio_interfaces_tone == "error":
        readiness_tone = "error"
    station_readiness = {
        "tone": readiness_tone,
        "overview": [
            {"label": "APRS-IS connection", "status": aprsis_connection_status, "tone": aprsis_connection_tone},
            {
                "label": "Local TX → APRS-IS",
                "status": "Configured" if local_tx_aprsis_ready else "Missing",
                "tone": "ok" if local_tx_aprsis_ready else "warn",
            },
            {
                "label": "Radio interfaces",
                "status_key": "{active} / {total} active",
                "status_params": {"active": len(active_radio_interfaces), "total": len(radio_interfaces)},
                "tone": radio_interfaces_tone,
            },
            {
                "label": "Beacon defined",
                "status": "Configured" if beacon_defined else "Missing",
                "tone": "ok" if beacon_defined else "warn",
            },
        ],
        "interfaces": readiness_interfaces,
    }

    checks = [
        {
            "label": "Runtime readiness",
            "state": runtime_check_state,
            "entries": runtime_entries,
            "show_state_badge": True,
            "blocks": runtime_check_state == "error",
            "note": "Runtime checks are evaluated from recent activity and current runtime state.",
        },
        {
            "label": "Configuration checklist",
            "state": configuration_state,
            "entries": config_entries,
            "show_state_badge": False,
            "blocks": not configuration_ready,
        },
        {
            "label": "Enabled services",
            "state": "ok",
            "entries": service_entries,
            "show_state_badge": False,
            "blocks": False,
        },
    ]
    next_steps = [item for item in checks if item["blocks"] and item["state"] != "ok"]
    beacon_ready = len(next_steps) == 0

    if last_rf_rx_age_s is not None and last_rf_rx_age_s <= 15 * 60:
        hero = {
            "kind": "receiving",
            "tone": "good",
            "title": "Station is receiving APRS traffic",
            "status": "Receiving",
            "heard_stations": traffic["heard_stations"],
            "decoded_aprs": traffic["decoded_aprs"],
        }
    elif tx_enabled_flag and last_rf_tx_age_s is not None and last_rf_tx_age_s <= 60 * 60:
        hero = {
            "kind": "ready",
            "tone": "neutral",
            "title": "Station is transmitting",
            "summary": "Station TX activity was observed recently.",
            "status": "Transmitting",
        }
    elif beacon_ready:
        hero = {
            "kind": "ready",
            "tone": "neutral",
            "title": "Station is ready for a beacon test",
            "summary": "Basic station data and interface selection are configured. You can try manual beacon send.",
            "status": "Ready",
        }
    else:
        hero = {
            "kind": "setup",
            "tone": "caution",
            "title": "Finish station setup",
            "summary": "Complete the basic station data so APRSBox can beacon and present your station properly.",
            "status": "Needs setup",
        }

    if dashboard_band and dashboard_band.get("condition_index") is None:
        band_summary = "Band condition will become more useful after more traffic is collected."
    elif dashboard_band:
        band_summary = dashboard_band.get("diagnosis_summary") or ""
    else:
        band_summary = "Band condition is not available yet."

    last_heard_station = heard_snapshots[0] if heard_snapshots else None
    last_mobile_station = next((item for item in heard_snapshots if str(item.get("entity_class") or "").strip().lower() == "mobile"), None)
    last_object_station = next((item for item in heard_snapshots if str(item.get("entity_class") or "").strip().lower() == "object"), None)
    last_wx_station = next((item for item in heard_snapshots if str(item.get("frame_type") or "").strip().upper() == "W"), None)
    last_rf_activity: list[dict[str, str]] = []
    if last_heard_station:
        last_rf_activity.append(
            {
                "name": "Last heard station",
                "value": str(last_heard_station.get("display_callsign") or "-"),
                "note": str(last_heard_station.get("last_heard_date") or ""),
            }
        )
    last_rf_activity.append({"name": "Last RF frame time", "value": last_rf_rx_display, "note": ""})
    if last_mobile_station:
        last_rf_activity.append(
            {
                "name": "Last mobile station",
                "value": str(last_mobile_station.get("display_callsign") or "-"),
                "note": str(last_mobile_station.get("last_heard_date") or ""),
            }
        )
    if last_object_station:
        last_rf_activity.append(
            {
                "name": "Last object/item",
                "value": str(last_object_station.get("display_callsign") or "-"),
                "note": str(last_object_station.get("last_heard_date") or ""),
            }
        )
    if last_wx_station:
        last_rf_activity.append(
            {
                "name": "Last WX packet",
                "value": str(last_wx_station.get("display_callsign") or "-"),
                "note": str(last_wx_station.get("last_heard_date") or ""),
            }
        )
    last_rf_activity.append({"name": "Last own TX", "value": latest_station_tx_display, "note": ""})

    hero_summary = [
        {"label": "Callsign", "value": main_callsign or "Not set", "tone": "neutral"},
        {"label": "RF RX", "value": rx_runtime_status, "tone": rx_runtime_tone},
        {"label": "RF TX", "value": tx_runtime_status, "tone": tx_runtime_tone},
    ]
    if igate_enabled:
        hero_summary.append({"label": "APRS-IS", "value": aprsis_runtime_label, "tone": aprsis_runtime_tone})

    activity_kpis = dict((dashboard_activity or {}).get("kpis") or {})
    dashboard_heard_stations = int(activity_kpis.get("heard_stations", traffic["heard_stations"]) or 0)
    dashboard_aprs_frames = int(activity_kpis.get("aprs_frames", traffic["decoded_aprs"]) or 0)
    stats = [
        {
            "label": "Heard stations",
            "value": str(dashboard_heard_stations),
            "suffix": "",
        },
        {
            "label": "APRS frames",
            "value": str(dashboard_aprs_frames),
            "suffix": "",
        },
        {"label": "Interfaces", "value": f"{len(enabled_interfaces)} / {len(interfaces)}", "suffix": ""},
        {"label": "Last RF RX", "value": last_rf_rx_display, "suffix": ""},
        {"label": "Last RF TX", "value": last_rf_tx_display, "suffix": ""},
    ]
    if igate_enabled:
        stats.append({"label": "Last APRS-IS uplink", "value": aprsis_last_sent_display, "suffix": ""})

    return {
        "hero": hero,
        "hero_summary": hero_summary,
        "stats": stats,
        "activity_chart": (
            _dashboard_activity_series_from_aggregated(dashboard_activity)
            if dashboard_activity is not None
            else dashboard_activity_series()
        ),
        "checks": checks,
        "station_readiness": station_readiness,
        "next_steps": next_steps,
        "beacon_ready": beacon_ready,
        "station_callsign": main_callsign or "Not set",
        "interface_summary": interface_summary,
        "interface_entries": interface_entries,
        "last_rf_activity": last_rf_activity,
        "band_summary": band_summary,
    }


def visible_stations(limit: int = 500, unit_system: str = "metric") -> list[dict[str, Any]]:
    snapshots = get_visible_station_snapshots(limit=limit)
    return _station_list_rows(snapshots, unit_system=unit_system)


def projected_station_list(
    limit: int = 500,
    unit_system: str = "metric",
    *,
    since_revision: int | None = None,
    station_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.map_station_state import read_map_station_state

    state = read_map_station_state(
        since_revision=since_revision,
        station_settings=station_settings,
    )
    snapshots = list(state["snapshots"])[: max(1, int(limit or 0))]
    return {
        "revision": state["revision"],
        "full_snapshot": state["full_snapshot"],
        "removed_station_keys": state["removed_station_keys"],
        "stations": _station_list_rows(snapshots, unit_system=unit_system),
    }


def _station_list_rows(snapshots: list[dict[str, Any]], *, unit_system: str) -> list[dict[str, Any]]:
    stations: list[dict[str, Any]] = []
    for snapshot in snapshots:
        stations.append(
            {
                "callsign": snapshot["callsign"],
                "display_callsign": snapshot["display_callsign"],
                "origin": snapshot.get("origin", "heard"),
                "source_kind": snapshot.get("source_kind", RF_SOURCE_KIND),
                "is_rf": bool(snapshot.get("is_rf")),
                "direct_heard": bool(snapshot.get("direct_heard")),
                "statistics_eligible": bool(snapshot.get("statistics_eligible")),
                "last_seen_any_at": snapshot.get("last_seen_any_at"),
                "last_heard_rf_at": snapshot.get("last_heard_rf_at"),
                "last_seen_aprsis_at": snapshot.get("last_seen_aprsis_at"),
                "activity_label": snapshot.get("activity_label") or "Last heard",
                "activity_age_label": snapshot.get("activity_age_label") or "Last heard age",
                "last_heard_at": snapshot["last_heard_at"],
                "last_heard_label": snapshot["last_heard_label"],
                "last_heard_date": snapshot["last_heard_date"],
                "last_heard_relative": snapshot["last_heard_relative"],
                "entity_class": snapshot["entity_class"],
                "frame_type": snapshot["frame_type"],
                "frame_type_label": snapshot["frame_type_label"],
                "symbol": snapshot["symbol"],
                "symbol_icon": snapshot["symbol_icon"],
                "symbol_table": snapshot["symbol_table"],
                "symbol_code": snapshot["symbol_code"],
                "comment": snapshot["comment"],
                "data": _format_decoded_data_for_display(snapshot["data_raw"], unit_system),
                "latitude": snapshot["latitude"],
                "longitude": snapshot["longitude"],
                "position_ambiguity_digits": snapshot.get("position_ambiguity_digits"),
                "position_ambiguous": bool(snapshot.get("position_ambiguous")),
                "distance_km": snapshot.get("distance_km"),
                "aprs_device_short": snapshot["aprs_device_short"],
                "detail_href": build_station_detail_href(snapshot["display_callsign"]),
            }
        )
    return stations


def format_decoded_data_for_display(
    metrics: dict[str, float | int | str],
    unit_system: str,
) -> list[dict[str, str]]:
    return _format_decoded_data_for_display(metrics, unit_system)


def heard_stations(limit: int = 500, unit_system: str = "metric") -> list[dict[str, Any]]:
    return visible_stations(limit=limit, unit_system=unit_system)


def get_station_detail(
    callsign: str,
    unit_system: str = "metric",
    *,
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    normalized_callsign = callsign.strip()
    if not normalized_callsign:
        return None

    snapshot = _find_station_snapshot(normalized_callsign, snapshots=snapshots)
    if snapshot is None:
        return None

    latitude = _parse_coordinate(snapshot.get("latitude"))
    longitude = _parse_coordinate(snapshot.get("longitude"))
    last_heard_rf_at = str(snapshot.get("last_heard_rf_at") or "")
    last_seen_aprsis_at = str(snapshot.get("last_seen_aprsis_at") or "")
    last_heard_rf_date, last_heard_rf_relative = (
        _format_last_heard_parts(last_heard_rf_at) if last_heard_rf_at else ("", "")
    )
    last_seen_aprsis_date, last_seen_aprsis_relative = (
        _format_last_heard_parts(last_seen_aprsis_at) if last_seen_aprsis_at else ("", "")
    )
    return {
        "callsign": snapshot["callsign"],
        "ssid": snapshot["ssid"],
        "display_callsign": snapshot["display_callsign"],
        "detail_href": build_station_detail_href(snapshot["display_callsign"]),
        "base_callsign": snapshot["callsign"],
        "origin": snapshot.get("origin", "heard"),
        "source_kind": snapshot.get("source_kind", RF_SOURCE_KIND),
        "is_rf": bool(snapshot.get("is_rf")),
        "statistics_eligible": bool(snapshot.get("statistics_eligible")),
        "last_seen_any_at": snapshot.get("last_seen_any_at"),
        "last_heard_rf_at": snapshot.get("last_heard_rf_at"),
        "last_heard_rf_date": last_heard_rf_date,
        "last_heard_rf_relative": last_heard_rf_relative,
        "last_seen_aprsis_at": snapshot.get("last_seen_aprsis_at"),
        "last_seen_aprsis_date": last_seen_aprsis_date,
        "last_seen_aprsis_relative": last_seen_aprsis_relative,
        "activity_label": snapshot.get("activity_label", _t("Last heard")),
        "activity_age_label": snapshot.get("activity_age_label", _t("Last heard age")),
        "source": snapshot["source"],
        "destination": snapshot["destination"],
        "path": snapshot["path"],
        "entity_class": snapshot["entity_class"],
        "packet_type": snapshot["frame_type"],
        "packet_type_label": snapshot["frame_type_label"],
        "symbol": snapshot["symbol"],
        "symbol_icon": snapshot["symbol_icon"],
        "symbol_table": snapshot["symbol_table"],
        "symbol_code": snapshot["symbol_code"],
        "comment": snapshot["comment"],
        "raw_latest_packet": snapshot["raw_text"],
        "last_heard_at": snapshot["last_heard_at"],
        "last_heard_label": snapshot["last_heard_label"],
        "last_heard_date": snapshot["last_heard_date"],
        "last_heard_relative": snapshot["last_heard_relative"],
        "last_heard_age_s": snapshot["last_heard_age_s"],
        "latitude": snapshot["latitude"],
        "longitude": snapshot["longitude"],
        "latitude_float": latitude,
        "longitude_float": longitude,
        "position_ambiguity_digits": snapshot.get("position_ambiguity_digits"),
        "position_ambiguous": bool(snapshot.get("position_ambiguous")),
        "distance_km": snapshot.get("distance_km"),
        "messaging_capable": _messaging_capable(snapshot),
        "mic_e": dict(snapshot["mic_e"]) if snapshot.get("mic_e") else None,
        "aprs_device": dict(snapshot["aprs_device"]) if snapshot.get("aprs_device") else None,
        "data": _format_decoded_data_for_display(snapshot["data_raw"], unit_system),
        "fields": _station_detail_fields(snapshot, unit_system),
    }


def get_recent_station_packets(
    callsign: str,
    limit: int = 10,
    *,
    snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    snapshot = snapshot or _find_station_snapshot(callsign.strip())
    if snapshot is None:
        return []

    station_key = snapshot["display_callsign"]
    rows = fetch_all(
        """
        SELECT source, line, created_at
        FROM traffic_frames
        WHERE format IN ('TNC2', 'TNC2-TX')
        ORDER BY created_at DESC, id DESC
        LIMIT 500
        """
    )

    packets: list[dict[str, Any]] = []
    for row in rows:
        parsed = parse_tnc2_frame(str(row["line"] or ""))
        if parsed is None:
            continue
        aprs_data = dict(parsed.get("aprs_data") or {})
        packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
        if not _aprs_data_has_station_snapshot_fields(aprs_data) and packet_group != "status":
            continue
        row_station_key = str(aprs_data.get("entity_name") or parsed.get("logical_source_key") or parsed.get("source_key") or "").strip()
        if row_station_key.casefold() != station_key.casefold():
            continue

        heard_date, heard_relative = _format_last_heard_parts(row["created_at"])
        decoded_summary = aprs_data.get("comment", "")
        if not decoded_summary and aprs_data.get("data"):
            decoded_items = _format_decoded_data_for_display(aprs_data["data"], "metric")
            decoded_summary = ", ".join(item["value"] for item in decoded_items[:4])

        packets.append(
            {
                "timestamp": row["created_at"],
                "timestamp_label": heard_date,
                "timestamp_relative": heard_relative,
                "source": str(parsed.get("logical_source_key") or parsed.get("source_key") or ""),
                "destination": str(parsed.get("logical_destination") or parsed.get("destination") or ""),
                "path": str(parsed.get("logical_path") or parsed.get("path") or ""),
                "decoded_summary": decoded_summary,
                "raw_packet": row["line"],
            }
        )
        if bool(parsed.get("is_third_party")):
            packets[-1]["third_party"] = True
            packets[-1]["outer_source"] = str(parsed.get("source_key") or "")
            packets[-1]["outer_path"] = str(parsed.get("path") or "")
        if len(packets) >= limit:
            break
    return packets


def get_related_ssids(
    base_callsign: str,
    *,
    snapshots: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized_base = base_callsign.strip()
    if not normalized_base:
        return []

    related: list[dict[str, Any]] = []
    seen: set[str] = set()
    for snapshot in snapshots or get_visible_station_snapshots():
        if snapshot["callsign"].casefold() != normalized_base.casefold():
            continue
        display_callsign = snapshot["display_callsign"]
        dedupe_key = display_callsign.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        related.append(
            {
                "display_callsign": display_callsign,
                "detail_href": build_station_detail_href(display_callsign),
                "is_current": False,
                "last_heard_label": snapshot["last_heard_label"],
            }
        )
    return related


def _find_station_snapshot(
    callsign: str,
    *,
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    normalized = callsign.strip().casefold()
    if not normalized:
        return None
    available_snapshots = snapshots or get_visible_station_snapshots()
    for snapshot in available_snapshots:
        if snapshot["display_callsign"].casefold() == normalized:
            return snapshot
    for snapshot in available_snapshots:
        if snapshot["callsign"].casefold() == normalized:
            return snapshot
    return None


def get_heard_station_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    row_limit = _station_snapshot_row_limit(limit)
    # APRS-IS can be much busier than the local RF channel. Query both source
    # groups independently so an APRS-IS burst cannot push locally heard RF
    # frames outside the scan window, then use RF as the primary snapshot and
    # APRS-IS only to fill fields that RF did not provide.
    rf_rows = _station_snapshot_rows(
        ("TNC2",),
        row_limit=row_limit,
        statistics_only=True,
    )
    aprsis_rows = _station_snapshot_rows(
        ("TNC2",),
        row_limit=row_limit,
        source_kind=APRSIS_SOURCE_KIND,
    )
    rf_snapshots = _build_station_snapshots_from_rows(rf_rows, origin="heard", limit=limit)
    aprsis_snapshots = _build_station_snapshots_from_rows(aprsis_rows, origin="heard", limit=limit)
    return _merge_rf_primary_station_snapshots(
        rf_snapshots,
        aprsis_snapshots,
        limit=limit,
    )


def get_rf_heard_station_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    rows = _station_snapshot_rows(
        ("TNC2",),
        row_limit=_station_snapshot_row_limit(limit),
        statistics_only=True,
    )
    return _build_station_snapshots_from_rows(rows, origin="heard", limit=limit)


def get_local_tx_station_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    rows = _station_snapshot_rows(("TNC2-TX",), row_limit=_station_snapshot_row_limit(limit))
    return _build_station_snapshots_from_rows(rows, origin="local_tx", limit=limit)


def get_visible_station_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    normalized_limit = max(1, int(limit or 0))
    station_settings = get_station_settings()
    station_latitude = str(station_settings.get("latitude") or "")
    station_longitude = str(station_settings.get("longitude") or "")
    ttl_cache_key = (
        str(settings.database_path),
        normalized_limit,
        station_latitude,
        station_longitude,
    )
    cached_visible = _VISIBLE_STATION_SNAPSHOT_TTL_CACHE.get(ttl_cache_key)
    current_time = time.monotonic()
    if cached_visible is not None and current_time - cached_visible[0] < _VISIBLE_STATION_SNAPSHOT_TTL_SECONDS:
        return [dict(item) for item in cached_visible[1]]
    cache_key = (
        str(settings.database_path),
        normalized_limit,
        _latest_station_snapshot_frame_id(),
        station_latitude,
        station_longitude,
    )
    cached = _STATION_SNAPSHOT_CACHE.get(cache_key)
    if cached is not None:
        return [dict(item) for item in cached]

    snapshots_by_key: dict[str, dict[str, Any]] = {}

    for snapshot in get_heard_station_snapshots(limit=max(normalized_limit, 500)):
        snapshots_by_key[snapshot["display_callsign"].casefold()] = dict(snapshot)

    for snapshot in get_local_tx_station_snapshots(limit=max(normalized_limit, 500)):
        key = snapshot["display_callsign"].casefold()
        existing = snapshots_by_key.get(key)
        if existing is None:
            snapshots_by_key[key] = dict(snapshot)
            continue
        snapshots_by_key[key] = _merge_station_snapshots(existing, snapshot)

    snapshots = list(snapshots_by_key.values())
    _apply_station_reference_distances(snapshots)
    snapshots.sort(key=lambda item: (str(item.get("last_heard_at") or ""), str(item.get("display_callsign") or "")), reverse=True)
    result = snapshots[:normalized_limit]
    _STATION_SNAPSHOT_CACHE.clear()
    _STATION_SNAPSHOT_CACHE[cache_key] = [dict(item) for item in result]
    _VISIBLE_STATION_SNAPSHOT_TTL_CACHE[ttl_cache_key] = (time.monotonic(), [dict(item) for item in result])
    return [dict(item) for item in result]


def _station_snapshot_row_limit(limit: int) -> int:
    normalized_limit = max(1, int(limit or 0))
    return max(STATION_SNAPSHOT_ROW_LIMIT_MIN, normalized_limit * STATION_SNAPSHOT_ROW_LIMIT_FACTOR)


def _latest_station_snapshot_frame_id() -> int | None:
    row = fetch_one(
        """
        SELECT MAX(id) AS max_id
        FROM traffic_frames
        WHERE format IN ('TNC2', 'TNC2-TX')
        """
    )
    if row is None or row["max_id"] is None:
        return None
    return int(row["max_id"])


def get_visible_station_snapshot_revision() -> int | None:
    return _latest_station_snapshot_frame_id()


def _station_snapshot_rows(
    formats: tuple[str, ...],
    *,
    row_limit: int,
    statistics_only: bool = False,
    source_kind: str | None = None,
) -> list[dict[str, Any]]:
    placeholders = ", ".join("?" for _ in formats)
    params: tuple[Any, ...] = formats
    if source_kind is not None:
        source_clause = " AND LOWER(COALESCE(source_kind, 'rf')) = ?"
        params += (normalize_source_kind(source_kind),)
    elif statistics_only:
        source_clause = f" AND {STATISTICS_TRAFFIC_SQL_PREDICATE}"
    else:
        source_clause = ""
    rows = fetch_all(
        f"""
        SELECT source, source_kind, interface_id, line, created_at
        FROM traffic_frames
        WHERE format IN ({placeholders})
          {source_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        params + (row_limit,),
    )
    return [dict(row) for row in rows]


def _merge_rf_primary_station_snapshots(
    rf_snapshots: list[dict[str, Any]],
    aprsis_snapshots: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    aprsis_by_key = {
        str(snapshot.get("display_callsign") or "").casefold(): snapshot
        for snapshot in aprsis_snapshots
        if str(snapshot.get("display_callsign") or "").strip()
    }
    merged: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for rf_snapshot in rf_snapshots:
        key = str(rf_snapshot.get("display_callsign") or "").casefold()
        supplemental = aprsis_by_key.get(key)
        if supplemental is None:
            combined = dict(rf_snapshot)
        else:
            combined = _merge_station_snapshots(
                rf_snapshot,
                supplemental,
                prefer_primary_activity=True,
            )
        merged.append(combined)
        seen_keys.add(key)

    merged.sort(
        key=lambda item: (
            str(item.get("last_heard_rf_at") or item.get("last_heard_at") or ""),
            str(item.get("display_callsign") or ""),
        ),
        reverse=True,
    )
    aprsis_only = [
        snapshot
        for key, snapshot in aprsis_by_key.items()
        if key not in seen_keys
    ]
    aprsis_only.sort(
        key=lambda item: (
            str(item.get("last_seen_aprsis_at") or item.get("last_heard_at") or ""),
            str(item.get("display_callsign") or ""),
        ),
        reverse=True,
    )
    # The map has a finite station limit. Keep locally heard stations first and
    # use APRS-IS-only stations to fill the remaining capacity.
    return (merged + aprsis_only)[: max(1, int(limit or 0))]


def _normalize_interface_id(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _station_path_is_direct(path: Any) -> bool:
    tokens = [token.strip() for token in str(path or "").split(",") if token.strip()]
    return not any(token.endswith("*") for token in tokens)


def _build_station_snapshots_from_rows(
    rows: list[dict[str, Any]],
    *,
    origin: str,
    limit: int,
    materialize_display: bool = True,
) -> list[dict[str, Any]]:
    stations: dict[str, dict[str, Any]] = {}
    station_key_index: dict[str, str] = {}
    direct_heard_station_keys: set[str] = set()
    killed_station_keys: set[str] = set()
    pending_status_by_station_key: dict[str, str] = {}
    device_database = get_aprs_device_identification_database()

    for row in rows:
        parsed = parse_tnc2_frame(str(row["line"] or ""))
        if parsed is None:
            continue

        callsign = str(parsed.get("logical_source_key") or parsed.get("source_key") or "").strip()
        aprs_data = dict(parsed.get("aprs_data") or {})
        station_key = (aprs_data.get("entity_name") or callsign).strip()
        station_key_folded = station_key.casefold()
        row_source_kind = normalize_source_kind(row.get("source_kind"))
        logical_path = str(parsed.get("logical_path") or parsed.get("path") or "")
        if (
            station_key_folded
            and origin == "heard"
            and row_source_kind == RF_SOURCE_KIND
            and _station_path_is_direct(logical_path)
        ):
            direct_heard_station_keys.add(station_key_folded)
        packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
        if packet_group == "object" and str(aprs_data.get("state") or "").strip().lower() == "killed":
            existing_key = station_key_index.get(station_key_folded)
            if existing_key is None:
                killed_station_keys.add(station_key_folded)
            continue
        if station_key_folded in killed_station_keys:
            continue
        status_comment = str(aprs_data.get("comment") or "").strip()
        if packet_group == "status" and station_key and status_comment:
            existing_key = station_key_index.get(station_key_folded)
            if existing_key is not None and not str(stations[existing_key].get("status_text") or "").strip():
                stations[existing_key]["status_text"] = status_comment
            else:
                pending_status_by_station_key.setdefault(station_key_folded, status_comment)
        if not _aprs_data_has_station_snapshot_fields(aprs_data):
            continue

        if not station_key:
            continue

        if station_key not in stations:
            stations[station_key] = _new_station_snapshot(
                station_key,
                row["created_at"],
                row["source"],
                str(parsed.get("logical_destination") or parsed.get("destination") or ""),
                str(parsed.get("logical_path") or parsed.get("path") or ""),
                row["line"],
                _normalize_interface_id(row.get("interface_id")),
                source_kind=row_source_kind,
                origin=origin,
                materialize_display=materialize_display,
            )
            station_key_index[station_key_folded] = station_key

        station = stations[station_key]
        _record_station_source_observation(
            station,
            source_kind=row_source_kind,
            created_at=str(row["created_at"] or ""),
            source=str(row["source"] or ""),
            interface_id=_normalize_interface_id(row.get("interface_id")),
            origin=origin,
        )
        if not str(station.get("status_text") or "").strip():
            pending_status = pending_status_by_station_key.pop(station_key_folded, "")
            if pending_status:
                station["status_text"] = pending_status
        if not station["aprs_device"] and station_key.casefold() == callsign.casefold():
            device_identification = lookup_aprs_device_identification(
                destination=str(parsed.get("logical_destination") or parsed.get("destination") or ""),
                info=str(parsed.get("logical_info") or parsed.get("info") or ""),
                database=device_database,
            )
            if device_identification is not None:
                station["aprs_device"] = dict(device_identification)
                station["aprs_device_short"] = str(device_identification.get("short_name") or "")
        if not station["entity_class"] and aprs_data.get("entity_class"):
            station["entity_class"] = aprs_data["entity_class"]
        if not station["frame_type"] and aprs_data.get("frame_type"):
            station["frame_type"] = aprs_data["frame_type"]
            station["frame_type_label"] = aprs_data.get("frame_type_label", "")
        if not station["symbol"] and aprs_data.get("symbol"):
            station["symbol"] = aprs_data["symbol"]
            if materialize_display:
                station["symbol_icon"] = _aprs_symbol_icon_path(aprs_data["symbol"])
            symbol_table, symbol_code = _split_symbol(aprs_data["symbol"])
            station["symbol_table"] = symbol_table
            station["symbol_code"] = symbol_code
        if not station["comment"] and aprs_data.get("comment"):
            station["comment"] = aprs_data["comment"]
        if (
            not station.get("status_text")
            and str(aprs_data.get("packet_group") or "").strip().lower() == "status"
            and aprs_data.get("comment")
        ):
            station["status_text"] = str(aprs_data["comment"])
        if not station["data_raw"] and aprs_data.get("data"):
            station["data_raw"] = dict(aprs_data["data"])
        if not station.get("mic_e") and aprs_data.get("mic_e"):
            station["mic_e"] = dict(aprs_data["mic_e"])
        if not station["latitude"] and aprs_data.get("latitude"):
            station["latitude"] = aprs_data["latitude"]
        if not station["longitude"] and aprs_data.get("longitude"):
            station["longitude"] = aprs_data["longitude"]
        if station.get("position_ambiguity_digits") is None and aprs_data.get("position_ambiguity_digits") is not None:
            station["position_ambiguity_digits"] = int(aprs_data["position_ambiguity_digits"])
        if not station.get("position_ambiguous") and aprs_data.get("position_ambiguous"):
            station["position_ambiguous"] = True

    for direct_station_key in direct_heard_station_keys:
        stored_key = station_key_index.get(direct_station_key)
        if stored_key is not None:
            stations[stored_key]["direct_heard"] = True

    return list(stations.values())[:limit]


def _merge_station_snapshots(
    primary: dict[str, Any],
    secondary: dict[str, Any],
    *,
    prefer_primary_activity: bool = False,
) -> dict[str, Any]:
    merged = dict(primary)
    latest = secondary if str(secondary.get("last_heard_at") or "") > str(primary.get("last_heard_at") or "") else primary
    for field in (
        "entity_class",
        "frame_type",
        "frame_type_label",
        "symbol",
        "symbol_table",
        "symbol_code",
        "symbol_icon",
        "comment",
        "latitude",
        "longitude",
        "aprs_device",
        "aprs_device_short",
        "status_text",
        "mic_e",
        "position_ambiguity_digits",
    ):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    if not merged.get("position_ambiguous") and secondary.get("position_ambiguous"):
        merged["position_ambiguous"] = True
    merged["direct_heard"] = bool(primary.get("direct_heard") or secondary.get("direct_heard"))
    if (not merged.get("data_raw")) and secondary.get("data_raw"):
        merged["data_raw"] = dict(secondary["data_raw"])
    for field in (
        "last_heard_rf_at",
        "last_heard_rf_source",
        "last_heard_rf_interface_id",
        "last_seen_aprsis_at",
        "last_seen_aprsis_source",
        "last_seen_aprsis_interface_id",
    ):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    if latest is secondary and not prefer_primary_activity:
        for field in (
            "origin",
            "activity_label",
            "activity_age_label",
            "last_heard_at",
            "last_heard_age_s",
            "last_heard_label",
            "last_heard_date",
            "last_heard_relative",
            "source",
            "destination",
            "path",
            "raw_text",
            "interface_id",
            "source_kind",
            "is_rf",
            "last_seen_any_at",
        ):
            merged[field] = secondary.get(field)
    if prefer_primary_activity:
        merged["last_seen_any_at"] = max(
            str(primary.get("last_seen_any_at") or primary.get("last_heard_at") or ""),
            str(secondary.get("last_seen_any_at") or secondary.get("last_heard_at") or ""),
        )
    merged["statistics_eligible"] = bool(merged.get("last_heard_rf_at"))
    return merged


def _new_station_snapshot(
    name: str,
    created_at: str,
    source: str,
    destination: str,
    path: str,
    raw_text: str,
    interface_id: int | None,
    *,
    source_kind: str,
    origin: str,
    materialize_display: bool = True,
) -> dict[str, Any]:
    heard_date, heard_relative = _format_last_heard_parts(created_at)
    base_callsign, ssid = _split_ssid(name)
    normalized_kind = normalize_source_kind(source_kind)
    resolved_origin = APRSIS_SOURCE_KIND if origin == "heard" and normalized_kind == APRSIS_SOURCE_KIND else origin
    activity_label, activity_age_label = (
        _station_snapshot_activity_labels(resolved_origin)
        if materialize_display
        else ("", "")
    )
    is_rf_heard = origin == "heard" and normalized_kind == RF_SOURCE_KIND
    is_aprsis_seen = origin == "heard" and normalized_kind == APRSIS_SOURCE_KIND
    return {
        "callsign": base_callsign,
        "ssid": ssid,
        "display_callsign": name,
        "origin": resolved_origin,
        "source_kind": normalized_kind,
        "is_rf": is_rf_heard,
        "direct_heard": False,
        "statistics_eligible": is_rf_heard,
        "activity_label": activity_label,
        "activity_age_label": activity_age_label,
        "last_heard_at": created_at,
        "last_seen_any_at": created_at,
        "last_heard_rf_at": created_at if is_rf_heard else None,
        "last_heard_rf_source": source if is_rf_heard else None,
        "last_heard_rf_interface_id": interface_id if is_rf_heard else None,
        "last_seen_aprsis_at": created_at if is_aprsis_seen else None,
        "last_seen_aprsis_source": source if is_aprsis_seen else None,
        "last_seen_aprsis_interface_id": interface_id if is_aprsis_seen else None,
        "last_heard_age_s": _last_heard_age_seconds(created_at),
        "last_heard_label": _format_last_heard(created_at),
        "last_heard_date": heard_date,
        "last_heard_relative": heard_relative,
        "source": source,
        "destination": destination,
        "path": path,
        "raw_text": raw_text,
        "interface_id": interface_id,
        "entity_class": "",
        "frame_type": "",
        "frame_type_label": "",
        "symbol": "",
        "symbol_table": "",
        "symbol_code": "",
        "symbol_icon": get_aprs_symbol_icon_fallback_path() if materialize_display else "",
        "comment": "",
        "status_text": "",
        "data_raw": {},
        "mic_e": None,
        "latitude": "",
        "longitude": "",
        "position_ambiguity_digits": None,
        "position_ambiguous": False,
        "distance_km": None,
        "aprs_device": None,
        "aprs_device_short": "",
    }


def _station_snapshot_activity_labels(origin: str) -> tuple[str, str]:
    if origin == "local_tx":
        return _t("Last local TX"), _t("Last local TX age")
    if origin == APRSIS_SOURCE_KIND:
        return _t("Last seen via APRS-IS"), _t("Last APRS-IS activity age")
    return _t("Last heard"), _t("Last heard age")


def prepare_station_snapshots_for_display(
    snapshots: list[dict[str, Any]],
    *,
    station_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Refresh request-time fields without per-station settings lookups."""
    translator = get_translator(get_app_language())
    symbol_set = get_aprs_symbol_set()
    resolved_station_settings = station_settings if station_settings is not None else get_station_settings()
    reference_latitude = _parse_coordinate(resolved_station_settings.get("latitude"))
    reference_longitude = _parse_coordinate(resolved_station_settings.get("longitude"))
    result: list[dict[str, Any]] = []
    for stored in snapshots:
        snapshot = dict(stored)
        created_at = str(snapshot.get("last_heard_at") or "")
        heard_date, heard_relative = _format_last_heard_parts(created_at)
        snapshot["last_heard_age_s"] = _last_heard_age_seconds(created_at)
        snapshot["last_heard_label"] = _format_last_heard(created_at)
        snapshot["last_heard_date"] = heard_date
        snapshot["last_heard_relative"] = heard_relative
        origin = str(snapshot.get("origin") or "heard")
        if origin == "local_tx":
            labels = (translator("Last local TX"), translator("Last local TX age"))
        elif origin == APRSIS_SOURCE_KIND:
            labels = (translator("Last seen via APRS-IS"), translator("Last APRS-IS activity age"))
        else:
            labels = (translator("Last heard"), translator("Last heard age"))
        snapshot["activity_label"], snapshot["activity_age_label"] = labels
        snapshot["symbol_icon"] = _aprs_symbol_icon_path_for_resolved_set(
            str(snapshot.get("symbol") or ""), symbol_set
        )
        snapshot["distance_km"] = _distance_km_between_points(
            reference_latitude,
            reference_longitude,
            _parse_coordinate(snapshot.get("latitude")),
            _parse_coordinate(snapshot.get("longitude")),
        )
        result.append(snapshot)
    return result


def _record_station_source_observation(
    station: dict[str, Any],
    *,
    source_kind: str,
    created_at: str,
    source: str,
    interface_id: int | None,
    origin: str,
) -> None:
    if origin != "heard":
        return
    normalized_kind = normalize_source_kind(source_kind)
    if normalized_kind == RF_SOURCE_KIND and not station.get("last_heard_rf_at"):
        station["last_heard_rf_at"] = created_at
        station["last_heard_rf_source"] = source
        station["last_heard_rf_interface_id"] = interface_id
        station["statistics_eligible"] = True
    elif normalized_kind == APRSIS_SOURCE_KIND and not station.get("last_seen_aprsis_at"):
        station["last_seen_aprsis_at"] = created_at
        station["last_seen_aprsis_source"] = source
        station["last_seen_aprsis_interface_id"] = interface_id


def _aprs_data_has_station_snapshot_fields(aprs_data: dict[str, Any]) -> bool:
    return any(
        bool(aprs_data.get(field))
        for field in ("frame_type", "symbol", "latitude", "longitude", "entity_name")
    )


_TNC2_RE = re.compile(r"^(?P<source>[^>]+?)\s*>\s*(?P<destination>[^,:]+?)(?:\s*,\s*(?P<path>[^:]+))?\s*:(?P<info>.*)$")
_MESSAGE_SUFFIX_RE = re.compile(r"^(?P<text>.*?)(?:\{(?P<number>[0-9A-Z]{2})(?:}(?P<reply_ack>[0-9A-Z]{2})?)?)?$")
_ACK_MESSAGE_RE = re.compile(r"ack(?P<number>[0-9A-Z]{2})(?:}(?P<reply_ack>[0-9A-Z]{2})?)?$", flags=re.IGNORECASE)
_REJECT_MESSAGE_RE = re.compile(r"rej(?P<number>[0-9A-Z]{2})(?:}(?P<reply_ack>[0-9A-Z]{2})?)?$", flags=re.IGNORECASE)
_TELEMETRY_MESSAGE_PREFIXES = ("PARM.", "UNIT.", "EQNS.", "BITS.")
_PACKET_GROUP_LABELS = {
    "position": "Position",
    "object": "Object",
    "item": "Item",
    "message": "Message",
    "status": "Status",
    "weather": "Weather",
    "telemetry": "Telemetry",
    "query": "Query",
}


def _parse_tnc2_line(line: str) -> dict[str, str] | None:
    match = _TNC2_RE.match(line.strip("\r\n"))
    if not match:
        return None
    parsed = match.groupdict(default="")
    return {
        "source": parsed["source"].strip(),
        "destination": parsed["destination"].strip(),
        "path": parsed["path"].strip(),
        # Preserve leading and trailing info-field spaces: compressed c/s/T
        # can legally carry spaces and stripping them breaks fixed-offset
        # decoding and packet integrity for forwarding paths.
        "info": parsed["info"],
    }


def parse_tnc2_frame(line: str) -> dict[str, Any] | None:
    parsed = _parse_tnc2_line(line)
    if parsed is None:
        return None

    aprs_data = _parse_aprs_packet(parsed)
    source_key = parsed["source"].strip()
    source_callsign, source_ssid = _split_ssid(source_key)
    third_party_inner_valid = bool((aprs_data or {}).get("third_party_inner_valid"))
    logical_source_key = (
        str((aprs_data or {}).get("inner_source_key") or "").strip()
        if third_party_inner_valid
        else source_key
    ) or source_key
    logical_source_callsign, logical_source_ssid = _split_ssid(logical_source_key)
    logical_destination = (
        str((aprs_data or {}).get("inner_destination") or "").strip()
        if third_party_inner_valid
        else parsed["destination"]
    ) or parsed["destination"]
    logical_path = (
        str((aprs_data or {}).get("inner_path") or "").strip()
        if third_party_inner_valid
        else parsed["path"]
    ) or parsed["path"]
    logical_info = (
        str((aprs_data or {}).get("inner_info") or "")
        if third_party_inner_valid
        else parsed["info"]
    )
    entity_name = (aprs_data or {}).get("entity_name")
    entity_class = str((aprs_data or {}).get("entity_class") or "").strip()
    classification = "unknown"
    if entity_class == "mobile":
        classification = "mobile"
    elif entity_class == "object":
        classification = "object"
    elif entity_class:
        classification = "fixed"

    return {
        "source": parsed["source"],
        "destination": parsed["destination"],
        "path": parsed["path"],
        "info": parsed["info"],
        "source_key": source_key,
        "source_callsign": source_callsign,
        "source_ssid": source_ssid,
        "logical_source_key": logical_source_key,
        "logical_source_callsign": logical_source_callsign,
        "logical_source_ssid": logical_source_ssid,
        "logical_destination": logical_destination,
        "logical_path": logical_path,
        "logical_info": logical_info,
        "is_third_party": bool((aprs_data or {}).get("is_third_party")),
        "third_party_inner_valid": third_party_inner_valid,
        "entity_name": str(entity_name or "").strip(),
        "entity_class": entity_class,
        "classification": classification,
        "aprs_data": aprs_data,
    }


def _format_last_heard(timestamp: str) -> str:
    heard_at = _parse_iso_timestamp_utc(timestamp)
    if heard_at is None:
        return timestamp

    now = datetime.now(timezone.utc)
    delta_seconds = max(0, int((now - heard_at).total_seconds()))
    relative = "teraz"
    if delta_seconds < 60:
        relative = "teraz"
    elif delta_seconds < 3600:
        minutes = delta_seconds // 60
        relative = f"{minutes} {_pluralize_minutes(minutes)} temu"
    else:
        hours = delta_seconds // 3600
        relative = f"{hours} {_pluralize_hours(hours)} temu"
    return f"{heard_at.strftime('%Y.%m.%d %H:%M UTC')} ({relative})"


def _format_last_heard_parts(timestamp: str) -> tuple[str, str]:
    heard_at = _parse_iso_timestamp_utc(timestamp)
    if heard_at is None:
        return timestamp, ""

    now = datetime.now(timezone.utc)
    delta_seconds = max(0, int((now - heard_at).total_seconds()))
    if delta_seconds < 60:
        relative = "teraz"
    elif delta_seconds < 3600:
        minutes = delta_seconds // 60
        relative = f"{minutes} {_pluralize_minutes(minutes)} temu"
    else:
        hours = delta_seconds // 3600
        relative = f"{hours} {_pluralize_hours(hours)} temu"
    return heard_at.strftime("%Y.%m.%d %H:%M UTC"), relative


def _last_heard_age_seconds(timestamp: str) -> int | None:
    heard_at = _parse_iso_timestamp_utc(timestamp)
    if heard_at is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - heard_at).total_seconds()))


def _parse_iso_timestamp_utc(timestamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _split_ssid(value: str) -> tuple[str, str]:
    base, separator, suffix = value.partition("-")
    if separator and suffix.isdigit():
        return base, suffix
    return value, ""


def _split_symbol(symbol: str) -> tuple[str, str]:
    if len(symbol) >= 2:
        return symbol[0], symbol[1]
    if symbol:
        return symbol[0], ""
    return "", ""


def build_station_detail_href(display_callsign: str) -> str:
    return f"/stations/{quote(display_callsign, safe='')}"


def _parse_coordinate(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _apply_station_reference_distances(snapshots: list[dict[str, Any]]) -> None:
    station_settings = get_station_settings()
    reference_latitude = _parse_coordinate(station_settings.get("latitude"))
    reference_longitude = _parse_coordinate(station_settings.get("longitude"))
    for snapshot in snapshots:
        latitude = _parse_coordinate(snapshot.get("latitude"))
        longitude = _parse_coordinate(snapshot.get("longitude"))
        snapshot["distance_km"] = _distance_km_between_points(
            reference_latitude,
            reference_longitude,
            latitude,
            longitude,
        )


def _distance_km_between_points(
    latitude_a: float | None,
    longitude_a: float | None,
    latitude_b: float | None,
    longitude_b: float | None,
) -> float | None:
    if None in {latitude_a, longitude_a, latitude_b, longitude_b}:
        return None

    earth_radius_km = 6371.0
    phi_1 = math.radians(float(latitude_a))
    phi_2 = math.radians(float(latitude_b))
    delta_phi = math.radians(float(latitude_b) - float(latitude_a))
    delta_lambda = math.radians(float(longitude_b) - float(longitude_a))
    haversine = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    )
    arc = 2.0 * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
    return round(earth_radius_km * arc, 1)


def _messaging_capable(snapshot: dict[str, Any]) -> bool | None:
    if snapshot.get("entity_class") == "object":
        return False
    return None


def _render_station_detail_comment(comment: str) -> str:
    text = str(comment or "")
    if not text:
        return ""

    parts: list[str] = []
    last_index = 0
    for match in _STATION_DETAIL_URL_PATTERN.finditer(text):
        start, end = match.span()
        if start > last_index:
            parts.append(escape(text[last_index:start]))

        url = match.group(0)
        trailing = ""
        while url and url[-1] in ").,!?;:]":
            trailing = url[-1] + trailing
            url = url[:-1]

        if url:
            parts.append(
                f'<a class="station-detail-comment-link" href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(url)}</a>'
            )
        parts.append(escape(trailing))
        last_index = end

    if last_index < len(text):
        parts.append(escape(text[last_index:]))

    return "".join(parts)


def _station_detail_fields(snapshot: dict[str, Any], _unit_system: str) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    display_callsign = snapshot.get("display_callsign")
    if display_callsign:
        fields.append({"label": _t("Display callsign"), "value": str(display_callsign)})
    if snapshot.get("callsign"):
        fields.append({"label": _t("Base callsign"), "value": str(snapshot["callsign"])})
    if snapshot.get("ssid"):
        fields.append({"label": _t("SSID"), "value": str(snapshot["ssid"])})
    if snapshot.get("source"):
        fields.append({"label": _t("Source"), "value": str(snapshot["source"])})
    if snapshot.get("last_heard_date"):
        fields.append({"label": str(snapshot.get("activity_label") or _t("Last heard")), "value": str(snapshot["last_heard_date"])})
    if snapshot.get("last_heard_relative"):
        fields.append({"label": str(snapshot.get("activity_age_label") or _t("Last heard age")), "value": str(snapshot["last_heard_relative"])})
    if snapshot.get("latitude"):
        fields.append({"label": _t("Latitude"), "value": str(snapshot["latitude"])})
    if snapshot.get("longitude"):
        fields.append({"label": _t("Longitude"), "value": str(snapshot["longitude"])})
    if snapshot.get("symbol_table"):
        fields.append({"label": _t("Symbol table"), "value": str(snapshot["symbol_table"])})
    if snapshot.get("symbol_code"):
        fields.append({"label": _t("Symbol code"), "value": str(snapshot["symbol_code"])})
    if snapshot.get("comment"):
        comment = str(snapshot["comment"])
        fields.append({"label": _t("Comment"), "value": comment, "html": _render_station_detail_comment(comment)})
    mic_e_fields = _station_detail_mic_e_fields(snapshot.get("mic_e"))
    if mic_e_fields:
        fields.extend(mic_e_fields)
    if not snapshot.get("mic_e"):
        fields.append({"label": _t("Status"), "value": str(snapshot.get("status_text") or "")})
    if snapshot.get("path"):
        fields.append({"label": _t("Path"), "value": str(snapshot["path"])})

    messaging_capable = _messaging_capable(snapshot)
    if messaging_capable is not None:
        fields.append({"label": _t("Messaging capability"), "value": _t("Yes") if messaging_capable else _t("No")})
    if snapshot.get("raw_text"):
        fields.append({"label": _t("Latest raw packet"), "value": str(snapshot["raw_text"])})
    return fields


def _station_detail_mic_e_fields(mic_e: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not mic_e:
        return []

    def add_field(fields: list[dict[str, Any]], label: str, value: Any) -> None:
        if value in {None, ""}:
            return
        fields.append({"label": label, "value": str(value)})

    def bool_text(value: bool | None) -> str:
        if value is True:
            return _t("Yes")
        if value is False:
            return _t("No")
        return _t("Unknown")

    def unknown_text(value: Any) -> str:
        text = str(value or "").strip()
        return text if text else _t("Unknown")

    fields: list[dict[str, Any]] = []
    add_field(fields, _t("Packet type"), _t("Mic-E"))
    if mic_e.get("destination_raw"):
        fields.append({"label": _t("Destination"), "value": f'{mic_e["destination_raw"]} (Mic-E encoded)'})
    fields.append({"label": _t("Status"), "value": unknown_text(mic_e.get("status"))})
    fields.append({"label": _t("Emergency"), "value": bool_text(mic_e.get("emergency"))})
    fields.append({"label": _t("Device"), "value": unknown_text(mic_e.get("device_name"))})
    fields.append({"label": _t("Device type"), "value": unknown_text(mic_e.get("device_type"))})
    fields.append({"label": _t("Raw type byte"), "value": unknown_text("space" if mic_e.get("raw_type_byte") == " " else mic_e.get("raw_type_byte"))})
    fields.append({"label": _t("Raw identifier"), "value": unknown_text(mic_e.get("raw_identifier"))})
    fields.append({"label": _t("Message capable"), "value": bool_text(mic_e.get("message_capable"))})

    speed_knots = mic_e.get("speed_knots")
    speed_kmh = mic_e.get("speed_kmh")
    if speed_knots is not None and speed_kmh is not None:
        fields.append({"label": _t("Speed"), "value": f"{speed_knots} kt / {speed_kmh} km/h"})
    else:
        fields.append({"label": _t("Speed"), "value": _t("Unknown")})

    course_deg = mic_e.get("course_deg")
    fields.append({"label": _t("Course"), "value": f"{course_deg}°" if course_deg is not None else _t("Unknown")})

    altitude_m = mic_e.get("altitude_m")
    altitude_ft = mic_e.get("altitude_ft")
    if altitude_m is not None and altitude_ft is not None:
        fields.append({"label": _t("Altitude"), "value": f"{altitude_m} m / {altitude_ft} ft"})
    else:
        fields.append({"label": _t("Altitude"), "value": _t("Unknown")})

    fields.append({"label": _t("Position ambiguity"), "value": unknown_text(mic_e.get("position_ambiguity"))})
    return fields


def station_summary(stations: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": 0, "direct": 0, "stationary": 0, "mobile": 0, "objects": 0}
    for station in stations:
        summary["total"] += 1
        if station.get("direct_heard"):
            summary["direct"] += 1
        entity_class = station.get("entity_class")
        if entity_class == "object":
            summary["objects"] += 1
        elif entity_class == "mobile":
            summary["mobile"] += 1
        else:
            summary["stationary"] += 1
    return summary


def _pluralize_minutes(value: int) -> str:
    if value == 1:
        return "minutę"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return "minuty"
    return "minut"


def _pluralize_hours(value: int) -> str:
    if value == 1:
        return "godzinę"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return "godziny"
    return "godzin"


def _parse_aprs_packet(packet: dict[str, str]) -> dict[str, Any] | None:
    info = packet["info"]
    if not info:
        return None

    packet_type = info[0]
    if packet_type in {"!", "="}:
        return _parse_position_without_timestamp(info)
    if packet_type in {"/", "@"}:
        return _parse_position_with_timestamp(info)
    if packet_type in {"`", "'"}:
        return _parse_mic_e_packet(packet)
    if packet_type == ">":
        return _parse_status_packet(info)
    if packet_type == "_":
        return _parse_weather_only_packet(info)
    if packet_type == ";":
        return _parse_object_packet(info)
    if packet_type == ")":
        return _parse_item_packet(info)
    if packet_type == ":":
        return _parse_message_packet(info)
    if packet_type == "T" and info.upper().startswith("T#"):
        return _parse_telemetry_packet(info)
    if packet_type == "}":
        return _parse_third_party_packet(packet)
    return None


def _parse_position_without_timestamp(info: str) -> dict[str, Any] | None:
    if len(info) >= 14 and _looks_like_compressed_position(info, with_timestamp=False):
        compressed = _parse_compressed_position(info, with_timestamp=False)
        if compressed is not None:
            return compressed

    if len(info) < 20:
        return None
    latitude = _parse_latitude(info[1:9])
    symbol_table = info[9]
    longitude = _parse_longitude(info[10:19])
    symbol_code = info[19]
    if latitude is None or longitude is None:
        return None
    result = {
        "entity_class": "stationary",
        "frame_type": "S",
        "frame_type_label": "S - stała",
        "packet_group": "position",
        "packet_group_label": _packet_group_label("position"),
        "packet_type_code": "position",
        "latitude": latitude,
        "longitude": longitude,
        "symbol": f"{symbol_table}{symbol_code}",
        "comment": info[20:].strip(),
    }
    _attach_comment_extensions(result)
    return result


def _parse_position_with_timestamp(info: str) -> dict[str, Any] | None:
    if len(info) >= 21 and _looks_like_compressed_position(info, with_timestamp=True):
        compressed = _parse_compressed_position(info, with_timestamp=True)
        if compressed is not None:
            return compressed

    if len(info) < 27:
        return None
    latitude = _parse_latitude(info[8:16])
    symbol_table = info[16]
    longitude = _parse_longitude(info[17:26])
    symbol_code = info[26]
    if latitude is None or longitude is None:
        return None
    result = {
        "entity_class": "stationary",
        "frame_type": "S",
        "frame_type_label": "S - stała",
        "packet_group": "position",
        "packet_group_label": _packet_group_label("position"),
        "packet_type_code": "position_timestamped",
        "latitude": latitude,
        "longitude": longitude,
        "symbol": f"{symbol_table}{symbol_code}",
        "comment": info[27:].strip(),
    }
    _attach_comment_extensions(result)
    return result


def _parse_latitude(value: str) -> str | None:
    if len(value) != 8 or value[4] != ".":
        return None
    try:
        degrees = int(value[0:2])
        minutes = float(value[2:7])
    except ValueError:
        return None
    hemisphere = value[7]
    decimal = degrees + (minutes / 60.0)
    if hemisphere == "S":
        decimal *= -1
    elif hemisphere != "N":
        return None
    return f"{decimal:.5f}"


def _parse_longitude(value: str) -> str | None:
    if len(value) != 9 or value[5] != ".":
        return None
    try:
        degrees = int(value[0:3])
        minutes = float(value[3:8])
    except ValueError:
        return None
    hemisphere = value[8]
    decimal = degrees + (minutes / 60.0)
    if hemisphere == "W":
        decimal *= -1
    elif hemisphere != "E":
        return None
    return f"{decimal:.5f}"


def _looks_like_compressed_position(info: str, *, with_timestamp: bool) -> bool:
    if with_timestamp:
        if len(info) < 21:
            return False
        symbol_table = info[8]
        lat_block = info[9:13]
        lon_block = info[13:17]
        symbol_code = info[17]
        cst_block = info[18:21]
    else:
        if len(info) < 14:
            return False
        symbol_table = info[1]
        lat_block = info[2:6]
        lon_block = info[6:10]
        symbol_code = info[10]
        cst_block = info[11:14]

    if not _is_valid_compressed_symbol_table(symbol_table):
        return False
    normalized_symbol_table = _normalize_compressed_symbol_table(symbol_table)
    if "0" <= normalized_symbol_table <= "9":
        if with_timestamp:
            if (
                len(info) >= 27
                and _parse_latitude(info[8:16]) is not None
                and _parse_longitude(info[17:26]) is not None
                and 33 <= ord(info[26]) <= 126
            ):
                return False
        else:
            if (
                len(info) >= 20
                and _parse_latitude(info[1:9]) is not None
                and _parse_longitude(info[10:19]) is not None
                and 33 <= ord(info[19]) <= 126
            ):
                return False
    if not _is_base91_block(lat_block) or not _is_base91_block(lon_block):
        return False
    if not _is_valid_compressed_cst_block(cst_block):
        return False
    return 33 <= ord(symbol_code) <= 126


def _parse_compressed_position(info: str, *, with_timestamp: bool) -> dict[str, Any] | None:
    if with_timestamp:
        symbol_table = _normalize_compressed_symbol_table(info[8])
        lat_block = info[9:13]
        lon_block = info[13:17]
        symbol_code = info[17]
        comment = info[21:].strip() if len(info) > 21 else ""
    else:
        symbol_table = _normalize_compressed_symbol_table(info[1])
        lat_block = info[2:6]
        lon_block = info[6:10]
        symbol_code = info[10]
        comment = info[14:].strip() if len(info) > 14 else ""

    try:
        lat_value = _base91_value(lat_block)
        lon_value = _base91_value(lon_block)
    except ValueError:
        return None

    latitude = 90.0 - (lat_value / 380926.0)
    longitude = -180.0 + (lon_value / 190463.0)
    result = {
        "entity_class": "stationary",
        "frame_type": "S",
        "frame_type_label": "S - stała",
        "packet_group": "position",
        "packet_group_label": _packet_group_label("position"),
        "packet_type_code": "position_compressed_timestamped" if with_timestamp else "position_compressed",
        "latitude": f"{latitude:.5f}",
        "longitude": f"{longitude:.5f}",
        "symbol": f"{symbol_table}{symbol_code}",
        "comment": comment,
    }
    _attach_comment_extensions(result)
    return result


def _parse_mic_e_packet(packet: dict[str, str]) -> dict[str, Any] | None:
    info = packet["info"]
    destination = packet["destination"]
    if len(destination) != 6 or len(info) < 9:
        return None

    mic_e_payload = info[9:] if len(info) > 9 else ""
    raw_type_byte = mic_e_payload[:1] if mic_e_payload else ""
    mic_e_comment, mic_e_altitude_ft = _decode_mic_e_comment(mic_e_payload)
    device_identification = lookup_aprs_device_identification(
        destination="",
        info=info,
        database=get_aprs_device_identification_database(),
    )

    latitude, position_ambiguity_digits = _decode_mic_e_latitude(destination)
    longitude = _decode_mic_e_longitude(destination, info)
    if latitude is None or longitude is None:
        return None

    symbol_code = info[7] if len(info) > 7 else ""
    symbol_table = info[8] if len(info) > 8 else "/"
    result = {
        "entity_class": "mobile",
        "frame_type": "M",
        "frame_type_label": "M - ruch",
        "packet_group": "position",
        "packet_group_label": _packet_group_label("position"),
        "packet_type_code": "mic_e",
        "latitude": latitude,
        "longitude": longitude,
        "symbol": f"{symbol_table}{symbol_code}" if symbol_code else "",
        "comment": mic_e_comment,
    }
    mice_message_code, mice_message = _decode_mic_e_message(destination)
    if mice_message is not None:
        result["mice_message"] = mice_message
        result["mice_message_code"] = mice_message_code
        if mice_message == "EMERGENCY":
            result["emergency"] = True
            result["emergency_source"] = "mic-e"
    if position_ambiguity_digits > 0:
        result["position_ambiguity_digits"] = position_ambiguity_digits
        result["position_ambiguous"] = True
    mic_e_movement = _decode_mic_e_speed_course(info)
    if mic_e_movement:
        result["data"] = mic_e_movement
    if mic_e_altitude_ft is not None:
        result.setdefault("data", {})["altitude_ft"] = mic_e_altitude_ft
    _attach_comment_extensions(result)
    mic_e_status = _MIC_E_STATUS_LABELS.get(mice_message_code) if mice_message_code is not None else None
    type_label, type_message_capable = _decode_mic_e_type_byte(raw_type_byte)
    message_capable = type_message_capable
    known_device_name = None
    raw_identifier = None
    if device_identification is not None:
        known_device_name = str(device_identification.get("short_name") or device_identification.get("identified_as") or "").strip() or None
        raw_identifier = str(device_identification.get("actual_identifier") or "").strip() or None
        if message_capable is None and device_identification.get("message_capable") is not None:
            message_capable = bool(device_identification.get("message_capable"))
    altitude_m = int(round(float(mic_e_altitude_ft) * 0.3048)) if mic_e_altitude_ft is not None else None
    mic_e_details = {
        "destination_raw": destination,
        "destination_is_encoded": True,
        "destination_is_tocall": False,
        "status": mic_e_status,
        "emergency": bool(result.get("emergency")),
        "device_name": known_device_name,
        "device_known": device_identification is not None,
        "device_type": type_label,
        "type_byte": type_label,
        "raw_identifier": raw_identifier,
        "raw_type_byte": raw_type_byte or None,
        "message_capable": message_capable,
        "speed_knots": mic_e_movement.get("speed_knots") if mic_e_movement else None,
        "speed_kmh": int(round(float(mic_e_movement["speed_knots"]) * 1.852)) if mic_e_movement and mic_e_movement.get("speed_knots") is not None else None,
        "course_deg": mic_e_movement.get("course_deg") if mic_e_movement else None,
        "altitude_m": altitude_m,
        "altitude_ft": mic_e_altitude_ft,
        "position_ambiguity": _format_mic_e_position_ambiguity(position_ambiguity_digits),
        "raw_mice_payload": mic_e_payload,
    }
    result["mic_e"] = mic_e_details
    return result


def _decode_mic_e_comment(raw_payload: str) -> tuple[str, int | None]:
    payload = re.sub(r"[\x00-\x1f\x7f]", " ", str(raw_payload or ""))
    if not payload:
        return "", None

    payload = payload.lstrip()
    if payload[:1] in {" ", ">", "]", "`", "'"}:
        payload = payload[1:].lstrip()

    altitude_ft = None
    if len(payload) >= 4 and payload[3] == "}":
        try:
            altitude_value = (
                8192 * _mic_e_base91_value(payload[0])
                + 91 * _mic_e_base91_value(payload[1])
                + _mic_e_base91_value(payload[2])
                - 10000
            )
        except ValueError:
            altitude_value = None
        else:
            altitude_ft = max(0, min(32700, altitude_value))
            payload = payload[4:].lstrip()

    return payload.strip(" /|,;:-"), altitude_ft


def _mic_e_base91_value(char: str) -> int:
    value = ord(char) - 33
    if value < 0 or value > 90:
        raise ValueError("Mic-E altitude byte out of range.")
    return value


def _decode_mic_e_type_byte(raw_type_byte: str) -> tuple[str | None, bool | None]:
    if raw_type_byte == " ":
        return "Original Mic-E", False
    if raw_type_byte == ">":
        return "Kenwood TH-D7A family", True
    if raw_type_byte == "]":
        return "Kenwood TM-D700 family", True
    if raw_type_byte == "`":
        return "Other Mic-E (message capable)", True
    if raw_type_byte == "'":
        return "Other Mic-E (tracker)", False
    return None, None


def _format_mic_e_position_ambiguity(position_ambiguity_digits: int) -> str:
    if position_ambiguity_digits <= 0:
        return "none"
    if position_ambiguity_digits == 1:
        return "1 digit"
    return f"{position_ambiguity_digits} digits"


def _decode_mic_e_latitude(destination: str) -> tuple[str | None, int]:
    digits: list[int] = []
    ambiguous_positions: list[int] = []
    for index, char in enumerate(destination):
        digit, is_ambiguity_space = _decode_mic_e_dest_digit(char)
        if digit is None:
            return None, 0
        if is_ambiguity_space:
            ambiguous_positions.append(index)
        digits.append(digit)

    position_ambiguity_digits = 0
    if ambiguous_positions:
        first_ambiguous_index = ambiguous_positions[0]
        expected_ambiguous_positions = list(range(first_ambiguous_index, len(destination)))
        if ambiguous_positions != expected_ambiguous_positions:
            return None, 0
        position_ambiguity_digits = len(ambiguous_positions)
        # APRS101 Mic-E allows ambiguity-space in destination bytes (e.g. L),
        # so we decode the latitude as the midpoint of the ambiguous suffix.
        digits[first_ambiguous_index] = 5
        for index in range(first_ambiguous_index + 1, len(destination)):
            digits[index] = 0

    latitude = (digits[0] * 10 + digits[1]) + ((digits[2] * 10 + digits[3]) + (digits[4] * 10 + digits[5]) / 100.0) / 60.0
    if not _mic_e_flag(destination[3]):
        latitude *= -1
    return f"{latitude:.5f}", position_ambiguity_digits


def _decode_mic_e_longitude(destination: str, info: str) -> str | None:
    if len(info) < 4:
        return None
    try:
        degrees = ord(info[1]) - 28
        if _mic_e_flag(destination[4]):
            degrees += 100
        if 180 <= degrees <= 189:
            degrees -= 80
        elif 190 <= degrees <= 199:
            degrees -= 190

        minutes = ord(info[2]) - 28
        if minutes >= 60:
            minutes -= 60

        hundredths = ord(info[3]) - 28
    except (IndexError, TypeError):
        return None

    longitude = degrees + (minutes + hundredths / 100.0) / 60.0
    if _mic_e_flag(destination[5]):
        longitude *= -1
    return f"{longitude:.5f}"


def _decode_mic_e_speed_course(info: str) -> dict[str, int] | None:
    if len(info) < 7:
        return None
    try:
        speed = (ord(info[4]) - 28) * 10 + ((ord(info[5]) - 28) // 10)
        course = (((ord(info[5]) - 28) % 10) * 100) + (ord(info[6]) - 28)
    except (IndexError, TypeError):
        return None

    if speed >= 800:
        speed -= 800
    if course >= 400:
        course -= 400
    return {
        "course_deg": course,
        "speed_knots": speed,
    }


def _decode_mic_e_message(destination: str) -> tuple[int | None, str | None]:
    if len(destination) != 6:
        return None, None

    bits = [
        0 if ("A" <= char <= "J" or "P" <= char <= "Y") else 1
        for char in destination[:3]
    ]
    message_code = 4 * bits[0] + 2 * bits[1] + bits[2]
    return message_code, _MIC_E_MESSAGE_LABELS.get(message_code)


def _decode_mic_e_dest_digit(char: str) -> tuple[int | None, bool]:
    if "0" <= char <= "9":
        return ord(char) - ord("0"), False
    if "A" <= char <= "J":
        return ord(char) - ord("A"), False
    if "P" <= char <= "Y":
        return ord(char) - ord("P"), False
    if char in {"K", "L", "Z"}:
        return 0, True
    return None, False


def _mic_e_flag(char: str) -> bool:
    return ("A" <= char <= "J") or ("P" <= char <= "Z")


def _parse_weather_only_packet(info: str) -> dict[str, Any] | None:
    weather = _parse_weather_fields(info)
    if not weather:
        return None
    return {
        "entity_class": "stationary",
        "frame_type": "W",
        "frame_type_label": "W - pogoda",
        "packet_group": "weather",
        "packet_group_label": _packet_group_label("weather"),
        "packet_type_code": "weather",
        "symbol": "/_",
        "comment": _clean_decoded_tokens(info),
        "data": weather,
    }


def _parse_object_packet(info: str) -> dict[str, Any] | None:
    if len(info) < 37:
        return None

    name = info[1:10].strip()
    if not name:
        return None

    state = "killed" if info[10] == "_" else "live"
    latitude = _parse_latitude(info[18:26])
    symbol_table = info[26]
    longitude = _parse_longitude(info[27:36])
    symbol_code = info[36]
    if latitude is None or longitude is None:
        return None

    result = {
        "entity_name": name,
        "entity_class": "object",
        "frame_type": "O",
        "frame_type_label": "O - obiekt",
        "packet_group": "object",
        "packet_group_label": _packet_group_label("object"),
        "packet_type_code": "object",
        "state": state,
        "latitude": latitude,
        "longitude": longitude,
        "symbol": f"{symbol_table}{symbol_code}",
        "comment": info[37:].strip(),
    }
    object_extension = _parse_object_extension(result["symbol"], result["comment"])
    if object_extension:
        result["data"] = object_extension
        result["comment"] = _clean_decoded_tokens(result["comment"])
    _attach_comment_extensions(result)
    return result


def _parse_item_packet(info: str) -> dict[str, Any] | None:
    if len(info) < 5:
        return None
    delimiter_index = next((index for index in range(2, min(len(info), 11)) if info[index] in {"!", "_"}), None)
    if delimiter_index is None:
        return None
    name = info[1:delimiter_index].strip()
    if len(name) < 3 or len(name) > 9:
        return None
    return {
        "entity_name": name,
        "packet_group": "item",
        "packet_group_label": _packet_group_label("item"),
        "packet_type_code": "item",
        "comment": info[delimiter_index + 1 :].strip(),
    }


def _parse_status_packet(info: str) -> dict[str, Any] | None:
    return {
        "packet_group": "status",
        "packet_group_label": _packet_group_label("status"),
        "packet_type_code": "status",
        "comment": info[1:].strip(),
    }


def _parse_message_packet(info: str) -> dict[str, Any] | None:
    separator_index = info.find(":", 1)
    addressee = ""
    text_field = ""
    if separator_index != -1 and 1 < separator_index <= 10:
        addressee = info[1:separator_index].rstrip()
        text_field = info[separator_index + 1 :]
    if text_field:
        upper_text = text_field.upper()
        upper_addressee = addressee.upper()
        if upper_addressee.startswith("BLN"):
            return {
                "packet_group": "message",
                "packet_group_label": _packet_group_label("message"),
                "packet_type_code": _bulletin_packet_type_code(upper_addressee),
                "comment": text_field.strip(),
                "addressee": addressee,
            }
        if upper_text.startswith("?"):
            return {
                "packet_group": "query",
                "packet_group_label": _packet_group_label("query"),
                "packet_type_code": "query",
                "comment": text_field.strip(),
                "addressee": addressee,
            }
        if _ACK_MESSAGE_RE.fullmatch(text_field):
            return {
                "packet_group": "message",
                "packet_group_label": _packet_group_label("message"),
                "packet_type_code": "ack",
                "comment": text_field.strip(),
                "addressee": addressee,
            }
        if _REJECT_MESSAGE_RE.fullmatch(text_field):
            return {
                "packet_group": "message",
                "packet_group_label": _packet_group_label("message"),
                "packet_type_code": "reject",
                "comment": text_field.strip(),
                "addressee": addressee,
            }
        if upper_text.startswith(_TELEMETRY_MESSAGE_PREFIXES):
            return {
                "packet_group": "telemetry",
                "packet_group_label": _packet_group_label("telemetry"),
                "packet_type_code": "telemetry_definition",
                "comment": text_field.strip(),
                "addressee": addressee,
            }
        suffix_match = _MESSAGE_SUFFIX_RE.fullmatch(text_field)
        message_text = str((suffix_match.group("text") if suffix_match else text_field) or "").strip()
        return {
            "packet_group": "message",
            "packet_group_label": _packet_group_label("message"),
            "packet_type_code": "message",
            "comment": message_text,
            "addressee": addressee,
        }

    return {
        "packet_group": "message",
        "packet_group_label": _packet_group_label("message"),
        "packet_type_code": "message",
        "comment": info[1:].strip(),
        "addressee": addressee,
    }


def _parse_telemetry_packet(info: str) -> dict[str, Any] | None:
    return {
        "packet_group": "telemetry",
        "packet_group_label": _packet_group_label("telemetry"),
        "packet_type_code": "telemetry",
        "comment": info.strip(),
    }


def _parse_third_party_packet(packet: dict[str, str]) -> dict[str, Any] | None:
    info = packet["info"]
    encapsulated = info[1:].lstrip()
    outer_source = str(packet.get("source") or "").strip()
    outer_destination = str(packet.get("destination") or "").strip()
    outer_path = str(packet.get("path") or "").strip()
    base_result: dict[str, Any] = {
        "packet_type_code": "third_party",
        "comment": encapsulated,
        "is_third_party": True,
        "third_party_inner_valid": False,
        "outer_source": outer_source,
        "outer_destination": outer_destination,
        "outer_path": outer_path,
        "third_party_payload": encapsulated,
    }
    parsed = _parse_tnc2_line(encapsulated)
    if parsed is None:
        return base_result
    base_result["inner_source_key"] = parsed["source"]
    base_result["inner_destination"] = parsed["destination"]
    base_result["inner_path"] = parsed["path"]
    base_result["inner_info"] = parsed["info"]
    embedded = _parse_aprs_packet(parsed)
    if embedded is None:
        return base_result
    result = dict(embedded)
    result["is_third_party"] = True
    result["third_party_inner_valid"] = True
    result["outer_source"] = outer_source
    result["outer_destination"] = outer_destination
    result["outer_path"] = outer_path
    result["third_party_payload"] = encapsulated
    result["inner_source_key"] = parsed["source"]
    result["inner_destination"] = parsed["destination"]
    result["inner_path"] = parsed["path"]
    result["inner_info"] = parsed["info"]
    result["wrapped_packet_type_code"] = str(embedded.get("packet_type_code") or "")
    result["encapsulation_packet_type_code"] = "third_party"
    return result


def _bulletin_packet_type_code(addressee: str) -> str:
    normalized = str(addressee or "").strip().upper()
    if re.fullmatch(r"BLN[A-Z]", normalized):
        return "announcement"
    if re.fullmatch(r"BLN[0-9][A-Z0-9]{1,5}", normalized):
        return "group_bulletin"
    return "bulletin"


def _packet_group_label(group: str) -> str:
    return _PACKET_GROUP_LABELS.get(str(group or "").strip().casefold(), "")


def _parse_weather_fields(text: str) -> dict[str, float | int] | None:
    if not text:
        return None

    metrics: dict[str, float | int] = {}
    wind_dir = _match_group(text, r"c(\d{3})")
    wind_speed = _match_group(text, r"s(\d{3})")
    wind_gust = _match_group(text, r"g(\d{3})")
    temperature = _match_group(text, r"t(-?\d{3})")
    rain_1h = _match_group(text, r"r(\d{3})")
    rain_24h = _match_group(text, r"p(\d{3})")
    rain_midnight = _match_group(text, r"P(\d{3})")
    humidity = _match_group(text, r"h(\d{2})")
    pressure = _match_group(text, r"b(\d{5})")
    radiation = _match_group(text, r"[Xx](\d{3})")

    if wind_dir:
        metrics["wind_dir"] = int(wind_dir)
    if wind_speed:
        metrics["wind_speed_mph"] = int(wind_speed)
    if wind_gust:
        metrics["wind_gust_mph"] = int(wind_gust)
    if temperature:
        metrics["temperature_f"] = int(temperature)
    if rain_1h:
        metrics["rain_1h_in"] = int(rain_1h) / 100
    if rain_24h:
        metrics["rain_24h_in"] = int(rain_24h) / 100
    if rain_midnight:
        metrics["rain_since_midnight_in"] = int(rain_midnight) / 100
    if humidity:
        humidity_value = 100 if humidity == "00" else int(humidity)
        metrics["humidity_percent"] = humidity_value
    if pressure:
        metrics["pressure_hpa"] = int(pressure) / 10
    if radiation:
        mantissa = int(radiation[:2])
        exponent = int(radiation[2])
        metrics["radiation_nsv_h"] = float(mantissa * (10**exponent))

    return metrics or None


def _attach_comment_extensions(result: dict[str, Any]) -> None:
    comment = result.get("comment", "") or ""
    data: dict[str, Any] = dict(result.get("data", {}) or {})
    preserve_qsy_callsign_in_comment = False
    is_weather_context = bool(result.get("packet_group") == "weather" or result.get("symbol", "").endswith("_"))
    if str(result.get("symbol") or "").strip() == "\\!":
        result["emergency"] = True
        result.setdefault("emergency_code", "EMERGENCY")
    emergency_token = _extract_emergency_comment_token(comment)
    if emergency_token is not None or bool(result.get("emergency")):
        result["emergency"] = True
    if emergency_token is not None:
        result["emergency_code"] = emergency_token
    if bool(result.get("emergency")) and comment:
        result["emergency_comment"] = str(comment).strip()
    if result.get("symbol", "").endswith("_"):
        weather = _parse_weather_fields(comment)
        if weather:
            data.update(weather)

    phg = _parse_phg_fields(comment)
    if phg:
        data.update(phg)

    if not is_weather_context:
        movement = _parse_course_speed_fields(comment)
        if movement:
            data.update(movement)
            result["entity_class"] = "mobile"
            result["frame_type"] = "M"
            result["frame_type_label"] = "M - ruch"

    altitude = _parse_altitude_fields(comment)
    if altitude:
        data.update(altitude)

    qsy = _parse_qsy_fields(comment)
    if qsy:
        if result.get("entity_class") == "mobile":
            qsy.pop("qsy_callsign", None)
            preserve_qsy_callsign_in_comment = True
        data.update(qsy)

    if data:
        result["data"] = data
    if comment:
        cleaned_comment = _clean_decoded_tokens(comment, preserve_qsy_callsign=preserve_qsy_callsign_in_comment)
        if data or cleaned_comment != comment:
            result["comment"] = cleaned_comment


def _parse_phg_fields(text: str) -> dict[str, Any] | None:
    match = re.search(r"PHG(\d)(\d)(\d)(\d)", text)
    if not match:
        return None

    power_code, height_code, gain_code, direction_code = (int(value) for value in match.groups())
    direction_map = {
        0: "omni",
        1: "NE",
        2: "E",
        3: "SE",
        4: "S",
        5: "SW",
        6: "W",
        7: "NW",
        8: "N",
    }
    result: dict[str, Any] = {
        "phg_power_w": power_code * power_code,
        "phg_height_ft": 10 * (2**height_code),
        "phg_gain_dbi": gain_code,
        "phg_direction": direction_map.get(direction_code, str(direction_code)),
    }
    return result


def _parse_course_speed_fields(text: str) -> dict[str, Any] | None:
    match = re.search(r"(?<!\d)(\d{3})/(\d{3})(?!\d)", text)
    if not match:
        return None

    course, speed = (int(value) for value in match.groups())
    if course > 360:
        return None
    return {
        "course_deg": course,
        "speed_knots": speed,
    }


def _parse_altitude_fields(text: str) -> dict[str, Any] | None:
    match = re.search(r"(?:^|[\s/])A=(\d{6})", text)
    if not match:
        return None
    return {"altitude_ft": int(match.group(1))}


def _parse_object_extension(symbol: str, text: str) -> dict[str, Any] | None:
    if symbol != "\\l":
        return None
    match = re.search(r"([0-9])([0-9]{2})/([0-9A-F])([0-9]{2})", text)
    if not match:
        return None

    shape_code, lat_offset, color_code, lon_offset = match.groups()
    shape_map = {
        "0": "Okrąg otwarty",
        "1": "Linia prawa-dół",
        "2": "Elipsa otwarta",
        "3": "Trójkąt otwarty",
        "4": "Prostokąt otwarty",
        "5": "Okrąg wypełniony",
        "6": "Linia lewa-dół",
        "7": "Elipsa wypełniona",
        "8": "Trójkąt wypełniony",
        "9": "Prostokąt wypełniony",
    }
    color_map = {
        "0": "Czarny jasny",
        "1": "Niebieski jasny",
        "2": "Zielony jasny",
        "3": "Cyjan jasny",
        "4": "Czerwony jasny",
        "5": "Fiolet jasny",
        "6": "Żółty jasny",
        "7": "Szary jasny",
        "8": "Czarny ciemny",
        "9": "Niebieski ciemny",
        "A": "Zielony ciemny",
        "B": "Cyjan ciemny",
        "C": "Czerwony ciemny",
        "D": "Fiolet ciemny",
        "E": "Żółty ciemny",
        "F": "Szary ciemny",
    }
    return {
        "object_shape": shape_map.get(shape_code, shape_code),
        "object_color": color_map.get(color_code, color_code),
        "object_lat_offset_hundredths": int(lat_offset),
        "object_lon_offset_hundredths": int(lon_offset),
    }


def _parse_qsy_fields(text: str) -> dict[str, Any] | None:
    match = re.search(
        r"(?i)(?P<frequency>\d{3}\.\d{3,4})mhz(?:\s+(?P<tone>[CT]\d{3}))?(?:\s+(?P<offset>[+-]\d{3,4}))?(?:\s+R(?P<range>\d+(?:\.\d+)?)k)?(?:\s+(?P<callsign>[A-Z0-9-]{3,10}))?",
        text,
    )
    if not match:
        return None

    result: dict[str, Any] = {
        "qsy_frequency_mhz": float(match.group("frequency")),
    }
    tone = match.group("tone")
    if tone:
        result["qsy_tone"] = tone
    offset = match.group("offset")
    if offset:
        result["qsy_offset_khz"] = int(offset)
    qsy_range = match.group("range")
    if qsy_range:
        result["qsy_range_km"] = float(qsy_range)
    qsy_callsign = match.group("callsign")
    if qsy_callsign:
        result["qsy_callsign"] = qsy_callsign
    return result


def _clean_decoded_tokens(text: str, *, preserve_qsy_callsign: bool = False) -> str:
    cleaned = text
    cleaned = re.sub(r'^[A-Za-z`"\',}\]>{<\[\(0-9-]{1,6}(?=\d{3}\.\d{3,4}(?i:mhz))', " ", cleaned)
    cleaned = re.sub(r'^(?:[/\\`"\',}{\]\[\(\)!@#$%^&*+=:;?.<>0-9-]{2,8})\s*(?=[A-Za-zĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż_])', " ", cleaned)
    cleaned = re.sub(r"^_?\d{8}", "", cleaned)
    cleaned = re.sub(r"\|[!-{]{4,14}\|", " ", cleaned)
    cleaned = re.sub(r"![Ww][!-{]{2}!", " ", cleaned)
    cleaned = re.sub(r"(?:c\d{3}|s\d{3}|g\d{3}|t-?\d{3}|r\d{3}|p\d{3}|P\d{3}|h\d{2}|b\d{5}|[Xx]\d{3})", " ", cleaned)
    cleaned = re.sub(r"PHG\d{4}", " ", cleaned)
    cleaned = re.sub(r"(?<!\d)\d{3}/\d{3}(?!\d)", " ", cleaned)
    cleaned = re.sub(r"(?:^|[\s/])A=\d{6}", " ", cleaned)
    cleaned = re.sub(r"[0-9][0-9]{2}/[0-9][0-9]{2}", " ", cleaned)
    qsy_pattern = r"(?i)\d{3}\.\d{3,4}mhz(?:\s+[CT]\d{3})?(?:\s+[+-]\d{3,4})?(?:\s+R\d+(?:\.\d+)?k)?"
    if preserve_qsy_callsign:
        cleaned = re.sub(qsy_pattern, " ", cleaned)
    else:
        cleaned = re.sub(qsy_pattern + r"(?:\s+[A-Z0-9-]{3,10})?", " ", cleaned)
    cleaned = re.sub(r'^(?:[/\\`"\',}{\]\[\(\)!@#$%^&*+=:;?.<>0-9-]{2,8})\s*(?=[A-Za-zĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż_])', " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" /|,;:-")


def _format_qsy_offset_display(offset_code: Any) -> str | None:
    try:
        offset_steps = int(offset_code)
    except (TypeError, ValueError):
        return None

    offset_khz = offset_steps * 10
    if abs(offset_khz) >= 1000:
        value_mhz = offset_khz / 1000.0
        value_text = f"{value_mhz:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        if offset_khz > 0 and not value_text.startswith("+"):
            value_text = f"+{value_text}"
        return f"{value_text}MHz"

    if offset_khz > 0:
        return f"+{offset_khz}kHz"
    return f"{offset_khz}kHz"


def _format_decoded_data_for_display(metrics: dict[str, float | int | str], unit_system: str) -> list[dict[str, str]]:
    if not metrics:
        return []

    use_imperial = unit_system == "imperial"
    items: list[dict[str, str]] = []

    wind_dir = metrics.get("wind_dir")
    if wind_dir is not None:
        items.append(_weather_item("compass-outline.svg", "Kierunek wiatru", f"{int(wind_dir)}°"))

    wind_speed_mph = metrics.get("wind_speed_mph")
    if wind_speed_mph is not None:
        value = f"{float(wind_speed_mph):.0f} mph" if use_imperial else f"{float(wind_speed_mph) * 1.609344:.0f} km/h"
        items.append(_weather_item("weather-windy.svg", "Prędkość wiatru", value))

    wind_gust_mph = metrics.get("wind_gust_mph")
    if wind_gust_mph is not None:
        value = f"{float(wind_gust_mph):.0f} mph" if use_imperial else f"{float(wind_gust_mph) * 1.609344:.0f} km/h"
        items.append(_weather_item("weather-windy-variant.svg", "Porywy", value))

    temperature_f = metrics.get("temperature_f")
    if temperature_f is not None:
        value = f"{float(temperature_f):.0f}°F" if use_imperial else f"{(float(temperature_f) - 32.0) * 5.0 / 9.0:.1f}°C"
        items.append(_weather_item("thermometer.svg", "Temperatura", value))

    rain_1h_in = metrics.get("rain_1h_in")
    if rain_1h_in is not None:
        value = f"{float(rain_1h_in):.2f} in" if use_imperial else f"{float(rain_1h_in) * 25.4:.1f} mm"
        items.append(_weather_item("weather-rainy.svg", "Deszcz 1h", value))

    rain_24h_in = metrics.get("rain_24h_in")
    if rain_24h_in is not None:
        value = f"{float(rain_24h_in):.2f} in" if use_imperial else f"{float(rain_24h_in) * 25.4:.1f} mm"
        items.append(_weather_item("weather-pouring.svg", "Deszcz 24h", value))

    rain_since_midnight_in = metrics.get("rain_since_midnight_in")
    if rain_since_midnight_in is not None:
        value = f"{float(rain_since_midnight_in):.2f} in" if use_imperial else f"{float(rain_since_midnight_in) * 25.4:.1f} mm"
        items.append(_weather_item("cup-water.svg", "Deszcz od północy", value))

    humidity_percent = metrics.get("humidity_percent")
    if humidity_percent is not None:
        items.append(_weather_item("water-percent.svg", "Wilgotność", f"{int(humidity_percent)}%"))

    pressure_hpa = metrics.get("pressure_hpa")
    if pressure_hpa is not None:
        items.append(_weather_item("gauge.svg", "Ciśnienie", f"{float(pressure_hpa):.1f} hPa"))

    radiation_nsv_h = metrics.get("radiation_nsv_h")
    if radiation_nsv_h is not None:
        radiation_value = float(radiation_nsv_h)
        if radiation_value >= 1_000_000:
            value = f"{radiation_value / 1_000_000:.3f} mSv/h"
        elif radiation_value >= 1_000:
            value = f"{radiation_value / 1_000:.2f} µSv/h"
        else:
            value = f"{radiation_value:.0f} nSv/h"
        items.append(_weather_item("radioactive.svg", "Promieniowanie", value))

    phg_power_w = metrics.get("phg_power_w")
    if phg_power_w is not None:
        items.append(_weather_item("gauge.svg", "Moc PHG", f"{int(phg_power_w)} W"))

    phg_height_ft = metrics.get("phg_height_ft")
    if phg_height_ft is not None:
        value = f"{int(phg_height_ft)} ft" if use_imperial else f"{int(round(float(phg_height_ft) * 0.3048))} m"
        items.append(_weather_item("arrow-up.svg", "Wysokość PHG", value))

    phg_gain_dbi = metrics.get("phg_gain_dbi")
    if phg_gain_dbi is not None:
        items.append(_weather_item("speedometer.svg", "Zysk PHG", f"{int(phg_gain_dbi)} dBi"))

    phg_direction = metrics.get("phg_direction")
    if phg_direction is not None:
        items.append(_weather_item("compass-outline.svg", "Kierunek PHG", str(phg_direction)))

    object_shape = metrics.get("object_shape")
    if object_shape is not None:
        items.append(_weather_item("shape-outline.svg", "Kształt obiektu", str(object_shape)))

    object_color = metrics.get("object_color")
    if object_color is not None:
        items.append(_weather_item("palette.svg", "Kolor obiektu", str(object_color)))

    object_lat_offset_hundredths = metrics.get("object_lat_offset_hundredths")
    if object_lat_offset_hundredths is not None:
        items.append(_weather_item("arrow-down.svg", "Offset Y", f"{int(object_lat_offset_hundredths) / 100:.2f}°"))

    object_lon_offset_hundredths = metrics.get("object_lon_offset_hundredths")
    if object_lon_offset_hundredths is not None:
        items.append(_weather_item("arrow-right.svg", "Offset X", f"{int(object_lon_offset_hundredths) / 100:.2f}°"))

    qsy_frequency_mhz = metrics.get("qsy_frequency_mhz")
    if qsy_frequency_mhz is not None:
        items.append(_weather_item("radio-handheld.svg", "QSY", f"{float(qsy_frequency_mhz):.3f} MHz"))

    qsy_tone = metrics.get("qsy_tone")
    if qsy_tone is not None:
        items.append(_weather_item("radio.svg", "Ton", str(qsy_tone)))

    qsy_offset_khz = metrics.get("qsy_offset_khz")
    if qsy_offset_khz is not None:
        offset_display = _format_qsy_offset_display(qsy_offset_khz)
        if offset_display is not None:
            items.append(_weather_item("signal-distance-variant.svg", "Offset", offset_display))

    qsy_range_km = metrics.get("qsy_range_km")
    if qsy_range_km is not None:
        items.append(_weather_item("map-marker-distance.svg", "Zasięg", f"{float(qsy_range_km):g} km"))

    qsy_callsign = metrics.get("qsy_callsign")
    if qsy_callsign is not None:
        items.append(_weather_item("antenna.svg", "Przemiennik", str(qsy_callsign)))

    course_deg = metrics.get("course_deg")
    if course_deg is not None:
        items.append(_weather_item("navigation-outline.svg", "Kurs", f"{int(course_deg)}°"))

    speed_knots = metrics.get("speed_knots")
    if speed_knots is not None:
        value = f"{int(round(float(speed_knots) * 1.15078))} mph" if use_imperial else f"{int(round(float(speed_knots) * 1.852))} km/h"
        items.append(_weather_item("speedometer.svg", "Prędkość", value))

    altitude_ft = metrics.get("altitude_ft")
    if altitude_ft is not None:
        value = f"{int(altitude_ft)} ft" if use_imperial else f"{int(round(float(altitude_ft) * 0.3048))} m"
        items.append(_weather_item("arrow-up.svg", "Wysokość", value))

    return items


def _weather_item(icon: str, label: str, value: str) -> dict[str, str]:
    return {"icon": icon, "label": label, "value": value}


def _match_group(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _is_base91_block(value: str) -> bool:
    return len(value) == 4 and all(33 <= ord(char) <= 123 for char in value)


def _normalize_compressed_symbol_table(symbol_table: str) -> str:
    if len(symbol_table) == 1 and "a" <= symbol_table <= "j":
        return chr(ord(symbol_table) - 49)
    return symbol_table


def _is_valid_compressed_symbol_table(symbol_table: str) -> bool:
    normalized = _normalize_compressed_symbol_table(symbol_table)
    if normalized in {"/", "\\"}:
        return True
    if len(normalized) != 1:
        return False
    return ("0" <= normalized <= "9") or ("A" <= normalized <= "Z")


def _is_valid_compressed_cst_block(cst_block: str) -> bool:
    if len(cst_block) != 3:
        return False
    for char in cst_block:
        code = ord(char)
        if code == 32:
            continue
        if code < 33 or code > 123:
            return False
    return True


def _base91_value(value: str) -> int:
    total = 0
    for char in value:
        code = ord(char)
        if code < 33 or code > 123:
            raise ValueError("Out of base91 range")
        total = total * 91 + (code - 33)
    return total


def _aprs_symbol_icon_path(symbol: str) -> str:
    current_set = get_aprs_symbol_set()
    alternate_set = APRS_SYMBOL_SET_LEGACY if current_set == APRS_SYMBOL_SET_MODERN else APRS_SYMBOL_SET_MODERN
    for symbol_set in (current_set, alternate_set):
        candidate = _aprs_symbol_icon_path_for_set(symbol, symbol_set)
        if candidate is not None:
            return candidate
    return get_aprs_symbol_icon_fallback_path()


def get_aprs_symbol_icon_path(symbol: str) -> str:
    return _aprs_symbol_icon_path(symbol)


def safe_create_section_row(slug: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        create_section_row(slug, payload)
    except ValueError as exc:
        return False, str(exc)
    except sqlite3.IntegrityError as exc:
        if "idx_modems_single_aprsis" in str(exc) or "modems.modem_type" in str(exc):
            return False, "An APRSIS interface already exists. Edit the existing interface instead."
        return False, str(exc)
    return True, None


def safe_update_section_row(slug: str, row_id: int, payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        update_section_row(slug, row_id, payload)
    except ValueError as exc:
        return False, str(exc)
    except sqlite3.IntegrityError as exc:
        if "idx_modems_single_aprsis" in str(exc) or "modems.modem_type" in str(exc):
            return False, "An APRSIS interface already exists. Edit the existing interface instead."
        return False, str(exc)
    return True, None


def _normalize_section_payload(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "modems":
        return _normalize_modem_payload(payload)
    if slug == "objects":
        return _normalize_aprs_entity_payload("object", payload)
    if slug == "items":
        return _normalize_aprs_entity_payload("item", payload)
    if slug == "bulletins":
        return _normalize_aprs_message_payload(payload)
    return payload


def _normalize_modem_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    modem_type = str(payload.get("modem_type") or "").strip().upper()
    if modem_type == "SERIAL":
        modem_type = "SERIALL"
    supported_modem_types = set(TX_CAPABLE_MODEM_TYPES) | {OPENWEBRX_MQTT_MODEM_TYPE, APRSIS_MODEM_TYPE}
    if modem_type not in supported_modem_types:
        raise ValueError("Unsupported interface type.")

    normalized["modem_type"] = modem_type
    normalized["name"] = str(payload.get("name") or "").strip()
    normalized["band"] = str(payload.get("band") or "").strip().lower()
    if normalized["band"] not in {"", "2m", "70cm"}:
        raise ValueError("Band condition assessment must be disabled, 2m or 70cm.")
    if modem_type == APRSIS_MODEM_TYPE:
        normalized["band"] = ""
        normalized["device_path"] = normalize_aprsis_filter(payload.get("device_path"))
        normalized["baud_rate"] = None
        normalized["serial_rx_silence_reconnect_seconds"] = SERIAL_RX_SILENCE_TIMEOUT_DEFAULT_SECONDS
        normalized["tx_blocked"] = 1
        normalized["tx_min_gap_seconds"] = MODEM_TX_MIN_GAP_SECONDS_DEFAULT
        normalized["expose_port_enabled"] = 0
        normalized["expose_allow_tx"] = 0
        normalized["expose_bind_address"] = "0.0.0.0"
        normalized["expose_port"] = 8002
        normalized["expose_whitelist"] = ""
        return normalized
    if modem_type == OPENWEBRX_MQTT_MODEM_TYPE:
        endpoint = parse_mqtt_url(payload.get("device_path"), label="OpenWebRX MQTT URL")
        normalized["device_path"] = endpoint.normalized_url
        normalized["baud_rate"] = None
        normalized["tx_blocked"] = 1
        normalized["expose_port_enabled"] = 0
        normalized["expose_allow_tx"] = 0
        normalized["expose_bind_address"] = "0.0.0.0"
        normalized["expose_port"] = 8002
        normalized["expose_whitelist"] = ""
        normalized["tx_min_gap_seconds"] = _normalize_modem_tx_min_gap_seconds(payload.get("tx_min_gap_seconds"))
        normalized["serial_rx_silence_reconnect_seconds"] = _normalize_serial_rx_silence_timeout_seconds(
            payload.get("serial_rx_silence_reconnect_seconds")
        )
        return normalized

    expose_port_enabled = int(bool(payload.get("expose_port_enabled")))
    expose_bind_address = _normalize_ipv4_address(
        payload.get("expose_bind_address"),
        default="0.0.0.0",
        label="Bind address",
    )
    expose_port = _normalize_tcp_port(payload.get("expose_port"), default=8002, label="Expose port")
    expose_whitelist = _normalize_ip_whitelist(payload.get("expose_whitelist"))

    normalized["expose_port_enabled"] = expose_port_enabled
    normalized["expose_bind_address"] = expose_bind_address
    normalized["expose_port"] = expose_port
    normalized["expose_whitelist"] = expose_whitelist
    if modem_type == "SERIALL":
        normalized["device_path"] = normalize_serial_device_path(payload.get("device_path"))
        normalized["baud_rate"] = normalize_serial_baud_rate(payload.get("baud_rate"))
    else:
        normalized["device_path"] = str(payload.get("device_path") or "").strip()
        normalized["baud_rate"] = None
    normalized["tx_min_gap_seconds"] = _normalize_modem_tx_min_gap_seconds(payload.get("tx_min_gap_seconds"))
    normalized["serial_rx_silence_reconnect_seconds"] = _normalize_serial_rx_silence_timeout_seconds(
        payload.get("serial_rx_silence_reconnect_seconds")
    )
    return normalized


def _ensure_single_aprsis_interface(*, exclude_id: int | None = None) -> None:
    query = "SELECT id FROM modems WHERE UPPER(modem_type) = 'APRSIS'"
    params: tuple[Any, ...] = ()
    if exclude_id is not None:
        query += " AND id <> ?"
        params = (int(exclude_id),)
    query += " LIMIT 1"
    existing = fetch_one(query, params)
    if existing is not None:
        raise ValueError("An APRSIS interface already exists. Edit the existing interface instead.")


def _normalize_aprs_entity_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    name = _normalize_printable_ascii(str(payload.get("name") or "").strip())
    if kind == "object":
        if not name:
            raise ValueError("Object name is required.")
        if len(name) > 9:
            raise ValueError("Object name must be 1-9 printable ASCII characters.")
        lifetime = str(payload.get("lifetime") or "temporary").strip().lower()
        if lifetime not in {"temporary", "permanent"}:
            raise ValueError("Object lifetime must be temporary or permanent.")
        normalized["lifetime"] = lifetime
    else:
        if len(name) < 3 or len(name) > 9:
            raise ValueError("Item name must be 3-9 printable ASCII characters.")
        if "!" in name or "_" in name:
            raise ValueError("Item name cannot contain ! or _.")
    normalized["name"] = name

    state = str(payload.get("state") or "live").strip().lower()
    if state not in {"live", "killed"}:
        raise ValueError(f"{kind.capitalize()} state must be live or killed.")
    normalized["state"] = state

    latitude = str(payload.get("latitude") or "").strip()
    longitude = str(payload.get("longitude") or "").strip()
    if bool(latitude) != bool(longitude):
        raise ValueError(f"{kind.capitalize()} requires both latitude and longitude, or neither.")
    if latitude:
        _validate_coordinate(latitude, minimum=-90.0, maximum=90.0, label="Latitude")
        _validate_coordinate(longitude, minimum=-180.0, maximum=180.0, label="Longitude")
    normalized["latitude"] = latitude
    normalized["longitude"] = longitude

    symbol_table = str(payload.get("symbol_table") or "/").strip()
    if symbol_table not in {"/", "\\"}:
        raise ValueError("Symbol table must be / or \\.")
    normalized["symbol_table"] = symbol_table

    symbol_code = _normalize_symbol_code_value(payload.get("symbol_code"))
    normalized["symbol_code"] = symbol_code
    normalized["symbol_overlay"] = _normalize_symbol_overlay_value(payload.get("symbol_overlay"), symbol_table=symbol_table)

    try:
        interval_minutes = int(str(payload.get("interval_minutes") or "30").strip())
    except ValueError as exc:
        raise ValueError("Send interval must be one of: 5, 10, 15, 30, 45, 60 minutes.") from exc
    if interval_minutes not in {5, 10, 15, 30, 45, 60}:
        raise ValueError("Send interval must be one of: 5, 10, 15, 30, 45, 60 minutes.")
    normalized["interval_minutes"] = interval_minutes
    valid_until_utc, activation_schedule = _normalize_aprs_activation_payload(payload)
    normalized["valid_until_utc"] = valid_until_utc
    normalized.update(activation_schedule)

    path = _normalize_printable_ascii(str(payload.get("path") or "").strip().upper())
    if len(path) > 64:
        raise ValueError("Future RF path must be 64 printable ASCII characters or fewer.")
    normalized["path"] = path

    comment = _normalize_printable_ascii(str(payload.get("comment") or "").strip())
    if kind == "object" and not comment:
        raise ValueError("Object comment is required.")
    if len(comment) > 43:
        raise ValueError("Comment must be 43 printable ASCII characters or fewer.")
    normalized["comment"] = comment
    return normalized


def _normalize_aprs_message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    message_kind = str(payload.get("message_kind") or "bulletin").strip().lower()
    if message_kind not in {"bulletin", "announcement", "group_bulletin"}:
        raise ValueError("Type must be bulletin, announcement or group bulletin.")
    normalized["message_kind"] = message_kind

    bulletin_code = str(payload.get("bulletin_code") or "").strip().upper()
    group_name = str(payload.get("group_name") or "").strip().upper()

    if message_kind in {"bulletin", "group_bulletin"}:
        if not re.fullmatch(r"[0-9]", bulletin_code):
            raise ValueError("Bulletin code must be a single digit from 0 to 9.")
    elif message_kind == "announcement":
        if not re.fullmatch(r"[A-Z]", bulletin_code):
            raise ValueError("Announcement code must be a single letter from A to Z.")
    else:
        bulletin_code = ""

    if message_kind == "group_bulletin":
        if not re.fullmatch(r"[A-Z0-9]{1,5}", group_name):
            raise ValueError("Group must be 1-5 characters: A-Z or 0-9.")
    else:
        group_name = ""

    try:
        interval_minutes = int(str(payload.get("interval_minutes") or "30").strip())
    except ValueError as exc:
        raise ValueError("Send interval must be one of: 5, 10, 15, 30, 45, 60 minutes.") from exc
    if interval_minutes not in {5, 10, 15, 30, 45, 60}:
        raise ValueError("Send interval must be one of: 5, 10, 15, 30, 45, 60 minutes.")

    valid_until_utc, activation_schedule = _normalize_aprs_activation_payload(payload)
    normalized["valid_until_utc"] = valid_until_utc
    normalized.update(activation_schedule)

    path = _normalize_printable_ascii(str(payload.get("path") or "").strip().upper())
    if len(path) > 64:
        raise ValueError("Future RF path must be 64 printable ASCII characters or fewer.")

    message_text = _normalize_aprs_message_text(str(payload.get("message_text") or "").strip())
    if not message_text:
        raise ValueError("Message text is required.")

    normalized["bulletin_code"] = bulletin_code
    normalized["group_name"] = group_name
    normalized["interval_minutes"] = interval_minutes
    normalized["path"] = path
    normalized["message_text"] = message_text
    return normalized


def _normalize_symbol_code_value(value: Any) -> str:
    text = str(value or ">").strip()
    if len(text) != 1:
        raise ValueError("Symbol code must be a single printable ASCII character.")
    codepoint = ord(text)
    if codepoint < 33 or codepoint > 126:
        raise ValueError("Symbol code must be a single printable ASCII character.")
    return text


def _normalize_symbol_overlay_value(value: Any, *, symbol_table: str) -> str | None:
    if symbol_table != "\\":
        return None
    text = str(value or "").strip().upper()
    if not text or text == "NONE":
        return None
    if len(text) != 1 or not ("0" <= text <= "9" or "A" <= text <= "Z"):
        raise ValueError("Symbol overlay must be one of: None, 0-9, A-Z.")
    return text


def _coerce_symbol_overlay_value(value: Any, *, symbol_table: str) -> str:
    if symbol_table != "\\":
        return ""
    text = str(value or "").strip().upper()
    if len(text) == 1 and ("0" <= text <= "9" or "A" <= text <= "Z"):
        return text
    return ""


def _normalize_printable_ascii(value: str) -> str:
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise ValueError("Only printable ASCII characters are allowed in APRS object/item fields.")
    return value


def _ensure_printable_station_ascii(value: str, *, label: str) -> str:
    try:
        return _normalize_printable_ascii(value)
    except ValueError as exc:
        raise ValueError(f"{label} may contain only printable ASCII characters.") from exc


def _normalize_station_text_field(value: Any, *, max_length: int, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = _ensure_printable_station_ascii(text, label=label)
    if len(normalized) > max_length:
        raise ValueError(f"{label} must be {max_length} printable ASCII characters or fewer.")
    return normalized


def _normalize_station_callsign(value: Any) -> str:
    return _normalize_station_text_field(str(value or "").strip().upper(), max_length=6, label="Callsign")


def _normalize_aprs_message_text(value: str) -> str:
    if len(value) > 67:
        raise ValueError("Message text must be 67 ASCII characters or fewer.")
    for char in value:
        codepoint = ord(char)
        if codepoint < 32 or codepoint > 126:
            raise ValueError("Message text may contain only printable ASCII characters.")
    return value


def _normalize_station_interval(value: Any, *, label: str) -> int:
    try:
        interval_minutes = int(str(value or "30").strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be one of: 15, 30, 45, 60 minutes.") from exc
    if interval_minutes not in {15, 30, 45, 60}:
        raise ValueError(f"{label} must be one of: 15, 30, 45, 60 minutes.")
    return interval_minutes


def _normalize_station_beacon_interval_config(payload: dict[str, Any]) -> tuple[str, int]:
    raw_interval = str(payload.get("beacon_interval_minutes") or "").strip()
    mode = normalize_beacon_interval_mode(payload.get("beacon_interval_mode"), default=BEACON_INTERVAL_MODE_FIXED)
    if raw_interval.lower() == BEACON_INTERVAL_MODE_PROPORTIONAL:
        mode = BEACON_INTERVAL_MODE_PROPORTIONAL
    elif mode == BEACON_INTERVAL_MODE_PROPORTIONAL and "beacon_interval_minutes_fixed" in payload:
        # Defensive fallback for form submissions: if select sends numeric value,
        # treat it as fixed interval even when stale hidden mode says proportional.
        mode = BEACON_INTERVAL_MODE_FIXED

    if mode == BEACON_INTERVAL_MODE_PROPORTIONAL:
        fallback_value = payload.get("beacon_interval_minutes_fixed")
        fallback_text = str(fallback_value or "").strip()
        if not fallback_text and raw_interval.lower() != BEACON_INTERVAL_MODE_PROPORTIONAL:
            fallback_text = raw_interval
        if not fallback_text:
            fallback_text = "30"
        return mode, _normalize_station_interval(fallback_text, label="Beacon interval")

    return BEACON_INTERVAL_MODE_FIXED, _normalize_station_interval(raw_interval, label="Beacon interval")


def _normalize_serial_rx_silence_timeout_seconds(value: Any) -> int:
    raw = str(value if value is not None else SERIAL_RX_SILENCE_TIMEOUT_DEFAULT_SECONDS).strip()
    if not raw:
        return SERIAL_RX_SILENCE_TIMEOUT_DEFAULT_SECONDS
    try:
        seconds = int(raw)
    except ValueError as exc:
        raise ValueError("RX silence reconnect timeout must be one of: 0, 30, 60, 90, 120, 150, ..., 600 seconds.") from exc
    if seconds not in SERIAL_RX_SILENCE_TIMEOUT_ALLOWED_SECONDS:
        raise ValueError("RX silence reconnect timeout must be one of: 0, 30, 60, 90, 120, 150, ..., 600 seconds.")
    return seconds


def _normalize_modem_tx_min_gap_seconds(value: Any) -> float:
    raw = str(value if value is not None else MODEM_TX_MIN_GAP_SECONDS_DEFAULT).strip()
    if not raw:
        return MODEM_TX_MIN_GAP_SECONDS_DEFAULT
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise ValueError("TX minimum gap must be a number between 0.2 and 1.2 seconds.") from exc
    if seconds < MODEM_TX_MIN_GAP_SECONDS_MIN or seconds > MODEM_TX_MIN_GAP_SECONDS_MAX:
        raise ValueError("TX minimum gap must be between 0.2 and 1.2 seconds.")
    return round(seconds, 2)


def _normalize_optional_utc_date(value: Any, *, label: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD or YYYY-MM-DD HH:MM format.") from exc
    return parsed.strftime("%Y-%m-%d")


def _normalize_aprs_activation_payload(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    schedule_payload = dict(payload)
    mode = str(payload.get("activation_mode") or "manual").strip().lower()
    if mode == "manual" and "active_until_utc" in payload:
        schedule_payload["valid_until_utc"] = payload.get("active_until_utc")
    elif mode == "recurring":
        if "active_from_utc" in payload:
            schedule_payload["first_activation_utc"] = payload.get("active_from_utc")
        if "active_until_utc" in payload:
            schedule_payload["recurrence_until_utc"] = payload.get("active_until_utc")
    valid_until_label = "Active until date" if "active_until_utc" in payload else "Valid until date"
    valid_until_utc = _normalize_optional_utc_date(schedule_payload.get("valid_until_utc"), label=valid_until_label)
    return valid_until_utc, normalize_activation_schedule(schedule_payload)


def _normalize_ipv4_address(value: Any, *, default: str, label: str) -> str:
    text = str(value or "").strip() or default
    try:
        parsed = ipaddress.ip_address(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid IPv4 address.") from exc
    if parsed.version != 4:
        raise ValueError(f"{label} must be a valid IPv4 address.")
    return str(parsed)


def _normalize_tcp_port(value: Any, *, default: int, label: str) -> int:
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be between 1 and 65535.") from exc
    if port < 1 or port > 65535:
        raise ValueError(f"{label} must be between 1 and 65535.")
    return port


def _normalize_ip_whitelist(value: Any) -> str:
    entries = re.split(r"[\n,]+", str(value or ""))
    normalized_entries: list[str] = []
    seen: set[str] = set()
    for raw_entry in entries:
        entry = raw_entry.strip()
        if not entry:
            continue
        normalized_entry = _normalize_ip_whitelist_entry(entry)
        if normalized_entry in seen:
            continue
        normalized_entries.append(normalized_entry)
        seen.add(normalized_entry)
    return "\n".join(normalized_entries)


def _normalize_ip_whitelist_entry(value: str) -> str:
    try:
        if "/" in value:
            network = ipaddress.ip_network(value, strict=False)
            if network.version != 4:
                raise ValueError
            return str(network)
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("Whitelist entries must be valid IPv4 addresses or CIDR ranges.") from exc
    if address.version != 4:
        raise ValueError("Whitelist entries must be valid IPv4 addresses or CIDR ranges.")
    return str(address)


def _validate_coordinate(value: str, *, minimum: float, maximum: float, label: str) -> None:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid decimal coordinate.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{label} is out of range.")


def _decorate_aprs_entity_row(slug: str, row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    symbol_table = str(result.get("symbol_table") or "/").strip()
    if symbol_table not in {"/", "\\"}:
        symbol_table = "/"
    result["symbol_table"] = symbol_table
    result["symbol_overlay"] = _coerce_symbol_overlay_value(result.get("symbol_overlay"), symbol_table=symbol_table)
    symbol_code = str(result.get("symbol_code") or ">")
    result["symbol_icon"] = get_aprs_symbol_icon_path(f"{symbol_table}{symbol_code}")
    result["raw_frame_preview"] = _build_aprs_entity_preview(slug, result)
    _decorate_activation_schedule(result)
    return result


def _decorate_aprs_message_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["target_display"] = resolve_message_addressee(result).rstrip()
    result["type_label"] = {
        "bulletin": "Bulletin",
        "announcement": "Announcement",
        "group_bulletin": "Group Bulletin",
    }.get(str(result.get("message_kind") or ""), "Bulletin")
    result["raw_frame_preview"] = _build_aprs_message_preview(result)
    _decorate_activation_schedule(result)
    return result


def _decorate_activation_schedule(row: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    state = compute_activation_state(row, now)
    row["activation_active_now"] = state.active_now
    row["activation_reason"] = state.reason
    row["activation_summary"] = schedule_summary(row, now)
    row["activation_short_label"] = schedule_short_label(row, now)
    row["activation_warnings"] = schedule_warnings(row)
    mode = str(row.get("activation_mode") or "manual").strip().lower()
    if mode == "manual":
        row["activation_form_active_from_utc"] = None
        row["activation_form_active_until_utc"] = row.get("valid_until_utc")
    elif mode == "recurring":
        row["activation_form_active_from_utc"] = row.get("first_activation_utc")
        row["activation_form_active_until_utc"] = row.get("recurrence_until_utc")
    else:
        row["activation_form_active_from_utc"] = row.get("active_from_utc")
        row["activation_form_active_until_utc"] = row.get("active_until_utc")


def _build_aprs_entity_preview(slug: str, payload: dict[str, Any]) -> str:
    station_settings = get_station_settings()
    source = _build_preview_source(station_settings)
    latitude = _parse_coordinate(payload.get("latitude"))
    longitude = _parse_coordinate(payload.get("longitude"))
    if not source or latitude is None or longitude is None:
        return "Preview requires station callsign and valid coordinates."
    if slug == "objects":
        preview_payload = {
            "callsign": station_settings.get("callsign"),
            "ssid": station_settings.get("ssid"),
            "name": payload.get("name"),
            "lifetime": payload.get("lifetime"),
            "state": payload.get("state"),
            "latitude": latitude,
            "longitude": longitude,
            "symbol_table": payload.get("symbol_table"),
            "symbol_code": payload.get("symbol_code"),
            "symbol_overlay": payload.get("symbol_overlay"),
            "comment": payload.get("comment"),
            "path": payload.get("path"),
        }
        return build_object_tnc2(preview_payload)
    symbol_table = _resolve_symbol_table_for_frame(payload.get("symbol_table"), payload.get("symbol_overlay"))
    symbol_code = str(payload.get("symbol_code") or ">")
    comment = str(payload.get("comment") or "").strip()
    path = str(payload.get("path") or "").strip()
    header = f"{source}>APRS"
    if path:
        header = f"{header},{path}"
    name = str(payload.get("name") or "")
    state_marker = "!" if str(payload.get("state") or "live") == "live" else "_"
    info = (
        f"){name}{state_marker}"
        f"{_format_aprs_latitude(latitude)}{symbol_table}{_format_aprs_longitude(longitude)}{symbol_code}{comment}"
    )
    return f"{header}:{info}"


def _build_aprs_message_preview(payload: dict[str, Any]) -> str:
    station_settings = get_station_settings()
    source = _build_preview_source(station_settings)
    if not source:
        return "Preview requires station callsign."
    preview_payload = {
        "callsign": station_settings.get("callsign"),
        "ssid": station_settings.get("ssid"),
        "message_kind": payload.get("message_kind"),
        "bulletin_code": payload.get("bulletin_code"),
        "group_name": payload.get("group_name"),
        "path": payload.get("path"),
        "message_text": payload.get("message_text"),
    }
    return build_message_tnc2(preview_payload)


def _build_preview_source(station_settings: dict[str, Any]) -> str:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    if not callsign:
        return ""
    ssid = str(station_settings.get("ssid") or "").strip()
    if ssid == "0":
        ssid = ""
    return f"{callsign}-{ssid}" if ssid else callsign


def _format_aprs_latitude(value: float) -> str:
    hemisphere = "N" if value >= 0 else "S"
    absolute = abs(value)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60
    return f"{degrees:02d}{minutes:05.2f}{hemisphere}"


def _format_aprs_longitude(value: float) -> str:
    hemisphere = "E" if value >= 0 else "W"
    absolute = abs(value)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60
    return f"{degrees:03d}{minutes:05.2f}{hemisphere}"


def _resolve_symbol_table_for_frame(symbol_table: Any, symbol_overlay: Any) -> str:
    normalized_table = str(symbol_table or "/").strip()
    if normalized_table not in {"/", "\\"}:
        normalized_table = "/"
    normalized_overlay = _coerce_symbol_overlay_value(symbol_overlay, symbol_table=normalized_table)
    return normalized_overlay or normalized_table
