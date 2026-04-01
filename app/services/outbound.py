from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import fetch_one, get_connection, log_event, utc_now

KISS_FEND = 0xC0
KISS_FESC = 0xDB
KISS_TFEND = 0xDC
KISS_TFESC = 0xDD
AX25_CONTROL_UI = 0x03
AX25_PID_NO_LAYER3 = 0xF0
OUTBOUND_KIND_BEACON = "beacon"
OUTBOUND_KIND_STATUS = "status"
OUTBOUND_KIND_OBJECT = "object"
OUTBOUND_KIND_MESSAGE = "message"
OUTBOUND_STATUS_QUEUED = "queued"
OUTBOUND_STATUS_PROCESSING = "processing"
OUTBOUND_STATUS_SENT = "sent"
OUTBOUND_STATUS_FAILED = "failed"


def enqueue_beacon_job(station_settings: dict[str, Any], *, trigger: str = "manual") -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    beacon_interface_id = station_settings.get("beacon_interface_id")
    if not callsign:
        return False, "Callsign is required."
    if beacon_interface_id in {None, ""}:
        return False, "Interface is required."
    try:
        interface_id = int(beacon_interface_id)
    except (TypeError, ValueError):
        return False, "Selected interface is invalid."
    modem = fetch_one(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE id = ?
        """,
        (interface_id,),
    )
    if modem is None:
        return False, "Selected interface does not exist."

    latitude = _parse_coordinate(station_settings.get("latitude"))
    longitude = _parse_coordinate(station_settings.get("longitude"))
    if latitude is None or longitude is None:
        return False, "Latitude and longitude must be valid decimal coordinates."

    payload = {
        "callsign": callsign,
        "ssid": ssid,
        "latitude": latitude,
        "longitude": longitude,
        "symbol_table": _normalize_symbol_table(station_settings.get("symbol_table")),
        "symbol_code": _normalize_symbol_code(station_settings.get("symbol_code")),
        "beacon_comment": str(station_settings.get("beacon_comment") or "").strip(),
        "beacon_path": str(station_settings.get("beacon_path") or "").strip(),
        "trigger": str(trigger or "manual").strip() or "manual",
    }
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO outbound_jobs(
                kind, interface_id, payload_json, status, scheduled_at,
                locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 0, NULL, ?, ?)
            """,
            (
                OUTBOUND_KIND_BEACON,
                int(modem["id"]),
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                OUTBOUND_STATUS_QUEUED,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        job_id = cursor.lastrowid
    log_event("INFO", "outbound", f"Queued {payload['trigger']} beacon job #{job_id} for interface {modem['name']}")
    return True, f"Beacon queued as job #{job_id}."


def enqueue_status_job(station_settings: dict[str, Any], *, trigger: str = "manual") -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    beacon_interface_id = station_settings.get("beacon_interface_id")
    status_text = str(station_settings.get("status_text") or "").strip()
    if not callsign:
        return False, "Callsign is required."
    if beacon_interface_id in {None, ""}:
        return False, "Interface is required."
    if not status_text:
        return False, "Status text is required."
    try:
        interface_id = int(beacon_interface_id)
    except (TypeError, ValueError):
        return False, "Selected interface is invalid."
    modem = fetch_one(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE id = ?
        """,
        (interface_id,),
    )
    if modem is None:
        return False, "Selected interface does not exist."

    payload = {
        "callsign": callsign,
        "ssid": ssid,
        "status_text": status_text,
        "trigger": str(trigger or "manual").strip() or "manual",
    }
    timestamp = utc_now()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO outbound_jobs(
                kind, interface_id, payload_json, status, scheduled_at,
                locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 0, NULL, ?, ?)
            """,
            (
                OUTBOUND_KIND_STATUS,
                int(modem["id"]),
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                OUTBOUND_STATUS_QUEUED,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        job_id = cursor.lastrowid
    log_event("INFO", "outbound", f"Queued {payload['trigger']} status job #{job_id} for interface {modem['name']}")
    return True, f"Status queued as job #{job_id}."


def pending_beacon_job_count() -> int:
    return pending_outbound_job_count(OUTBOUND_KIND_BEACON)


def pending_status_job_count() -> int:
    return pending_outbound_job_count(OUTBOUND_KIND_STATUS)


def pending_outbound_job_count(kind: str) -> int:
    row = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM outbound_jobs
        WHERE kind = ?
          AND status IN (?, ?)
        """,
        (kind, OUTBOUND_STATUS_QUEUED, OUTBOUND_STATUS_PROCESSING),
    )
    return int(row["total"]) if row else 0


def enqueue_object_job(
    obj: dict[str, Any],
    station_settings: dict[str, Any],
    *,
    trigger: str = "scheduled",
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    beacon_interface_id = station_settings.get("beacon_interface_id")
    if not callsign:
        return False, "Callsign is required."
    if beacon_interface_id in {None, ""}:
        return False, "Interface is required."
    try:
        interface_id = int(beacon_interface_id)
    except (TypeError, ValueError):
        return False, "Selected interface is invalid."
    modem = fetch_one(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE id = ?
        """,
        (interface_id,),
    )
    if modem is None:
        return False, "Selected interface does not exist."

    latitude = _parse_coordinate(obj.get("latitude"))
    longitude = _parse_coordinate(obj.get("longitude"))
    if latitude is None or longitude is None:
        return False, "Object latitude and longitude must be valid decimal coordinates."

    payload = {
        "object_id": int(obj["id"]),
        "callsign": callsign,
        "ssid": ssid,
        "name": str(obj.get("name") or ""),
        "lifetime": str(obj.get("lifetime") or "temporary"),
        "state": str(obj.get("state") or "live"),
        "latitude": latitude,
        "longitude": longitude,
        "symbol_table": _normalize_symbol_table(obj.get("symbol_table")),
        "symbol_code": _normalize_symbol_code(obj.get("symbol_code")),
        "comment": str(obj.get("comment") or "").strip(),
        "path": str(obj.get("path") or "").strip(),
        "object_timestamp": _object_timestamp(str(obj.get("lifetime") or "temporary")),
        "trigger": str(trigger or "scheduled").strip() or "scheduled",
    }
    now_text = utc_now()
    scheduled_at = (scheduled_for.astimezone(timezone.utc).replace(microsecond=0).isoformat() if scheduled_for else now_text)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO outbound_jobs(
                kind, interface_id, payload_json, status, scheduled_at,
                locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 0, NULL, ?, ?)
            """,
            (
                OUTBOUND_KIND_OBJECT,
                int(modem["id"]),
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                OUTBOUND_STATUS_QUEUED,
                scheduled_at,
                now_text,
                now_text,
            ),
        )
        job_id = cursor.lastrowid
    log_event("INFO", "outbound", f"Queued {payload['trigger']} object job #{job_id} for interface {modem['name']}")
    return True, f"Object queued as job #{job_id}."


def enqueue_message_job(
    bulletin: dict[str, Any],
    station_settings: dict[str, Any],
    *,
    trigger: str = "scheduled",
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    beacon_interface_id = station_settings.get("beacon_interface_id")
    if not callsign:
        return False, "Callsign is required."
    if beacon_interface_id in {None, ""}:
        return False, "Interface is required."
    try:
        interface_id = int(beacon_interface_id)
    except (TypeError, ValueError):
        return False, "Selected interface is invalid."
    modem = fetch_one(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE id = ?
        """,
        (interface_id,),
    )
    if modem is None:
        return False, "Selected interface does not exist."

    payload = {
        "message_id": int(bulletin["id"]),
        "callsign": callsign,
        "ssid": ssid,
        "message_kind": str(bulletin.get("message_kind") or "message").strip(),
        "addressee": str(bulletin.get("addressee") or "").strip().upper(),
        "bulletin_code": str(bulletin.get("bulletin_code") or "").strip().upper(),
        "group_name": str(bulletin.get("group_name") or "").strip().upper(),
        "message_text": str(bulletin.get("message_text") or "").strip(),
        "trigger": str(trigger or "scheduled").strip() or "scheduled",
    }
    now_text = utc_now()
    scheduled_at = (scheduled_for.astimezone(timezone.utc).replace(microsecond=0).isoformat() if scheduled_for else now_text)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO outbound_jobs(
                kind, interface_id, payload_json, status, scheduled_at,
                locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 0, NULL, ?, ?)
            """,
            (
                OUTBOUND_KIND_MESSAGE,
                int(modem["id"]),
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                OUTBOUND_STATUS_QUEUED,
                scheduled_at,
                now_text,
                now_text,
            ),
        )
        job_id = cursor.lastrowid
    log_event("INFO", "outbound", f"Queued {payload['trigger']} message job #{job_id} for interface {modem['name']}")
    return True, f"Message queued as job #{job_id}."


def claim_next_outbound_job() -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, kind, interface_id, payload_json, status, scheduled_at, attempt_count
            FROM outbound_jobs
            WHERE status = ?
              AND scheduled_at <= ?
            ORDER BY scheduled_at ASC, id ASC
            LIMIT 1
            """,
            (OUTBOUND_STATUS_QUEUED, utc_now()),
        ).fetchone()
        if row is None:
            return None
        locked_at = utc_now()
        connection.execute(
            """
            UPDATE outbound_jobs
            SET status = ?, locked_at = ?, started_at = ?, attempt_count = attempt_count + 1, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (OUTBOUND_STATUS_PROCESSING, locked_at, locked_at, locked_at, row["id"], OUTBOUND_STATUS_QUEUED),
        )
        updated = connection.execute("SELECT changes() AS changes").fetchone()
        if not updated or int(updated["changes"]) != 1:
            return None
    return get_outbound_job(row["id"])


def get_outbound_job(job_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT j.id, j.kind, j.interface_id, j.payload_json, j.status, j.scheduled_at, j.locked_at,
               j.started_at, j.sent_at, j.attempt_count, j.last_error, j.created_at, j.updated_at,
               m.name AS interface_name, m.modem_type, m.device_path, m.enabled AS interface_enabled, m.band
        FROM outbound_jobs j
        LEFT JOIN modems m ON m.id = j.interface_id
        WHERE j.id = ?
        """,
        (job_id,),
    )
    if row is None:
        return None
    result = dict(row)
    try:
        result["payload"] = json.loads(result.pop("payload_json") or "{}")
    except json.JSONDecodeError:
        result["payload"] = {}
    return result


def mark_outbound_job_sent(job_id: int) -> None:
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE outbound_jobs
            SET status = ?, sent_at = ?, last_error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (OUTBOUND_STATUS_SENT, timestamp, timestamp, job_id),
        )


