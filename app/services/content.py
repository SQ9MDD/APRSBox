from __future__ import annotations

from datetime import datetime, timezone
import re
import sqlite3
import subprocess
from shutil import which
from typing import Any

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
    return dict(row) if row else {}


def update_station_settings(payload: dict[str, Any]) -> None:
    values = {
        "callsign": payload.get("callsign", ""),
        "ssid": payload.get("ssid", ""),
        "beacon_comment": payload.get("beacon_comment", ""),
        "latitude": payload.get("latitude", ""),
        "longitude": payload.get("longitude", ""),
        "symbol_table": payload.get("symbol_table", "/"),
        "symbol_code": payload.get("symbol_code", ">"),
        "tx_enabled": int(bool(payload.get("tx_enabled"))),
        "updated_at": utc_now(),
    }
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE station_settings
            SET callsign = :callsign,
                ssid = :ssid,
                beacon_comment = :beacon_comment,
                latitude = :latitude,
                longitude = :longitude,
                symbol_table = :symbol_table,
                symbol_code = :symbol_code,
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


def dashboard_summary() -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for slug, definition in SECTION_DEFINITIONS.items():
        row = fetch_one(f"SELECT COUNT(*) AS total FROM {definition.table_name}")
        metrics[slug] = row["total"] if row else 0
    metrics["users"] = fetch_one("SELECT COUNT(*) AS total FROM users")["total"]
    metrics["logs"] = fetch_one("SELECT COUNT(*) AS total FROM event_logs")["total"]
    return metrics


def heard_stations(limit: int = 500) -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT line, created_at
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

        callsign = parsed["source"]
        if callsign not in stations:
            stations[callsign] = {
                "callsign": callsign,
                "base_callsign": _base_callsign(callsign),
                "ssid": _ssid_value(callsign),
                "last_heard_at": row["created_at"],
                "last_heard_label": _relative_time_label(row["created_at"]),
                "symbol": "",
                "comment": "",
                "latitude": "",
                "longitude": "",
            }

        aprs_data = _parse_aprs_payload(parsed["info"])
        if aprs_data is None:
            continue

        station = stations[callsign]
        if not station["symbol"] and aprs_data.get("symbol"):
            station["symbol"] = aprs_data["symbol"]
        if not station["comment"] and aprs_data.get("comment"):
            station["comment"] = aprs_data["comment"]
        if not station["latitude"] and aprs_data.get("latitude"):
            station["latitude"] = aprs_data["latitude"]
        if not station["longitude"] and aprs_data.get("longitude"):
            station["longitude"] = aprs_data["longitude"]

    return list(stations.values())[:limit]


_TNC2_RE = re.compile(r"^(?P<source>[^>]+)>(?P<destination>[^,:]+)(?:,(?P<path>[^:]+))?:(?P<info>.*)$")


def _parse_tnc2_line(line: str) -> dict[str, str] | None:
    match = _TNC2_RE.match(line.strip())
    if not match:
        return None
    return match.groupdict(default="")


def _base_callsign(callsign: str) -> str:
    return callsign.split("-", 1)[0]


def _ssid_value(callsign: str) -> str:
    if "-" not in callsign:
        return ""
    return callsign.split("-", 1)[1]


def _relative_time_label(timestamp: str) -> str:
    try:
        heard_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp

    now = datetime.now(timezone.utc)
    delta_seconds = max(0, int((now - heard_at).total_seconds()))
    if delta_seconds < 60:
        return "teraz"
    if delta_seconds < 3600:
        minutes = delta_seconds // 60
        return f"{minutes} min temu"
    hours = delta_seconds // 3600
    return f"{hours} h temu"


def _parse_aprs_payload(info: str) -> dict[str, str] | None:
    if not info:
        return None

    packet_type = info[0]
    if packet_type in {"!", "="}:
        return _parse_position_without_timestamp(info)
    if packet_type in {"/", "@"}:
        return _parse_position_with_timestamp(info)
    return None


def _parse_position_without_timestamp(info: str) -> dict[str, str] | None:
    if len(info) < 20:
        return None
    latitude = _parse_latitude(info[1:9])
    symbol_table = info[9]
    longitude = _parse_longitude(info[10:19])
    symbol_code = info[19]
    if latitude is None or longitude is None:
        return None
    return {
        "latitude": latitude,
        "longitude": longitude,
        "symbol": f"{symbol_table}{symbol_code}",
        "comment": info[20:].strip(),
    }


def _parse_position_with_timestamp(info: str) -> dict[str, str] | None:
    if len(info) < 27:
        return None
    latitude = _parse_latitude(info[8:16])
    symbol_table = info[16]
    longitude = _parse_longitude(info[17:26])
    symbol_code = info[26]
    if latitude is None or longitude is None:
        return None
    return {
        "latitude": latitude,
        "longitude": longitude,
        "symbol": f"{symbol_table}{symbol_code}",
        "comment": info[27:].strip(),
    }


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
