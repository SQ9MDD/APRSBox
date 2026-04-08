from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import math
import re
import sqlite3
import subprocess
from shutil import which
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.i18n import get_app_language, get_translator
from app.services.aprs_device_identification import (
    get_aprs_device_identification_database,
    lookup_aprs_device_identification,
)
from app.services.messages import get_messages_page_data
from app.services.outbound import build_beacon_tnc2, build_message_tnc2, build_object_tnc2, build_status_tnc2, resolve_message_addressee
from app.services.serial_tnc import normalize_serial_baud_rate, normalize_serial_device_path
from app.sections import SECTION_DEFINITIONS


WORKER_DEFINITIONS = (
    {
        "label": "aprs-core",
        "service_names": ("aprsbox-core", "aprs-core"),
        "process_patterns": ("aprsbox-core", "aprs-core", "aprsbox-core-placeholder.sh"),
    },
    {
        "label": "aprs-web",
        "service_names": ("aprsbox-web", "aprs-web"),
        "process_patterns": ("aprsbox-web", "aprs-web", "app.main:app"),
    },
)

STATION_SNAPSHOT_ROW_LIMIT_FACTOR = 40
STATION_SNAPSHOT_ROW_LIMIT_MIN = 4000
_STATION_SNAPSHOT_CACHE: dict[tuple[int, int | None, str, str], list[dict[str, Any]]] = {}


def _t(message: object) -> str:
    return get_translator(get_app_language())(message)


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
    runtime_rows = fetch_all(
        """
        SELECT modem_id, status, status_detail, last_error
        FROM traffic_runtime_interfaces
        """
    )
    runtime_by_modem_id = {int(row["modem_id"]): dict(row) for row in runtime_rows if row["modem_id"] is not None}
    return [_decorate_modem_row(row, runtime_by_modem_id.get(int(row["id"]))) for row in rows]