def mark_outbound_job_failed(job_id: int, error: str) -> None:
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE outbound_jobs
            SET status = ?, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (OUTBOUND_STATUS_FAILED, error.strip()[:500], timestamp, job_id),
        )


def persist_outbound_frame(
    *,
    source: str,
    line: str,
    port: str = "0",
    command: str = "TX",
    payload_hex: str = "",
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO traffic_frames(source, format, line, port, command, length, hex, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source, "TNC2-TX", line, port, command, len(line.encode("utf-8")), payload_hex, utc_now()),
        )


def build_beacon_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    path = str(payload.get("beacon_path") or "").strip()
    info = _build_beacon_info(payload)
    header = f"{source}>APRS"
    if path:
        header = f"{header},{path}"
    return f"{header}:{info}"


def build_object_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    path = str(payload.get("path") or "").strip()
    info = _build_object_info(payload)
    header = f"{source}>APRS"
    if path:
        header = f"{header},{path}"
    return f"{header}:{info}"


def build_status_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    info = _build_status_info(payload)
    return f"{source}>APRS:{info}"


def build_message_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    info = _build_message_info(payload)
    return f"{source}>APRS:{info}"


def latest_object_dispatch_at() -> datetime | None:
    row = fetch_one(
        """
        SELECT COALESCE(sent_at, started_at, scheduled_at, created_at) AS dispatch_at
        FROM outbound_jobs
        WHERE kind = ?
        ORDER BY COALESCE(sent_at, started_at, scheduled_at, created_at) DESC, id DESC
        LIMIT 1
        """,
        (OUTBOUND_KIND_OBJECT,),
    )
    if row is None or not row["dispatch_at"]:
        return None
    return _parse_timestamp(str(row["dispatch_at"]))


