from __future__ import annotations

from datetime import datetime, timezone
import re
import sqlite3
import subprocess
from shutil import which
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
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


def get_section_rows(slug: str) -> list[dict[str, Any]]:
    definition = SECTION_DEFINITIONS[slug]
    rows = fetch_all(f"SELECT * FROM {definition.table_name} ORDER BY id DESC")
    return [dict(row) for row in rows]


def get_section_row(slug: str, row_id: int) -> dict[str, Any] | None:
    definition = SECTION_DEFINITIONS[slug]
    row = fetch_one(f"SELECT * FROM {definition.table_name} WHERE id = ?", (row_id,))
    return dict(row) if row else None


def create_section_row(slug: str, payload: dict[str, Any]) -> None:
    definition = SECTION_DEFINITIONS[slug]
    timestamp = utc_now()
    values: dict[str, Any] = {}
    for field in definition.fields:
        name = field["name"]
        if field["type"] == "checkbox":
            values[name] = int(bool(payload.get(name)))
        else:
            values[name] = payload.get(name)
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
    values: dict[str, Any] = {}
    for field in definition.fields:
        name = field["name"]
        if field["type"] == "checkbox":
            values[name] = int(bool(payload.get(name)))
        else:
            values[name] = payload.get(name)
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


def update_station_settings(payload: dict[str, Any]) -> None:
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
    try:
        beacon_interval_minutes = int(payload.get("beacon_interval_minutes") or 30)
    except (TypeError, ValueError):
        beacon_interval_minutes = 30
    if beacon_interval_minutes not in {15, 30, 45, 60}:
        beacon_interval_minutes = 30
    symbol_table = str(payload.get("symbol_table", "/") or "/").strip()
    if symbol_table not in {"/", "\\"}:
        symbol_table = "/"
    symbol_code = str(payload.get("symbol_code", ">") or ">").strip()[:1]
    if len(symbol_code) != 1 or not (33 <= ord(symbol_code) <= 126):
        symbol_code = ">"
    values = {
        "callsign": payload.get("callsign", ""),
        "ssid": payload.get("ssid", ""),
        "beacon_interface_id": beacon_interface_id,
        "beacon_comment": payload.get("beacon_comment", ""),
        "beacon_interval_minutes": beacon_interval_minutes,
        "beacon_path": payload.get("beacon_path", ""),
        "latitude": payload.get("latitude", ""),
        "longitude": payload.get("longitude", ""),
        "symbol_table": symbol_table,
        "symbol_code": symbol_code,
        "default_units": default_units,
        "tx_enabled": int(bool(payload.get("tx_enabled"))),
        "updated_at": utc_now(),
    }
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
    log_event("INFO", "config", "Updated station settings")