def _decorate_modem_row(row: dict[str, Any], runtime_row: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(row)
    if not bool(result.get("enabled")):
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
        result["modem_runtime_title"] = runtime_error or runtime_detail or "TNC connection error."
        return result
    if runtime_status == "connecting":
        result["modem_runtime_status"] = "connecting"
        result["modem_runtime_label"] = "Connecting"
        result["modem_runtime_icon"] = "progress-clock.svg"
        result["modem_runtime_title"] = runtime_detail or "Connecting to TNC."
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
    values: dict[str, Any] = {}
    for field in definition.fields:
        name = field["name"]
        if field["type"] == "checkbox":
            values[name] = int(bool(normalized_payload.get(name)))
        else:
            values[name] = normalized_payload.get(name)
    if slug == "modems" and values.get("modem_type") == "TCP":
        values["baud_rate"] = None
    if slug in {"modems", "servers"}:
        values.setdefault("notes", "")
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
    values: dict[str, Any] = {}
    for field in definition.fields:
        name = field["name"]
        if field["type"] == "checkbox":
            values[name] = int(bool(normalized_payload.get(name)))
        else:
            values[name] = normalized_payload.get(name)
    if slug == "modems" and values.get("modem_type") == "TCP":
        values["baud_rate"] = None
    if slug in {"modems", "servers"}:
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
    log_event("INFO", "config", f"Updated record {row_id} in {definition.table_name}")


def delete_section_row(slug: str, row_id: int) -> None:
    definition = SECTION_DEFINITIONS[slug]
    with get_connection() as connection:
        connection.execute(f"DELETE FROM {definition.table_name} WHERE id = ?", (row_id,))
    log_event("INFO", "config", f"Deleted record {row_id} from {definition.table_name}")


def get_station_settings() -> dict[str, Any]:
    row = fetch_one("SELECT * FROM station_settings WHERE id = 1")
    if not row:
        return {}
    result = dict(row)
    result.setdefault("beacon_interface_id", None)
    result.setdefault("default_units", "metric")
    result.setdefault("beacon_interval_minutes", 30)
    result.setdefault("beacon_path", "")
    result.setdefault("status_enabled", 0)
    result.setdefault("status_text", "")
    result.setdefault("status_interval_minutes", 30)
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


def has_enabled_modem_interface() -> bool:
    row = fetch_one(
        """
        SELECT 1
        FROM modems
        WHERE enabled = 1 AND modem_type IN ('TCP', 'SERIALL')
        LIMIT 1
        """
    )
    return row is not None


def update_station_settings(payload: dict[str, Any]) -> None:
    values = normalize_station_settings_payload(payload)
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE station_settings
            SET callsign = :callsign,
                ssid = :ssid,
                beacon_interface_id = :beacon_interface_id,
                beacon_comment = :beacon_comment,
                beacon_interval_minutes = :beacon_interval_minutes,
                beacon_path = :beacon_path,
                status_enabled = :status_enabled,
                status_text = :status_text,
                status_interval_minutes = :status_interval_minutes,
                latitude = :latitude,
                longitude = :longitude,
                symbol_table = :symbol_table,
                symbol_code = :symbol_code,
                default_units = :default_units,
                tx_enabled = :tx_enabled,
                updated_at = :updated_at
            WHERE id = 1
            """,
            values,
        )
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
    try:
        beacon_interface_id = int(payload.get("beacon_interface_id")) if payload.get("beacon_interface_id") not in {None, ""} else None
    except (TypeError, ValueError):
        beacon_interface_id = None
    if beacon_interface_id is not None:
        interface_exists = fetch_one("SELECT id FROM modems WHERE id = ?", (beacon_interface_id,))
        if interface_exists is None:
            beacon_interface_id = None
    beacon_interval_minutes = _normalize_station_interval(payload.get("beacon_interval_minutes"), label="Beacon interval")
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
    return {
        "callsign": payload.get("callsign", ""),
        "ssid": payload.get("ssid", ""),
        "beacon_interface_id": beacon_interface_id,
        "beacon_comment": beacon_comment,
        "beacon_interval_minutes": beacon_interval_minutes,
        "beacon_path": payload.get("beacon_path", ""),
        "status_enabled": status_enabled,
        "status_text": status_text,
        "status_interval_minutes": status_interval_minutes,
        "latitude": payload.get("latitude", ""),
        "longitude": payload.get("longitude", ""),
        "symbol_table": symbol_table,
        "symbol_code": symbol_code,
        "default_units": default_units,
        "tx_enabled": int(bool(payload.get("tx_enabled"))),
        "updated_at": utc_now(),
    }


def recent_event_logs(limit: int = 100) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, level, category, message, created_at FROM event_logs ORDER BY id DESC LIMIT ?",
        (limit,),
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
        item["interface_name"] = item.get("interface_name") or "Unknown interface"
        skip_reason = str(item.get("last_error") or "").strip()
        item["is_tx_skipped"] = bool(skip_reason) and skip_reason.startswith("TX skipped:")
        item["display_time"] = item.get("sent_at") or item.get("started_at") or item.get("scheduled_at") or ""
        jobs.append(item)
    return jobs


def recent_beacon_jobs(limit: int = 20) -> list[dict[str, Any]]:
    return recent_station_outbound_jobs(limit=limit)


def traffic_snapshot(limit: int = 400) -> dict[str, Any]:
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
        SELECT source, interface_id, direction, band, format, line, port, command, length, hex, created_at
        FROM traffic_frames
        ORDER BY created_at DESC, id DESC
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
                "device_path": row["modem_endpoint"] or "",
                "band": row["band"] or "",
                "status": row["status"] or "idle",
                "status_detail": row["status_detail"] or "",
                "last_error": row["last_error"],
                "updated_at": _format_monitor_timestamp(row["updated_at"]),
                "expose": expose,
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
    if interfaces and len(interfaces) > 1:
        connected = [item for item in interfaces if item["status"] == "connected"]
        connecting = [item for item in interfaces if item["status"] == "connecting"]
        if connected:
            status = "connected"
            status_detail = f"{len(connected)}/{len(interfaces)} TNC interfaces connected."
        elif connecting:
            status = "connecting"
            status_detail = f"Connecting {len(connecting)} TNC interface(s)."
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
    for row in frame_rows:
        direction = str(row["direction"] or "").upper() or ("TX" if str(row["format"] or "").endswith("-TX") else "RX")
        row_class = _traffic_frame_row_class(
            direction=direction,
            line=str(row["line"] or ""),
            command=str(row["command"] or ""),
            station_source_key=station_source_key,
            wx_source_key=wx_source_key,
        )
        frames.append(
            {
                "timestamp": _format_monitor_timestamp(row["created_at"]),
                "source": row["source"],
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
            }
        )
    return {
        "status": status,
        "status_detail": status_detail,
        "active_modem": active_modem,
        "expose": expose,
        "interfaces": interfaces,
        "last_error": last_error,
        "updated_at": updated_at,
        "frames": frames,
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
) -> str:
    classes: list[str] = []
    normalized_direction = str(direction or "").strip().upper()
    normalized_command = str(command or "").strip().upper()
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
    packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
    packet_type_code = str(aprs_data.get("packet_type_code") or "").strip().lower()
    symbol = str(aprs_data.get("symbol") or "").strip()
    is_weather = packet_group == "weather" or symbol.endswith("_")
    is_beacon_or_status = packet_group in {"position", "status"} and not is_weather
    is_message_or_bulletin = packet_group == "message" and packet_type_code in {
        "message",
        "bulletin",
        "announcement",
        "group_bulletin",
    }
    is_own_station_source = bool(station_source_key) and source_key == station_source_key
    is_own_wx_source = bool(wx_source_key) and source_key == wx_source_key
    is_own_callsign = bool(station_callsign) and source_callsign == station_callsign

    if normalized_direction == "TX":
        if is_proxy_tx and source_key and source_key not in {station_source_key, wx_source_key}:
            classes.append("traffic-log-row-proxy-tx")
        elif (is_own_wx_source or is_own_callsign) and is_weather:
            classes.append("traffic-log-row-own-wx-tx")
        elif is_own_station_source and is_beacon_or_status:
            classes.append("traffic-log-row-own-beacon-tx")
        elif is_own_station_source and is_message_or_bulletin:
            classes.append("traffic-log-row-own-message-tx")
        elif source_key and source_key not in {station_source_key, wx_source_key}:
            classes.append("traffic-log-row-repeated-tx")
    elif normalized_direction == "RX":
        if (is_own_wx_source or is_own_callsign) and is_weather:
            classes.append("traffic-log-row-own-wx-rx")
        elif is_own_station_source and is_beacon_or_status:
            classes.append("traffic-log-row-own-beacon-rx")
        elif is_own_station_source and is_message_or_bulletin:
            classes.append("traffic-log-row-own-message-rx")

    return " ".join(classes)


def _format_monitor_timestamp(timestamp: str | None) -> str:
    if not timestamp:
        return "-"
    try:
        local_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return timestamp
    return local_time.strftime("%Y.%m.%d %H:%M:%S")


def dashboard_summary() -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for slug, definition in SECTION_DEFINITIONS.items():
        row = fetch_one(f"SELECT COUNT(*) AS total FROM {definition.table_name}")
        metrics[slug] = row["total"] if row else 0
    metrics["users"] = fetch_one("SELECT COUNT(*) AS total FROM users")["total"]
    metrics["logs"] = fetch_one("SELECT COUNT(*) AS total FROM event_logs")["total"]
    return metrics


def dashboard_traffic_summary() -> dict[str, Any]:
    total_frames_row = fetch_one("SELECT COUNT(*) AS total FROM traffic_frames")
    decoded_frames_row = fetch_one("SELECT COUNT(*) AS total FROM traffic_frames WHERE format = 'TNC2'")
    unique_sources_row = fetch_one(
        """
        SELECT COUNT(DISTINCT source) AS total
        FROM traffic_frames
        WHERE COALESCE(source, '') <> ''
        """
    )

    return {
        "received_frames": total_frames_row["total"] if total_frames_row else 0,
        "decoded_aprs": decoded_frames_row["total"] if decoded_frames_row else 0,
        "unique_sources": unique_sources_row["total"] if unique_sources_row else 0,
        "heard_stations": len(get_heard_station_snapshots()),
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


def dashboard_home_data(dashboard_band: dict[str, Any] | None = None) -> dict[str, Any]:
    station_settings = get_station_settings()
    traffic = dashboard_traffic_summary()
    interfaces = get_configured_modem_interfaces()
    enabled_interfaces = [item for item in interfaces if item.get("enabled")]
    selected_interface_id_raw = station_settings.get("beacon_interface_id")
    try:
        selected_interface_id = int(selected_interface_id_raw) if selected_interface_id_raw not in {None, ""} else None
    except (TypeError, ValueError):
        selected_interface_id = None
    selected_interface = next((item for item in interfaces if item.get("id") == selected_interface_id), None)
    selected_interface_row = (
        fetch_one(
            """
            SELECT id, name, enabled, tx_blocked
            FROM modems
            WHERE id = ?
            """,
            (selected_interface_id,),
        )
        if selected_interface_id is not None
        else None
    )
    selected_interface_enabled = bool(int(selected_interface_row["enabled"])) if selected_interface_row else False
    selected_interface_tx_blocked = bool(int(selected_interface_row["tx_blocked"])) if selected_interface_row else False

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
    selected_runtime = runtime_by_modem_id.get(selected_interface_id) if selected_interface_id is not None else None
    runtime_state_row = fetch_one(
        """
        SELECT status, status_detail, last_error
        FROM traffic_runtime_state
        WHERE id = 1
        """
    )

    monitor_status = str((selected_runtime or {}).get("status") or "").strip().lower()
    monitor_detail = str((selected_runtime or {}).get("status_detail") or "").strip()
    monitor_error = str((selected_runtime or {}).get("last_error") or "").strip()
    if not monitor_status and runtime_state_row:
        monitor_status = str(runtime_state_row["status"] or "").strip().lower()
        monitor_detail = str(runtime_state_row["status_detail"] or "").strip()
        monitor_error = str(runtime_state_row["last_error"] or "").strip()

    if not enabled_interfaces:
        monitor_check_state = "warn"
        monitor_check_value = "Disabled"
    elif monitor_error or monitor_status == "error":
        monitor_check_state = "error"
        monitor_check_value = "Error"
    elif monitor_status in {"connected", "running", "idle"}:
        monitor_check_state = "ok"
        monitor_check_value = "Enabled"
    elif monitor_status == "connecting":
        monitor_check_state = "warn"
        monitor_check_value = "Enabled"
    elif monitor_status in {"disabled", "stopped"}:
        monitor_check_state = "warn"
        monitor_check_value = "Disabled"
    elif monitor_status:
        monitor_check_state = "warn"
        monitor_check_value = "Unknown"
    else:
        monitor_check_state = "warn"
        monitor_check_value = "Unknown"

    recent_tx_jobs = recent_station_outbound_jobs(limit=1)
    latest_station_tx_display = "Never"
    latest_station_tx_state = "warn"
    latest_station_tx_value = "Never"
    latest_station_tx_note = ""
    if recent_tx_jobs:
        latest_tx = recent_tx_jobs[0]
        latest_tx_time = _format_monitor_timestamp(str(latest_tx.get("display_time") or ""))
        if latest_tx_time and latest_tx_time != "-":
            latest_station_tx_display = latest_tx_time
        tx_status = str(latest_tx.get("status") or "").strip().lower()
        if latest_tx.get("is_tx_skipped"):
            latest_station_tx_state = "warn"
            latest_station_tx_value = "Skipped"
            latest_station_tx_note = str(latest_tx.get("last_error") or "").strip()
        elif tx_status == "failed":
            latest_station_tx_state = "error"
            latest_station_tx_value = "Failed"
            latest_station_tx_note = str(latest_tx.get("last_error") or "").strip() or latest_station_tx_display
        elif tx_status in {"queued", "processing"}:
            latest_station_tx_state = "warn"
            latest_station_tx_value = "Queued"
            latest_station_tx_note = latest_station_tx_display
        else:
            latest_station_tx_state = "ok"
            latest_station_tx_value = "Sent"
            latest_station_tx_note = latest_station_tx_display

    latest_frame_row = fetch_one(
        """
        SELECT created_at
        FROM traffic_frames
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    )
    latest_activity = _format_monitor_timestamp(latest_frame_row["created_at"]) if latest_frame_row else "No traffic yet"
    callsign = str(station_settings.get("callsign") or "").strip()
    location_configured = bool(station_settings.get("latitude")) and bool(station_settings.get("longitude"))
    selected_interface_name = (
        str(selected_interface_row["name"]).strip()
        if selected_interface_row and str(selected_interface_row["name"] or "").strip()
        else (selected_interface["name"] if selected_interface else "Not selected")
    )

    checks = [
        {
            "label": "Callsign",
            "state": "ok" if callsign else "warn",
            "value": callsign or "Not set",
            "blocks": not callsign,
        },
        {
            "label": "Location",
            "state": "ok" if location_configured else "warn",
            "value": "Configured" if location_configured else "Missing coordinates",
            "blocks": not location_configured,
        },
        {
            "label": "Beacon interface",
            "state": "warn" if not selected_interface_row else ("error" if not selected_interface_enabled else "ok"),
            "value": selected_interface_name,
            "note": "Disabled" if selected_interface_row and not selected_interface_enabled else "",
            "blocks": not selected_interface_row or (selected_interface_row is not None and not selected_interface_enabled),
        },
        {
            "label": "Active interfaces",
            "state": "ok" if enabled_interfaces else "warn",
            "value": str(len(enabled_interfaces)),
            "blocks": not enabled_interfaces,
        },
        {
            "label": "Traffic Monitor",
            "state": monitor_check_state,
            "value": monitor_check_value,
            "note": monitor_error or monitor_detail,
            "blocks": monitor_check_state == "error",
        },
        {
            "label": "TX Block",
            "state": "warn" if not selected_interface_row else ("warn" if selected_interface_tx_blocked else "ok"),
            "value": "Not selected" if not selected_interface_row else ("On" if selected_interface_tx_blocked else "Off"),
            "blocks": bool(selected_interface_row) and selected_interface_tx_blocked,
        },
        {
            "label": "TX Enabled",
            "state": "ok" if bool(station_settings.get("tx_enabled")) else "warn",
            "value": "On" if bool(station_settings.get("tx_enabled")) else "Off",
            "blocks": False,
        },
        {
            "label": "APRS Status enabled",
            "state": "ok" if bool(station_settings.get("status_enabled")) else "warn",
            "value": "On" if bool(station_settings.get("status_enabled")) else "Off",
            "blocks": False,
        },
        {
            "label": "Last station TX",
            "state": latest_station_tx_state,
            "value": latest_station_tx_value,
            "note": latest_station_tx_note,
            "blocks": False,
        },
    ]
    next_steps = [item for item in checks if item["blocks"] and item["state"] != "ok"]
    beacon_ready = len(next_steps) == 0

    if traffic["heard_stations"] > 0 and traffic["decoded_aprs"] > 0:
        hero = {
            "kind": "receiving",
            "tone": "good",
            "title": "Station is receiving APRS traffic",
            "status": "Receiving",
            "heard_stations": traffic["heard_stations"],
            "decoded_aprs": traffic["decoded_aprs"],
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

    if dashboard_band and dashboard_band.get("label") == "Insufficient data":
        band_summary = "Band condition will become more useful after more traffic is collected."
    elif dashboard_band:
        band_summary = dashboard_band.get("diagnosis_summary") or ""
    else:
        band_summary = "Band condition is not available yet."

    return {
        "hero": hero,
        "stats": [
            {"label": "Heard stations", "value": str(traffic["heard_stations"]), "suffix": "in last h"},
            {"label": "APRS frames", "value": str(traffic["decoded_aprs"]), "suffix": "/ h"},
            {"label": "Active interfaces", "value": str(len(enabled_interfaces)), "suffix": ""},
            {"label": "Last station TX", "value": latest_station_tx_display, "suffix": ""},
        ],
        "checks": checks,
        "next_steps": next_steps,
        "beacon_ready": beacon_ready,
        "station_callsign": callsign or "Not set",
        "selected_interface_name": selected_interface_name,
        "latest_activity": latest_activity,
        "band_summary": band_summary,
    }


def visible_stations(limit: int = 500, unit_system: str = "metric") -> list[dict[str, Any]]:
    snapshots = get_visible_station_snapshots(limit=limit)
    stations: list[dict[str, Any]] = []
    for snapshot in snapshots:
        stations.append(
            {
                "callsign": snapshot["callsign"],
                "display_callsign": snapshot["display_callsign"],
                "origin": snapshot.get("origin", "heard"),
                "activity_label": snapshot.get("activity_label", _t("Last heard")),
                "activity_age_label": snapshot.get("activity_age_label", _t("Last heard age")),
                "last_heard_at": snapshot["last_heard_at"],
                "last_heard_label": snapshot["last_heard_label"],
                "last_heard_date": snapshot["last_heard_date"],
                "last_heard_relative": snapshot["last_heard_relative"],
                "entity_class": snapshot["entity_class"],
                "frame_type": snapshot["frame_type"],
                "frame_type_label": snapshot["frame_type_label"],
                "symbol": snapshot["symbol"],
                "symbol_icon": snapshot["symbol_icon"],
                "comment": snapshot["comment"],
                "data": _format_decoded_data_for_display(snapshot["data_raw"], unit_system),
                "latitude": snapshot["latitude"],
                "longitude": snapshot["longitude"],
                "distance_km": snapshot.get("distance_km"),
                "aprs_device_short": snapshot["aprs_device_short"],
                "detail_href": build_station_detail_href(snapshot["display_callsign"]),
            }
        )
    return stations


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
    return {
        "callsign": snapshot["callsign"],
        "ssid": snapshot["ssid"],
        "display_callsign": snapshot["display_callsign"],
        "detail_href": build_station_detail_href(snapshot["display_callsign"]),
        "base_callsign": snapshot["callsign"],
        "origin": snapshot.get("origin", "heard"),
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
        "distance_km": snapshot.get("distance_km"),
        "messaging_capable": _messaging_capable(snapshot),
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
        parsed = _parse_tnc2_line(row["line"])
        if parsed is None:
            continue
        aprs_data = _parse_aprs_packet(parsed)
        if aprs_data is None:
            continue
        if not _aprs_data_has_station_snapshot_fields(aprs_data):
            continue
        row_station_key = (aprs_data.get("entity_name") or parsed["source"]).strip()
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
                "source": parsed["source"],
                "destination": parsed["destination"],
                "path": parsed["path"],
                "decoded_summary": decoded_summary,
                "raw_packet": row["line"],
            }
        )
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
    rows = _station_snapshot_rows(("TNC2",), row_limit=_station_snapshot_row_limit(limit))
    return _build_station_snapshots_from_rows(rows, origin="heard", limit=limit)