def latest_message_dispatch_at() -> datetime | None:
    row = fetch_one(
        """
        SELECT COALESCE(sent_at, started_at, scheduled_at, created_at) AS dispatch_at
        FROM outbound_jobs
        WHERE kind = ?
        ORDER BY COALESCE(sent_at, started_at, scheduled_at, created_at) DESC, id DESC
        LIMIT 1
        """,
        (OUTBOUND_KIND_MESSAGE,),
    )
    if row is None or not row["dispatch_at"]:
        return None
    return _parse_timestamp(str(row["dispatch_at"]))


def build_tnc2_kiss_frame(line: str) -> bytes:
    source, destination, path, info = _parse_tnc2_line(line)
    ax25 = bytearray()
    addresses = [_encode_ax25_address(destination, is_last=False), _encode_ax25_address(source, is_last=not bool(path))]
    if path:
        path_parts = [item.strip() for item in path.split(",") if item.strip()]
        if path_parts:
            addresses[1] = _encode_ax25_address(source, is_last=False)
            for index, item in enumerate(path_parts):
                addresses.append(_encode_ax25_address(item.rstrip("*"), is_last=index == len(path_parts) - 1))
    for chunk in addresses:
        ax25.extend(chunk)
    ax25.append(AX25_CONTROL_UI)
    ax25.append(AX25_PID_NO_LAYER3)
    ax25.extend(info.encode("utf-8"))
    escaped = bytearray([0x00])
    for byte in ax25:
        if byte == KISS_FEND:
            escaped.extend((KISS_FESC, KISS_TFEND))
        elif byte == KISS_FESC:
            escaped.extend((KISS_FESC, KISS_TFESC))
        else:
            escaped.append(byte)
    return bytes([KISS_FEND]) + bytes(escaped) + bytes([KISS_FEND])