def recent_event_logs(limit: int = 100) -> list[dict[str, Any]]:
    rows = fetch_all(
        "SELECT id, level, category, message, created_at FROM event_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in rows]


def traffic_snapshot(limit: int = 400) -> dict[str, Any]:
    state_row = fetch_one(
        """
        SELECT status, status_detail, active_modem_name, active_modem_endpoint, last_error, updated_at
        FROM traffic_runtime_state
        WHERE id = 1
        """
    )
    frame_rows = fetch_all(
        """
        SELECT source, format, line, port, command, length, hex, created_at
        FROM traffic_frames
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    active_modem = None
    if state_row and (state_row["active_modem_name"] or state_row["active_modem_endpoint"]):
        active_modem = {
            "name": state_row["active_modem_name"] or "",
            "device_path": state_row["active_modem_endpoint"] or "",
        }
    return {
        "status": state_row["status"] if state_row else "idle",
        "status_detail": state_row["status_detail"] if state_row else "Traffic monitor state unavailable.",
        "active_modem": active_modem,
        "last_error": state_row["last_error"] if state_row else None,
        "updated_at": _format_monitor_timestamp(state_row["updated_at"]) if state_row else None,
        "frames": [
            {
                "timestamp": _format_monitor_timestamp(row["created_at"]),
                "source": row["source"],
                "format": row["format"],
                "line": row["line"],
                "port": row["port"] or "",
                "command": row["command"] or "",
                "length": str(row["length"]),
                "hex": row["hex"] or "",
            }
            for row in frame_rows
        ],
    }


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


def heard_stations(limit: int = 500, unit_system: str = "metric") -> list[dict[str, Any]]:
    snapshots = get_heard_station_snapshots(limit=limit)
    stations: list[dict[str, Any]] = []
    for snapshot in snapshots:
        stations.append(
            {
                "callsign": snapshot["callsign"],
                "display_callsign": snapshot["display_callsign"],
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
                "detail_href": build_station_detail_href(snapshot["display_callsign"]),
            }
        )
    return stations


def get_station_detail(callsign: str, unit_system: str = "metric") -> dict[str, Any] | None:
    normalized_callsign = callsign.strip()
    if not normalized_callsign:
        return None

    snapshot = _find_station_snapshot(normalized_callsign)
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
        "messaging_capable": _messaging_capable(snapshot),
        "data": _format_decoded_data_for_display(snapshot["data_raw"], unit_system),
        "fields": _station_detail_fields(snapshot, unit_system),
    }


def get_recent_station_packets(callsign: str, limit: int = 10) -> list[dict[str, Any]]:
    snapshot = _find_station_snapshot(callsign.strip())
    if snapshot is None:
        return []

    station_key = snapshot["display_callsign"]
    rows = fetch_all(
        """
        SELECT source, line, created_at
        FROM traffic_frames
        WHERE format = 'TNC2'
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


def get_related_ssids(base_callsign: str) -> list[dict[str, Any]]:
    normalized_base = base_callsign.strip()
    if not normalized_base:
        return []

    related: list[dict[str, Any]] = []
    seen: set[str] = set()
    for snapshot in get_heard_station_snapshots():
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


def _find_station_snapshot(callsign: str) -> dict[str, Any] | None:
    normalized = callsign.strip().casefold()
    if not normalized:
        return None
    snapshots = get_heard_station_snapshots()
    for snapshot in snapshots:
        if snapshot["display_callsign"].casefold() == normalized:
            return snapshot
    for snapshot in snapshots:
        if snapshot["callsign"].casefold() == normalized:
            return snapshot
    return None


def get_heard_station_snapshots(limit: int = 500) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT source, line, created_at
        FROM traffic_frames
        WHERE format = 'TNC2'
        ORDER BY created_at DESC, id DESC
        """
    )
    stations: dict[str, dict[str, Any]] = {}

    for row in rows:
        parsed = _parse_tnc2_line(row["line"])
        if parsed is None:
            continue

        callsign = parsed["source"].strip()
        aprs_data = _parse_aprs_packet(parsed)
        if aprs_data is None:
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
            )

        station = stations[station_key]
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


def _new_station_snapshot(
    name: str,
    created_at: str,
    source: str,
    destination: str,
    path: str,
    raw_text: str,
) -> dict[str, Any]:
    heard_date, heard_relative = _format_last_heard_parts(created_at)
    base_callsign, ssid = _split_ssid(name)
    return {
        "callsign": base_callsign,
        "ssid": ssid,
        "display_callsign": name,
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
    }


_TNC2_RE = re.compile(r"^(?P<source>[^>]+?)\s*>\s*(?P<destination>[^,:]+?)(?:\s*,\s*(?P<path>[^:]+))?\s*:(?P<info>.*)$")


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
        fields.append({"label": "Last heard", "value": str(snapshot["last_heard_date"])})
    if snapshot.get("last_heard_relative"):
        fields.append({"label": "Last heard age", "value": str(snapshot["last_heard_relative"])})
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
    if packet_type == "_":
        return _parse_weather_only_packet(info)
    if packet_type == ";":
        return _parse_object_packet(info)
    if packet_type == ":":
        return None
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
    except sqlite3.IntegrityError as exc:
        return False, str(exc)
    return True, None


def safe_update_section_row(slug: str, row_id: int, payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        update_section_row(slug, row_id, payload)
    except sqlite3.IntegrityError as exc:
        return False, str(exc)
    return True, None