def get_local_tx_station_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    rows = _station_snapshot_rows(("TNC2-TX",), row_limit=_station_snapshot_row_limit(limit))
    return _build_station_snapshots_from_rows(rows, origin="local_tx", limit=limit)


def get_visible_station_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    normalized_limit = max(1, int(limit or 0))
    station_settings = get_station_settings()
    cache_key = (
        normalized_limit,
        _latest_station_snapshot_frame_id(),
        str(station_settings.get("latitude") or ""),
        str(station_settings.get("longitude") or ""),
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


def _station_snapshot_rows(formats: tuple[str, ...], *, row_limit: int) -> list[dict[str, Any]]:
    placeholders = ", ".join("?" for _ in formats)
    rows = fetch_all(
        f"""
        SELECT source, line, created_at
        FROM traffic_frames
        WHERE format IN ({placeholders})
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        formats + (row_limit,),
    )
    return [dict(row) for row in rows]


def _build_station_snapshots_from_rows(
    rows: list[dict[str, Any]],
    *,
    origin: str,
    limit: int,
) -> list[dict[str, Any]]:
    stations: dict[str, dict[str, Any]] = {}
    device_database = get_aprs_device_identification_database()

    for row in rows:
        parsed = _parse_tnc2_line(row["line"])
        if parsed is None:
            continue

        callsign = parsed["source"].strip()
        aprs_data = _parse_aprs_packet(parsed)
        if aprs_data is None:
            continue
        if not _aprs_data_has_station_snapshot_fields(aprs_data):
            continue

        station_key = (aprs_data.get("entity_name") or callsign).strip()
        if not station_key:
            continue

        if station_key not in stations:
            stations[station_key] = _new_station_snapshot(
                station_key,
                row["created_at"],
                row["source"],
                parsed["destination"],
                parsed["path"],
                row["line"],
                origin=origin,
            )

        station = stations[station_key]
        if not station["aprs_device"] and station_key.casefold() == callsign.casefold():
            device_identification = lookup_aprs_device_identification(
                destination=parsed["destination"],
                info=parsed["info"],
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
            station["symbol_icon"] = _aprs_symbol_icon_path(aprs_data["symbol"])
            symbol_table, symbol_code = _split_symbol(aprs_data["symbol"])
            station["symbol_table"] = symbol_table
            station["symbol_code"] = symbol_code
        if not station["comment"] and aprs_data.get("comment"):
            station["comment"] = aprs_data["comment"]
        if not station["data_raw"] and aprs_data.get("data"):
            station["data_raw"] = dict(aprs_data["data"])
        if not station["latitude"] and aprs_data.get("latitude"):
            station["latitude"] = aprs_data["latitude"]
        if not station["longitude"] and aprs_data.get("longitude"):
            station["longitude"] = aprs_data["longitude"]

    return list(stations.values())[:limit]


def _merge_station_snapshots(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
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
    ):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    if (not merged.get("data_raw")) and secondary.get("data_raw"):
        merged["data_raw"] = dict(secondary["data_raw"])
    if latest is secondary:
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
        ):
            merged[field] = secondary.get(field)
    return merged


def _new_station_snapshot(
    name: str,
    created_at: str,
    source: str,
    destination: str,
    path: str,
    raw_text: str,
    *,
    origin: str,
) -> dict[str, Any]:
    heard_date, heard_relative = _format_last_heard_parts(created_at)
    base_callsign, ssid = _split_ssid(name)
    activity_label, activity_age_label = _station_snapshot_activity_labels(origin)
    return {
        "callsign": base_callsign,
        "ssid": ssid,
        "display_callsign": name,
        "origin": origin,
        "activity_label": activity_label,
        "activity_age_label": activity_age_label,
        "last_heard_at": created_at,
        "last_heard_age_s": _last_heard_age_seconds(created_at),
        "last_heard_label": _format_last_heard(created_at),
        "last_heard_date": heard_date,
        "last_heard_relative": heard_relative,
        "source": source,
        "destination": destination,
        "path": path,
        "raw_text": raw_text,
        "entity_class": "",
        "frame_type": "",
        "frame_type_label": "",
        "symbol": "",
        "symbol_table": "",
        "symbol_code": "",
        "symbol_icon": "icons/verG/x.gif",
        "comment": "",
        "data_raw": {},
        "latitude": "",
        "longitude": "",
        "distance_km": None,
        "aprs_device": None,
        "aprs_device_short": "",
    }


def _station_snapshot_activity_labels(origin: str) -> tuple[str, str]:
    if origin == "local_tx":
        return _t("Last local TX"), _t("Last local TX age")
    return _t("Last heard"), _t("Last heard age")


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
    match = _TNC2_RE.match(line.strip())
    if not match:
        return None
    parsed = match.groupdict(default="")
    return {key: value.strip() for key, value in parsed.items()}


def parse_tnc2_frame(line: str) -> dict[str, Any] | None:
    parsed = _parse_tnc2_line(line)
    if parsed is None:
        return None

    aprs_data = _parse_aprs_packet(parsed)
    source_key = parsed["source"].strip()
    source_callsign, source_ssid = _split_ssid(source_key)
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
        "entity_name": str(entity_name or "").strip(),
        "entity_class": entity_class,
        "classification": classification,
        "aprs_data": aprs_data,
    }


def _format_last_heard(timestamp: str) -> str:
    try:
        heard_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp

    local_time = heard_at.astimezone()
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
    return f"{local_time.strftime('%Y.%m.%d %H:%M')} ({relative})"


def _format_last_heard_parts(timestamp: str) -> tuple[str, str]:
    try:
        heard_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp, ""

    local_time = heard_at.astimezone()
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
    return local_time.strftime("%Y.%m.%d %H:%M"), relative


def _last_heard_age_seconds(timestamp: str) -> int | None:
    try:
        heard_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - heard_at).total_seconds()))


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


def _station_detail_fields(snapshot: dict[str, Any], unit_system: str) -> list[dict[str, str]]:
    metrics = dict(snapshot.get("data_raw", {}) or {})
    fields: list[dict[str, str]] = []
    display_callsign = snapshot.get("display_callsign")
    if display_callsign:
        fields.append({"label": "Display callsign", "value": str(display_callsign)})
    if snapshot.get("callsign"):
        fields.append({"label": "Base callsign", "value": str(snapshot["callsign"])})
    if snapshot.get("ssid"):
        fields.append({"label": "SSID", "value": str(snapshot["ssid"])})
    if snapshot.get("source"):
        fields.append({"label": "Source", "value": str(snapshot["source"])})
    if snapshot.get("destination"):
        fields.append({"label": "Destination", "value": str(snapshot["destination"])})
    if snapshot.get("last_heard_date"):
        fields.append({"label": str(snapshot.get("activity_label") or _t("Last heard")), "value": str(snapshot["last_heard_date"])})
    if snapshot.get("last_heard_relative"):
        fields.append({"label": str(snapshot.get("activity_age_label") or _t("Last heard age")), "value": str(snapshot["last_heard_relative"])})
    if snapshot.get("latitude"):
        fields.append({"label": "Latitude", "value": str(snapshot["latitude"])})
    if snapshot.get("longitude"):
        fields.append({"label": "Longitude", "value": str(snapshot["longitude"])})
    if snapshot.get("symbol_table"):
        fields.append({"label": "Symbol table", "value": str(snapshot["symbol_table"])})
    if snapshot.get("symbol_code"):
        fields.append({"label": "Symbol code", "value": str(snapshot["symbol_code"])})
    if snapshot.get("comment"):
        fields.append({"label": "Comment", "value": str(snapshot["comment"])})
    if snapshot.get("path"):
        fields.append({"label": "Path", "value": str(snapshot["path"])})
    if snapshot.get("frame_type"):
        fields.append({"label": "Packet type", "value": str(snapshot["frame_type"])})

    speed_knots = metrics.get("speed_knots")
    if speed_knots is not None:
        speed_value = f"{int(round(float(speed_knots) * 1.15078))} mph" if unit_system == "imperial" else f"{int(round(float(speed_knots) * 1.852))} km/h"
        fields.append({"label": "Speed", "value": speed_value})
    course_deg = metrics.get("course_deg")
    if course_deg is not None:
        fields.append({"label": "Course", "value": f"{int(course_deg)}°"})
    altitude_ft = metrics.get("altitude_ft")
    if altitude_ft is not None:
        altitude_value = f"{int(altitude_ft)} ft" if unit_system == "imperial" else f"{int(round(float(altitude_ft) * 0.3048))} m"
        fields.append({"label": "Altitude", "value": altitude_value})

    messaging_capable = _messaging_capable(snapshot)
    if messaging_capable is not None:
        fields.append({"label": "Messaging capability", "value": "Yes" if messaging_capable else "No"})
    if snapshot.get("raw_text"):
        fields.append({"label": "Latest raw packet", "value": str(snapshot["raw_text"])})

    for item in _format_decoded_data_for_display(metrics, unit_system):
        if item.get("value"):
            fields.append({"label": item["label"], "value": item["value"]})
    return fields


def station_summary(stations: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": 0, "stationary": 0, "mobile": 0, "objects": 0}
    for station in stations:
        summary["total"] += 1
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
        return _parse_third_party_packet(info)
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
    else:
        if len(info) < 14:
            return False
        symbol_table = info[1]
        lat_block = info[2:6]
        lon_block = info[6:10]
        symbol_code = info[10]

    if symbol_table not in {"/", "\\"}:
        return False
    if not _is_base91_block(lat_block) or not _is_base91_block(lon_block):
        return False
    return 33 <= ord(symbol_code) <= 126


def _parse_compressed_position(info: str, *, with_timestamp: bool) -> dict[str, Any] | None:
    if with_timestamp:
        symbol_table = info[8]
        lat_block = info[9:13]
        lon_block = info[13:17]
        symbol_code = info[17]
        comment = info[21:].strip() if len(info) > 21 else ""
    else:
        symbol_table = info[1]
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

    latitude = _decode_mic_e_latitude(destination)
    longitude = _decode_mic_e_longitude(destination, info)
    if latitude is None or longitude is None:
        return None

    symbol_code = info[7] if len(info) > 7 else ""
    symbol_table = info[8] if len(info) > 8 else "/"
    comment = info[9:].strip() if len(info) > 9 else ""
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
        "comment": comment,
    }
    mic_e_movement = _decode_mic_e_speed_course(info)
    if mic_e_movement:
        result["data"] = mic_e_movement
    _attach_comment_extensions(result)
    return result


def _decode_mic_e_latitude(destination: str) -> str | None:
    digits: list[int] = []
    for char in destination:
        digit = _decode_mic_e_dest_digit(char)
        if digit is None:
            return None
        digits.append(digit)

    latitude = (digits[0] * 10 + digits[1]) + ((digits[2] * 10 + digits[3]) + (digits[4] * 10 + digits[5]) / 100.0) / 60.0
    if not _mic_e_flag(destination[3]):
        latitude *= -1
    return f"{latitude:.5f}"


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
        if hundredths >= 60:
            hundredths -= 60
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


def _decode_mic_e_dest_digit(char: str) -> int | None:
    if "0" <= char <= "9":
        return ord(char) - ord("0")
    if "A" <= char <= "J":
        return ord(char) - ord("A")
    if "P" <= char <= "Y":
        return ord(char) - ord("P")
    return None


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


def _parse_third_party_packet(info: str) -> dict[str, Any] | None:
    encapsulated = info[1:].strip()
    parsed = _parse_tnc2_line(encapsulated)
    if parsed is None:
        return {
            "packet_type_code": "third_party",
            "comment": encapsulated,
        }
    embedded = _parse_aprs_packet(parsed)
    if embedded is None:
        return {
            "packet_type_code": "third_party",
            "comment": encapsulated,
        }
    result = dict(embedded)
    result["wrapped_packet_type_code"] = str(embedded.get("packet_type_code") or "")
    result["packet_type_code"] = "third_party"
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

    return metrics or None


def _attach_comment_extensions(result: dict[str, Any]) -> None:
    comment = result.get("comment", "") or ""
    data: dict[str, Any] = dict(result.get("data", {}) or {})
    preserve_qsy_callsign_in_comment = False
    if result.get("symbol", "").endswith("_"):
        weather = _parse_weather_fields(comment)
        if weather:
            data.update(weather)

    phg = _parse_phg_fields(comment)
    if phg:
        data.update(phg)

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
    cleaned = re.sub(r"(?:c\d{3}|s\d{3}|g\d{3}|t-?\d{3}|r\d{3}|p\d{3}|P\d{3}|h\d{2}|b\d{5})", " ", cleaned)
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
        sign = "+" if int(qsy_offset_khz) > 0 else ""
        items.append(_weather_item("signal-distance-variant.svg", "Offset", f"{sign}{int(qsy_offset_khz)} kHz"))

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


def _base91_value(value: str) -> int:
    total = 0
    for char in value:
        code = ord(char)
        if code < 33 or code > 123:
            raise ValueError("Out of base91 range")
        total = total * 91 + (code - 33)
    return total


def _aprs_symbol_icon_path(symbol: str) -> str:
    if len(symbol) != 2:
        return "icons/verG/x.gif"

    table, code = symbol[0], symbol[1]
    index = ord(code) - 33
    if index < 0 or index > 93:
        return "icons/verG/x.gif"

    filename = f"{index:02d}.gif" if table == "/" else f"a{index:02d}.gif"
    candidate = settings.static_dir / "icons" / "verG" / filename
    if candidate.exists():
        return f"icons/verG/{filename}"
    return "icons/verG/x.gif"


def get_aprs_symbol_icon_path(symbol: str) -> str:
    return _aprs_symbol_icon_path(symbol)


def _status_from_openrc(service_name: str) -> dict[str, str] | None:
    if which("rc-service") is None:
        return None
    try:
        result = subprocess.run(
            ["rc-service", service_name, "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = " ".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()).lower()
    if "does not exist" in output or "not found" in output:
        return None
    if result.returncode == 0 or "started" in output:
        return {"state": "running", "detail": "OpenRC service is running", "source": f"OpenRC ({service_name})"}
    if "stopped" in output or "inactive" in output:
        return {"state": "stopped", "detail": "OpenRC service is stopped", "source": f"OpenRC ({service_name})"}
    if "crashed" in output or "failed" in output:
        return {"state": "stopped", "detail": "OpenRC service reported a failure", "source": f"OpenRC ({service_name})"}
    return None


def _status_from_process_scan(worker_label: str, process_patterns: tuple[str, ...]) -> dict[str, str]:
    if which("ps") is None:
        return {
            "state": "unknown",
            "detail": "Neither OpenRC nor process listing is available",
            "source": worker_label,
        }

    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "state": "unknown",
            "detail": "Process listing failed",
            "source": worker_label,
        }

    matches: list[str] = []
    patterns = tuple(pattern.lower() for pattern in process_patterns)
    for line in result.stdout.splitlines():
        normalized = line.lower()
        if any(pattern in normalized for pattern in patterns):
            matches.append(line.strip())

    if matches:
        return {
            "state": "running",
            "detail": f"Matched {len(matches)} process{'es' if len(matches) != 1 else ''}",
            "source": "Process scan",
        }

    return {
        "state": "stopped",
        "detail": "No matching process found",
        "source": "Process scan",
    }


def worker_statuses() -> list[dict[str, str]]:
    statuses: list[dict[str, str]] = []
    for worker in WORKER_DEFINITIONS:
        status: dict[str, str] | None = None
        for service_name in worker["service_names"]:
            status = _status_from_openrc(service_name)
            if status is not None:
                break
        if status is None:
            status = _status_from_process_scan(worker["label"], worker["process_patterns"])
        statuses.append(
            {
                "label": worker["label"],
                "state": status["state"],
                "detail": status["detail"],
                "source": status["source"],
            }
        )
    return statuses


def safe_create_section_row(slug: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        create_section_row(slug, payload)
    except ValueError as exc:
        return False, str(exc)
    except sqlite3.IntegrityError as exc:
        return False, str(exc)
    return True, None


def safe_update_section_row(slug: str, row_id: int, payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        update_section_row(slug, row_id, payload)
    except ValueError as exc:
        return False, str(exc)
    except sqlite3.IntegrityError as exc:
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
    expose_port_enabled = int(bool(payload.get("expose_port_enabled")))
    expose_bind_address = _normalize_ipv4_address(
        payload.get("expose_bind_address"),
        default="0.0.0.0",
        label="Bind address",
    )
    expose_port = _normalize_tcp_port(payload.get("expose_port"), default=8002, label="Expose port")
    expose_whitelist = _normalize_ip_whitelist(payload.get("expose_whitelist"))

    normalized["modem_type"] = modem_type
    normalized["expose_port_enabled"] = expose_port_enabled
    normalized["expose_bind_address"] = expose_bind_address
    normalized["expose_port"] = expose_port
    normalized["expose_whitelist"] = expose_whitelist
    normalized["name"] = str(payload.get("name") or "").strip()
    normalized["band"] = str(payload.get("band") or "").strip().lower()
    if modem_type == "SERIALL":
        normalized["device_path"] = normalize_serial_device_path(payload.get("device_path"))
        normalized["baud_rate"] = normalize_serial_baud_rate(payload.get("baud_rate"))
    else:
        normalized["device_path"] = str(payload.get("device_path") or "").strip()
        normalized["baud_rate"] = None
    normalized["notes"] = str(payload.get("notes") or "").strip()
    return normalized


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

    try:
        interval_minutes = int(str(payload.get("interval_minutes") or "30").strip())
    except ValueError as exc:
        raise ValueError("Send interval must be one of: 5, 10, 15, 30, 45, 60 minutes.") from exc
    if interval_minutes not in {5, 10, 15, 30, 45, 60}:
        raise ValueError("Send interval must be one of: 5, 10, 15, 30, 45, 60 minutes.")
    normalized["interval_minutes"] = interval_minutes

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
    symbol_table = str(result.get("symbol_table") or "/")
    symbol_code = str(result.get("symbol_code") or ">")
    result["symbol_icon"] = get_aprs_symbol_icon_path(f"{symbol_table}{symbol_code}")
    result["raw_frame_preview"] = _build_aprs_entity_preview(slug, result)
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
    return result


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
            "comment": payload.get("comment"),
            "path": payload.get("path"),
        }
        return build_object_tnc2(preview_payload)
    symbol_table = str(payload.get("symbol_table") or "/")
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