def _parse_coordinate(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_symbol_table(value: Any) -> str:
    symbol_table = str(value or "/").strip()
    return symbol_table if symbol_table in {"/", "\\"} else "/"


def _normalize_symbol_code(value: Any) -> str:
    symbol_code = str(value or ">").strip()[:1]
    if len(symbol_code) != 1 or not (33 <= ord(symbol_code) <= 126):
        return ">"
    return symbol_code


def _format_station_callsign(callsign: Any, ssid: Any) -> str:
    base = str(callsign or "").strip().upper()
    ssid_text = str(ssid or "").strip()
    return f"{base}-{ssid_text}" if ssid_text else base


def _build_beacon_info(payload: dict[str, Any]) -> str:
    latitude = _format_aprs_latitude(float(payload["latitude"]))
    longitude = _format_aprs_longitude(float(payload["longitude"]))
    symbol_table = _normalize_symbol_table(payload.get("symbol_table"))
    symbol_code = _normalize_symbol_code(payload.get("symbol_code"))
    comment = str(payload.get("beacon_comment") or "").strip()
    return f"!{latitude}{symbol_table}{longitude}{symbol_code}{comment}"


def _build_object_info(payload: dict[str, Any]) -> str:
    name = str(payload.get("name") or "")[:9].ljust(9)
    state_marker = "*" if str(payload.get("state") or "live") == "live" else "_"
    timestamp = str(payload.get("object_timestamp") or _object_timestamp(str(payload.get("lifetime") or "temporary")))
    latitude = _format_aprs_latitude(float(payload["latitude"]))
    longitude = _format_aprs_longitude(float(payload["longitude"]))
    symbol_table = _normalize_symbol_table(payload.get("symbol_table"))
    symbol_code = _normalize_symbol_code(payload.get("symbol_code"))
    comment = str(payload.get("comment") or "").strip()
    return f";{name}{state_marker}{timestamp}{latitude}{symbol_table}{longitude}{symbol_code}{comment}"


def _build_status_info(payload: dict[str, Any]) -> str:
    return f">{str(payload.get('status_text') or '').strip()}"


def _build_message_info(payload: dict[str, Any]) -> str:
    addressee = resolve_message_addressee(payload)
    message_text = str(payload.get("message_text") or "").strip()
    return f":{addressee}:{message_text}"


def resolve_message_addressee(payload: dict[str, Any]) -> str:
    message_kind = str(payload.get("message_kind") or "message").strip()
    if message_kind == "message":
        return str(payload.get("addressee") or "").strip().upper()[:9].ljust(9)
    bulletin_code = str(payload.get("bulletin_code") or "").strip().upper()[:1]
    if message_kind == "announcement":
        return f"BLN{bulletin_code}".ljust(9)
    if message_kind == "group_bulletin":
        group_name = str(payload.get("group_name") or "").strip().upper()[:5]
        return f"BLN{bulletin_code}{group_name}".ljust(9)
    return f"BLN{bulletin_code}".ljust(9)


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


def _object_timestamp(lifetime: str) -> str:
    if lifetime == "permanent":
        return "111111z"
    return datetime.now(timezone.utc).strftime("%d%H%Mz")


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_tnc2_line(line: str) -> tuple[str, str, str, str]:
    header, separator, info = line.partition(":")
    if not separator:
        raise ValueError("Invalid TNC2 frame: missing info field.")
    source_destination, *path_parts = header.split(",")
    source, arrow, destination = source_destination.partition(">")
    if not arrow:
        raise ValueError("Invalid TNC2 frame: missing source/destination separator.")
    return source.strip(), destination.strip(), ",".join(item.strip() for item in path_parts if item.strip()), info


def _encode_ax25_address(value: str, *, is_last: bool) -> bytes:
    callsign, ssid = _split_callsign_ssid(value)
    padded = callsign.ljust(6)
    encoded = bytearray((ord(char) << 1) for char in padded[:6])
    control = 0x60 | ((ssid & 0x0F) << 1)
    if is_last:
        control |= 0x01
    encoded.append(control)
    return bytes(encoded)


def _split_callsign_ssid(value: str) -> tuple[str, int]:
    normalized = value.strip().upper()
    base, separator, ssid_text = normalized.partition("-")
    if not base:
        raise ValueError("Invalid AX.25 callsign.")
    ssid = 0
    if separator:
        try:
            ssid = int(ssid_text)
        except ValueError as exc:
            raise ValueError("Invalid AX.25 SSID.") from exc
        if ssid < 0 or ssid > 15:
            raise ValueError("AX.25 SSID out of range.")
    return base[:6], ssid
