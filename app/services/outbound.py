from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.services.tx_scope import TX_SCOPE_ALL_ACTIVE, TX_SCOPE_SINGLE, normalize_tx_scope

KISS_FEND = 0xC0
KISS_FESC = 0xDB
KISS_TFEND = 0xDC
KISS_TFESC = 0xDD
AX25_CONTROL_UI = 0x03
AX25_PID_NO_LAYER3 = 0xF0
APRSBOX_DESTINATION = "APBOX0"
OUTBOUND_KIND_BEACON = "beacon"
OUTBOUND_KIND_STATUS = "status"
OUTBOUND_KIND_OBJECT = "object"
OUTBOUND_KIND_MESSAGE = "message"
OUTBOUND_KIND_WX = "wx"
OUTBOUND_KIND_DIGI_TX = "digi_tx"
OUTBOUND_STATUS_QUEUED = "queued"
OUTBOUND_STATUS_PROCESSING = "processing"
OUTBOUND_STATUS_SENT = "sent"
OUTBOUND_STATUS_FAILED = "failed"
STALE_BEACON_PROCESSING_REASON = "Beacon was not transmitted: APRSBox core restarted while outbound job was processing."
STALE_WX_PROCESSING_REASON = "WX frame was not transmitted: APRSBox core restarted while outbound job was processing."
_AX25_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,6}$")
LOCAL_TX_ORIGIN = "local_generated"
INTERNAL_TX_INTERFACE_NAME = "Internal TX"
LOCAL_TX_OUTBOUND_PURPOSE_BY_KIND = {
    OUTBOUND_KIND_BEACON: "beacon",
    OUTBOUND_KIND_STATUS: "status",
    OUTBOUND_KIND_OBJECT: "object",
    OUTBOUND_KIND_MESSAGE: "message",
    OUTBOUND_KIND_WX: "wx",
}


def _list_active_tnc_modems() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE enabled = 1
          AND modem_type IN ('TCP', 'SERIALL', 'SERIAL')
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    return [dict(row) for row in rows]


def _get_modem_by_id(interface_id: int) -> dict[str, Any] | None:
    modem = fetch_one(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE id = ?
        """,
        (interface_id,),
    )
    return dict(modem) if modem is not None else None


def _resolve_station_target_modems(station_settings: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    if bool(station_settings.get("beacon_internal_tx")):
        return [
            {
                "id": None,
                "name": INTERNAL_TX_INTERFACE_NAME,
                "modem_type": "",
                "band": "",
                "device_path": "",
                "enabled": 1,
                "internal_tx_only": True,
            }
        ], None

    scope = normalize_tx_scope(station_settings.get("beacon_tx_scope"), default=TX_SCOPE_SINGLE)
    if scope == TX_SCOPE_ALL_ACTIVE:
        modems = _list_active_tnc_modems()
        if not modems:
            return None, "No active TNC interfaces are available."
        return modems, None

    beacon_interface_id = station_settings.get("beacon_interface_id")
    if beacon_interface_id in {None, ""}:
        return None, "Interface is required."
    try:
        interface_id = int(beacon_interface_id)
    except (TypeError, ValueError):
        return None, "Selected interface is invalid."
    modem = _get_modem_by_id(interface_id)
    if modem is None:
        return None, "Selected interface does not exist."
    return [modem], None


def _resolve_wx_target_modems(payload: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    scope = normalize_tx_scope(payload.get("tx_scope"), default=TX_SCOPE_SINGLE)
    if scope == TX_SCOPE_ALL_ACTIVE:
        interface_ids: list[int] = []
        for item in payload.get("interface_ids") or []:
            try:
                interface_ids.append(int(item))
            except (TypeError, ValueError):
                continue
        if not interface_ids:
            return None, "No active TNC interfaces are available."
        modems: list[dict[str, Any]] = []
        missing = False
        for interface_id in interface_ids:
            modem = _get_modem_by_id(interface_id)
            if modem is None:
                missing = True
                continue
            modems.append(modem)
        if not modems:
            return None, "No active TNC interfaces are available."
        if missing:
            log_event("WARNING", "outbound", "WX all-active target list contained unavailable interfaces.")
        return modems, None

    interface_id = payload.get("interface_id")
    if interface_id in {None, ""}:
        return None, "WX interface is required."
    try:
        normalized_interface_id = int(interface_id)
    except (TypeError, ValueError):
        return None, "Selected WX interface is invalid."
    modem = _get_modem_by_id(normalized_interface_id)
    if modem is None:
        return None, "Selected WX interface does not exist."
    return [modem], None


def _enqueue_jobs_for_modems(
    *,
    kind: str,
    payload: dict[str, Any],
    modems: list[dict[str, Any]],
    scheduled_at: str,
    aprs_message_id: int | None = None,
) -> list[int]:
    now_text = utc_now()
    stored_payload = _with_local_tx_metadata(kind=kind, payload=payload)
    job_ids: list[int] = []
    with get_connection() as connection:
        for modem in modems:
            internal_tx_only = bool(modem.get("internal_tx_only"))
            interface_id_value = modem.get("id")
            try:
                interface_id = int(interface_id_value) if interface_id_value not in {None, ""} else None
            except (TypeError, ValueError):
                interface_id = None
            payload_per_job = dict(stored_payload)
            if internal_tx_only:
                payload_per_job["internal_tx_only"] = True
            payload_json = json.dumps(payload_per_job, ensure_ascii=True, separators=(",", ":"))
            cursor = connection.execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, aprs_message_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0, NULL, ?, ?)
                """,
                (
                    kind,
                    interface_id,
                    aprs_message_id,
                    payload_json,
                    OUTBOUND_STATUS_QUEUED,
                    scheduled_at,
                    now_text,
                    now_text,
                ),
            )
            job_ids.append(int(cursor.lastrowid))
    return job_ids


def _format_queue_result(label: str, job_ids: list[int]) -> str:
    if len(job_ids) == 1:
        return f"{label} queued as job #{job_ids[0]}."
    joined_ids = ", ".join(str(job_id) for job_id in job_ids)
    return f"{label} queued as jobs #{joined_ids}."


def _with_local_tx_metadata(*, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    purpose = LOCAL_TX_OUTBOUND_PURPOSE_BY_KIND.get(str(kind or "").strip())
    if not purpose:
        return dict(payload)

    stored = dict(payload)
    event_id = str(stored.get("local_tx_event_id") or "").strip()
    if not event_id:
        event_id = uuid.uuid4().hex
    stored["local_tx_event_id"] = event_id

    metadata = dict(stored.get("local_tx_metadata") or {})
    metadata["origin"] = LOCAL_TX_ORIGIN
    metadata["local_generated"] = True
    metadata["own_station"] = True
    metadata["frame_purpose"] = str(metadata.get("frame_purpose") or purpose).strip() or purpose
    stored["local_tx_metadata"] = metadata
    return stored


def enqueue_beacon_job(
    station_settings: dict[str, Any],
    *,
    trigger: str = "manual",
    aprs_message_id: int | None = None,
    beacon_path_override: str | None = None,
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    if not callsign:
        return False, "Callsign is required."
    target_modems, target_error = _resolve_station_target_modems(station_settings)
    if not target_modems:
        return False, str(target_error or "Interface is required.")

    latitude = _parse_coordinate(station_settings.get("latitude"))
    longitude = _parse_coordinate(station_settings.get("longitude"))
    if latitude is None or longitude is None:
        return False, "Latitude and longitude must be valid decimal coordinates."
    symbol_table = _normalize_symbol_table(station_settings.get("symbol_table"))
    symbol_overlay = _normalize_symbol_overlay(station_settings.get("symbol_overlay"), symbol_table=symbol_table)

    selected_beacon_path = str(station_settings.get("beacon_path") or "").strip()
    if beacon_path_override is not None:
        selected_beacon_path = str(beacon_path_override).strip()

    payload = {
        "aprs_message_id": aprs_message_id,
        "callsign": callsign,
        "ssid": ssid,
        "latitude": latitude,
        "longitude": longitude,
        "symbol_table": symbol_table,
        "symbol_code": _normalize_symbol_code(station_settings.get("symbol_code")),
        "symbol_overlay": symbol_overlay,
        "beacon_comment": str(station_settings.get("beacon_comment") or "").strip(),
        "beacon_path": selected_beacon_path,
        "trigger": str(trigger or "manual").strip() or "manual",
    }
    scheduled_at = scheduled_for.astimezone(timezone.utc).replace(microsecond=0).isoformat() if scheduled_for else utc_now()
    job_ids = _enqueue_jobs_for_modems(
        kind=OUTBOUND_KIND_BEACON,
        payload=payload,
        modems=target_modems,
        scheduled_at=scheduled_at,
    )
    modem_names = ", ".join(str(modem["name"]) for modem in target_modems)
    if len(job_ids) == 1:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} beacon job #{job_ids[0]} for interface {modem_names}")
    else:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} beacon jobs {job_ids} for interfaces: {modem_names}")
    return True, _format_queue_result("Beacon", job_ids)


def enqueue_status_job(
    station_settings: dict[str, Any],
    *,
    trigger: str = "manual",
    aprs_message_id: int | None = None,
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    status_text = str(station_settings.get("status_text") or "").strip()
    if not callsign:
        return False, "Callsign is required."
    if not status_text:
        return False, "Status text is required."
    target_modems, target_error = _resolve_station_target_modems(station_settings)
    if not target_modems:
        return False, str(target_error or "Interface is required.")

    payload = {
        "aprs_message_id": aprs_message_id,
        "callsign": callsign,
        "ssid": ssid,
        "status_text": status_text,
        "trigger": str(trigger or "manual").strip() or "manual",
    }
    scheduled_at = scheduled_for.astimezone(timezone.utc).replace(microsecond=0).isoformat() if scheduled_for else utc_now()
    job_ids = _enqueue_jobs_for_modems(
        kind=OUTBOUND_KIND_STATUS,
        payload=payload,
        modems=target_modems,
        scheduled_at=scheduled_at,
    )
    modem_names = ", ".join(str(modem["name"]) for modem in target_modems)
    if len(job_ids) == 1:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} status job #{job_ids[0]} for interface {modem_names}")
    else:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} status jobs {job_ids} for interfaces: {modem_names}")
    return True, _format_queue_result("Status", job_ids)


def pending_beacon_job_count() -> int:
    return pending_outbound_job_count(OUTBOUND_KIND_BEACON)


def pending_status_job_count() -> int:
    return pending_outbound_job_count(OUTBOUND_KIND_STATUS)


def pending_wx_job_count() -> int:
    return pending_outbound_job_count(OUTBOUND_KIND_WX)


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


def recover_stale_processing_beacon_jobs() -> list[int]:
    recovered_ids: list[int] = []
    timestamp = utc_now()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id
            FROM outbound_jobs
            WHERE kind = ?
              AND status = ?
            ORDER BY id ASC
            """,
            (OUTBOUND_KIND_BEACON, OUTBOUND_STATUS_PROCESSING),
        ).fetchall()
        for row in rows:
            job_id = int(row["id"])
            connection.execute(
                """
                UPDATE outbound_jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                  AND status = ?
                """,
                (
                    OUTBOUND_STATUS_FAILED,
                    STALE_BEACON_PROCESSING_REASON,
                    timestamp,
                    job_id,
                    OUTBOUND_STATUS_PROCESSING,
                ),
            )
            changed = connection.execute("SELECT changes() AS total").fetchone()
            if changed and int(changed["total"]) == 1:
                recovered_ids.append(job_id)
    return recovered_ids


def recover_stale_processing_wx_jobs() -> list[int]:
    recovered_ids: list[int] = []
    timestamp = utc_now()
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id
            FROM outbound_jobs
            WHERE kind = ?
              AND status = ?
            ORDER BY id ASC
            """,
            (OUTBOUND_KIND_WX, OUTBOUND_STATUS_PROCESSING),
        ).fetchall()
        for row in rows:
            job_id = int(row["id"])
            connection.execute(
                """
                UPDATE outbound_jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                  AND status = ?
                """,
                (
                    OUTBOUND_STATUS_FAILED,
                    STALE_WX_PROCESSING_REASON,
                    timestamp,
                    job_id,
                    OUTBOUND_STATUS_PROCESSING,
                ),
            )
            changed = connection.execute("SELECT changes() AS total").fetchone()
            if changed and int(changed["total"]) == 1:
                recovered_ids.append(job_id)
    return recovered_ids


def oldest_pending_outbound_job(kind: str) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, status, scheduled_at, started_at
        FROM outbound_jobs
        WHERE kind = ?
          AND status IN (?, ?)
        ORDER BY
            CASE status WHEN ? THEN 0 ELSE 1 END ASC,
            COALESCE(started_at, scheduled_at, created_at) ASC,
            id ASC
        LIMIT 1
        """,
        (kind, OUTBOUND_STATUS_QUEUED, OUTBOUND_STATUS_PROCESSING, OUTBOUND_STATUS_PROCESSING),
    )
    return dict(row) if row is not None else None


def enqueue_object_job(
    obj: dict[str, Any],
    station_settings: dict[str, Any],
    *,
    trigger: str = "scheduled",
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    if not callsign:
        return False, "Callsign is required."
    target_modems, target_error = _resolve_station_target_modems(station_settings)
    if not target_modems:
        return False, str(target_error or "Interface is required.")

    latitude = _parse_coordinate(obj.get("latitude"))
    longitude = _parse_coordinate(obj.get("longitude"))
    if latitude is None or longitude is None:
        return False, "Object latitude and longitude must be valid decimal coordinates."
    symbol_table = _normalize_symbol_table(obj.get("symbol_table"))
    symbol_overlay = _normalize_symbol_overlay(obj.get("symbol_overlay"), symbol_table=symbol_table)

    payload = {
        "object_id": int(obj["id"]),
        "callsign": callsign,
        "ssid": ssid,
        "name": str(obj.get("name") or ""),
        "lifetime": str(obj.get("lifetime") or "temporary"),
        "state": str(obj.get("state") or "live"),
        "latitude": latitude,
        "longitude": longitude,
        "symbol_table": symbol_table,
        "symbol_code": _normalize_symbol_code(obj.get("symbol_code")),
        "symbol_overlay": symbol_overlay,
        "comment": str(obj.get("comment") or "").strip(),
        "path": str(obj.get("path") or "").strip(),
        "object_timestamp": _object_timestamp(str(obj.get("lifetime") or "temporary")),
        "trigger": str(trigger or "scheduled").strip() or "scheduled",
    }
    scheduled_at = (scheduled_for.astimezone(timezone.utc).replace(microsecond=0).isoformat() if scheduled_for else utc_now())
    job_ids = _enqueue_jobs_for_modems(
        kind=OUTBOUND_KIND_OBJECT,
        payload=payload,
        modems=target_modems,
        scheduled_at=scheduled_at,
    )
    modem_names = ", ".join(str(modem["name"]) for modem in target_modems)
    if len(job_ids) == 1:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} object job #{job_ids[0]} for interface {modem_names}")
    else:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} object jobs {job_ids} for interfaces: {modem_names}")
    return True, _format_queue_result("Object", job_ids)


def enqueue_message_job(
    bulletin: dict[str, Any],
    station_settings: dict[str, Any],
    *,
    trigger: str = "scheduled",
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    if not callsign:
        return False, "Callsign is required."
    target_modems, target_error = _resolve_station_target_modems(station_settings)
    if not target_modems:
        return False, str(target_error or "Interface is required.")

    payload = {
        "message_id": int(bulletin["id"]),
        "callsign": callsign,
        "ssid": ssid,
        "message_kind": str(bulletin.get("message_kind") or "bulletin").strip(),
        "bulletin_code": str(bulletin.get("bulletin_code") or "").strip().upper(),
        "group_name": str(bulletin.get("group_name") or "").strip().upper(),
        "path": str(bulletin.get("path") or "").strip(),
        "message_text": str(bulletin.get("message_text") or "").strip(),
        "trigger": str(trigger or "scheduled").strip() or "scheduled",
    }
    scheduled_at = (scheduled_for.astimezone(timezone.utc).replace(microsecond=0).isoformat() if scheduled_for else utc_now())
    job_ids = _enqueue_jobs_for_modems(
        kind=OUTBOUND_KIND_MESSAGE,
        payload=payload,
        modems=target_modems,
        scheduled_at=scheduled_at,
    )
    modem_names = ", ".join(str(modem["name"]) for modem in target_modems)
    if len(job_ids) == 1:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} message job #{job_ids[0]} for interface {modem_names}")
    else:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} message jobs {job_ids} for interfaces: {modem_names}")
    return True, _format_queue_result("Message", job_ids)


def enqueue_wx_job(payload: dict[str, Any]) -> tuple[bool, str]:
    callsign = str(payload.get("callsign") or "").strip().upper()
    if not callsign:
        return False, "WX callsign is required."
    target_modems, target_error = _resolve_wx_target_modems(payload)
    if not target_modems:
        return False, str(target_error or "WX interface is required.")
    latitude = _parse_coordinate(payload.get("latitude"))
    longitude = _parse_coordinate(payload.get("longitude"))
    if latitude is None or longitude is None:
        return False, "WX latitude and longitude must be valid decimal coordinates."

    weather = payload.get("weather") or {}
    if not isinstance(weather, dict):
        return False, "WX weather payload is invalid."

    base_payload = {
        "callsign": callsign,
        "ssid": str(payload.get("ssid") or "").strip(),
        "latitude": latitude,
        "longitude": longitude,
        "path": str(payload.get("path") or "").strip(),
        "weather": weather,
        "trigger": str(payload.get("trigger") or "scheduled").strip() or "scheduled",
        "generated_at": str(payload.get("generated_at") or utc_now()).strip(),
    }
    base_payload = _with_local_tx_metadata(kind=OUTBOUND_KIND_WX, payload=base_payload)
    now_text = utc_now()
    job_ids: list[int] = []
    with get_connection() as connection:
        for modem in target_modems:
            stored_payload = dict(base_payload)
            stored_payload["interface_id"] = int(modem["id"])
            cursor = connection.execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 0, NULL, ?, ?)
                """,
                (
                    OUTBOUND_KIND_WX,
                    int(modem["id"]),
                    json.dumps(stored_payload, ensure_ascii=True, separators=(",", ":")),
                    OUTBOUND_STATUS_QUEUED,
                    now_text,
                    now_text,
                    now_text,
                ),
            )
            job_ids.append(int(cursor.lastrowid))
    modem_names = ", ".join(str(modem["name"]) for modem in target_modems)
    if len(job_ids) == 1:
        log_event("INFO", "outbound", f"Queued {base_payload['trigger']} WX job #{job_ids[0]} for interface {modem_names}")
    else:
        log_event("INFO", "outbound", f"Queued {base_payload['trigger']} WX jobs {job_ids} for interfaces: {modem_names}")
    return True, _format_queue_result("WX", job_ids)


def enqueue_digi_tx_job(
    *,
    interface_name: str,
    line: str,
    trigger: str = "digi_flow",
    flow_id: int | None = None,
    frame_uid: str | None = None,
) -> tuple[bool, str]:
    target_name = str(interface_name or "").strip()
    tnc2_line = str(line or "").strip()
    if not target_name:
        return False, "RF target is required."
    if not tnc2_line:
        return False, "Packet line is required."

    modem = fetch_one(
        """
        SELECT id, name, modem_type, band, device_path, enabled
        FROM modems
        WHERE name = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (target_name,),
    )
    if modem is None:
        return False, "Selected interface does not exist."

    payload = {
        "line": tnc2_line,
        "trigger": str(trigger or "digi_flow").strip() or "digi_flow",
        "flow_id": int(flow_id) if flow_id is not None else None,
        "frame_uid": str(frame_uid).strip() if frame_uid is not None else None,
    }
    now_text = utc_now()
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
                OUTBOUND_KIND_DIGI_TX,
                int(modem["id"]),
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                OUTBOUND_STATUS_QUEUED,
                now_text,
                now_text,
                now_text,
            ),
        )
        job_id = int(cursor.lastrowid)
    log_event("INFO", "outbound", f"Queued {payload['trigger']} DIGI TX job #{job_id} for interface {modem['name']}")
    return True, f"DIGI TX queued as job #{job_id}."


def enqueue_direct_message_job(
    message: dict[str, Any],
    station_settings: dict[str, Any],
    *,
    trigger: str = "manual",
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    addressee = str(message.get("addressee") or "").strip().upper()
    message_text = str(message.get("message_text") or "").strip()
    message_number = str(message.get("message_number") or "").strip().upper()
    payload = {
        "aprs_message_id": int(message["id"]),
        "callsign": str(station_settings.get("callsign") or "").strip().upper(),
        "ssid": str(station_settings.get("ssid") or "").strip(),
        "message_kind": "direct_message",
        "addressee": addressee,
        "path": str(message.get("path") or "").strip(),
        "message_text": message_text,
        "message_number": message_number,
        "trigger": str(trigger or "manual").strip() or "manual",
    }
    return _enqueue_generic_message_payload(payload, station_settings, scheduled_for=scheduled_for)


def enqueue_query_message_job(
    message: dict[str, Any],
    station_settings: dict[str, Any],
    *,
    trigger: str = "manual",
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    addressee = str(message.get("addressee") or "").strip().upper()
    message_text = str(message.get("message_text") or "").strip()
    payload = {
        "aprs_message_id": int(message["id"]),
        "callsign": str(station_settings.get("callsign") or "").strip().upper(),
        "ssid": str(station_settings.get("ssid") or "").strip(),
        "message_kind": "query",
        "addressee": addressee,
        "path": str(message.get("path") or "").strip(),
        "message_text": message_text,
        "trigger": str(trigger or "manual").strip() or "manual",
    }
    return _enqueue_generic_message_payload(payload, station_settings, scheduled_for=scheduled_for)


def enqueue_query_response_job(
    *,
    addressee: str,
    message_text: str,
    station_settings: dict[str, Any],
    trigger: str = "query-response",
    path: str = "",
    aprs_message_id: int | None = None,
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    payload = {
        "aprs_message_id": aprs_message_id,
        "callsign": str(station_settings.get("callsign") or "").strip().upper(),
        "ssid": str(station_settings.get("ssid") or "").strip(),
        "message_kind": "query",
        "addressee": str(addressee or "").strip().upper(),
        "path": str(path or "").strip(),
        "message_text": str(message_text or "").strip(),
        "trigger": str(trigger or "query-response").strip() or "query-response",
    }
    return _enqueue_generic_message_payload(payload, station_settings, scheduled_for=scheduled_for)


def enqueue_ack_job(
    addressee: str,
    ack_number: str,
    station_settings: dict[str, Any],
    *,
    path: str = "",
    trigger: str = "ack",
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    payload = {
        "callsign": str(station_settings.get("callsign") or "").strip().upper(),
        "ssid": str(station_settings.get("ssid") or "").strip(),
        "message_kind": "ack",
        "addressee": str(addressee or "").strip().upper(),
        "path": str(path or "").strip(),
        "message_text": f"ack{str(ack_number or '').strip().upper()}",
        "trigger": str(trigger or "ack").strip() or "ack",
    }
    return _enqueue_generic_message_payload(payload, station_settings, scheduled_for=scheduled_for)


def claim_next_outbound_job() -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, kind, interface_id, payload_json, status, scheduled_at, attempt_count
            FROM outbound_jobs
            WHERE status = ?
              AND scheduled_at <= ?
            ORDER BY
                CASE
                    WHEN kind = ? THEN 0
                    ELSE 1
                END ASC,
                scheduled_at ASC,
                id ASC
            LIMIT 1
            """,
            (OUTBOUND_STATUS_QUEUED, utc_now(), OUTBOUND_KIND_DIGI_TX),
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
               m.name AS interface_name, m.modem_type, m.device_path, m.baud_rate, m.enabled AS interface_enabled, m.band,
               m.tx_min_gap_seconds
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


def mark_outbound_job_skipped(job_id: int, reason: str) -> None:
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE outbound_jobs
            SET status = ?, sent_at = ?, last_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (OUTBOUND_STATUS_SENT, timestamp, str(reason or "").strip()[:500], timestamp, job_id),
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


def mark_outbound_job_cancelled(job_id: int) -> None:
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE outbound_jobs
            SET status = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            ("cancelled", timestamp, job_id, OUTBOUND_STATUS_QUEUED),
        )


def persist_outbound_frame(
    *,
    source: str,
    interface_id: int | None = None,
    band: str = "",
    line: str,
    port: str = "0",
    command: str = "TX",
    payload_hex: str = "",
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO traffic_frames(
                source, interface_id, direction, band, format, line, port, command, length, hex, created_at
            )
            VALUES (?, ?, 'tx', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                interface_id,
                str(band or "").strip(),
                "TNC2-TX",
                line,
                port,
                command,
                len(line.encode("utf-8")),
                payload_hex,
                utc_now(),
            ),
        )


def build_beacon_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    path = str(payload.get("beacon_path") or "").strip()
    info = _build_beacon_info(payload)
    header = f"{source}>{APRSBOX_DESTINATION}"
    if path:
        header = f"{header},{path}"
    return f"{header}:{info}"


def build_object_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    path = str(payload.get("path") or "").strip()
    info = _build_object_info(payload)
    header = f"{source}>{APRSBOX_DESTINATION}"
    if path:
        header = f"{header},{path}"
    return f"{header}:{info}"


def build_status_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    info = _build_status_info(payload)
    return f"{source}>{APRSBOX_DESTINATION}:{info}"


def build_message_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    path = str(payload.get("path") or "").strip()
    info = _build_message_info(payload)
    header = f"{source}>{APRSBOX_DESTINATION}"
    if path:
        header = f"{header},{path}"
    return f"{header}:{info}"


def build_wx_tnc2(payload: dict[str, Any]) -> str:
    source = _format_station_callsign(payload.get("callsign"), payload.get("ssid"))
    path = str(payload.get("path") or "").strip()
    info = _build_wx_info(payload)
    header = f"{source}>{APRSBOX_DESTINATION}"
    if path:
        header = f"{header},{path}"
    return f"{header}:{info}"


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
                addresses.append(
                    _encode_ax25_address(
                        item.rstrip("*"),
                        is_last=index == len(path_parts) - 1,
                        has_been_repeated=item.endswith("*"),
                    )
                )
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


def _normalize_symbol_overlay(value: Any, *, symbol_table: str) -> str | None:
    if symbol_table != "\\":
        return None
    text = str(value or "").strip().upper()
    if len(text) == 1 and ("0" <= text <= "9" or "A" <= text <= "Z"):
        return text
    return None


def _format_station_callsign(callsign: Any, ssid: Any) -> str:
    base = str(callsign or "").strip().upper()
    ssid_text = str(ssid or "").strip()
    if ssid_text == "0":
        ssid_text = ""
    return f"{base}-{ssid_text}" if ssid_text else base


def _build_beacon_info(payload: dict[str, Any]) -> str:
    latitude = _format_aprs_latitude(float(payload["latitude"]))
    longitude = _format_aprs_longitude(float(payload["longitude"]))
    symbol_table = _normalize_symbol_table(payload.get("symbol_table"))
    symbol_overlay = _normalize_symbol_overlay(payload.get("symbol_overlay"), symbol_table=symbol_table)
    symbol_table_for_frame = symbol_overlay or symbol_table
    symbol_code = _normalize_symbol_code(payload.get("symbol_code"))
    comment = str(payload.get("beacon_comment") or "").strip()
    return f"={latitude}{symbol_table_for_frame}{longitude}{symbol_code}{comment}"


def _build_object_info(payload: dict[str, Any]) -> str:
    name = str(payload.get("name") or "")[:9].ljust(9)
    state_marker = "*" if str(payload.get("state") or "live") == "live" else "_"
    timestamp = str(payload.get("object_timestamp") or _object_timestamp(str(payload.get("lifetime") or "temporary")))
    latitude = _format_aprs_latitude(float(payload["latitude"]))
    longitude = _format_aprs_longitude(float(payload["longitude"]))
    symbol_table = _normalize_symbol_table(payload.get("symbol_table"))
    symbol_overlay = _normalize_symbol_overlay(payload.get("symbol_overlay"), symbol_table=symbol_table)
    symbol_table_for_frame = symbol_overlay or symbol_table
    symbol_code = _normalize_symbol_code(payload.get("symbol_code"))
    comment = str(payload.get("comment") or "").strip()
    return f";{name}{state_marker}{timestamp}{latitude}{symbol_table_for_frame}{longitude}{symbol_code}{comment}"


def _build_status_info(payload: dict[str, Any]) -> str:
    return f">{str(payload.get('status_text') or '').strip()}"


def _build_message_info(payload: dict[str, Any]) -> str:
    addressee = resolve_message_addressee(payload)
    message_text = str(payload.get("message_text") or "").strip()
    message_number = str(payload.get("message_number") or "").strip().upper()
    if str(payload.get("message_kind") or "").strip() == "direct_message" and message_number:
        message_text = f"{message_text}{{{message_number}"
    return f":{addressee}:{message_text}"


def _build_wx_info(payload: dict[str, Any]) -> str:
    latitude = _format_aprs_latitude(float(payload["latitude"]))
    longitude = _format_aprs_longitude(float(payload["longitude"]))
    weather = payload.get("weather") or {}
    if not isinstance(weather, dict):
        raise ValueError("WX payload weather data is invalid.")
    wind_direction = _format_wx_required_three_digits(weather.get("wind_direction_deg"))
    wind_speed = _format_wx_required_three_digits(weather.get("wind_speed_mph"))
    temperature = _format_wx_temperature(weather.get("temperature_f"))

    parts = [f"={latitude}/{longitude}_{wind_direction}/{wind_speed}"]
    gust = _format_wx_optional_three_digits("g", weather.get("wind_gust_mph"))
    if gust:
        parts.append(gust)
    parts.append(temperature)

    optional_fields = (
        _format_wx_hundredths_inches("r", weather.get("rain_last_hour_in")),
        _format_wx_hundredths_inches("p", weather.get("rain_last_24h_in")),
        _format_wx_hundredths_inches("P", weather.get("rain_since_midnight_in")),
        _format_wx_humidity(weather.get("humidity_pct")),
        _format_wx_pressure(weather.get("pressure_hpa")),
        _format_wx_snow(weather.get("snow_last_24h_in")),
        _format_wx_luminosity(weather.get("luminosity_w_m2")),
        _format_wx_counter(weather.get("raw_rain_counter")),
        _format_wx_water_height("F", weather.get("water_height_ft")),
        _format_wx_water_height("f", weather.get("water_height_m")),
        _format_wx_voltage(weather.get("battery_volts")),
        _format_wx_radiation(weather.get("radiation_nsv_h")),
    )
    for field in optional_fields:
        if field:
            parts.append(field)
    return "".join(parts)


def resolve_message_addressee(payload: dict[str, Any]) -> str:
    message_kind = str(payload.get("message_kind") or "bulletin").strip()
    if message_kind in {"direct_message", "query", "ack"}:
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


def _encode_ax25_address(value: str, *, is_last: bool, has_been_repeated: bool = False) -> bytes:
    callsign, ssid = _split_callsign_ssid(value)
    padded = callsign.ljust(6)
    encoded = bytearray((ord(char) << 1) for char in padded[:6])
    control = 0x60 | ((ssid & 0x0F) << 1)
    if has_been_repeated:
        control |= 0x80
    if is_last:
        control |= 0x01
    encoded.append(control)
    return bytes(encoded)


def _split_callsign_ssid(value: str) -> tuple[str, int]:
    normalized = value.strip().upper()
    base, separator, ssid_text = normalized.partition("-")
    if not base or not _AX25_CALLSIGN_RE.fullmatch(base):
        raise ValueError("Invalid AX.25 callsign.")
    ssid = 0
    if separator:
        try:
            ssid = int(ssid_text)
        except ValueError as exc:
            raise ValueError("Invalid AX.25 SSID.") from exc
        if ssid < 0 or ssid > 15:
            raise ValueError("AX.25 SSID out of range.")
    return base, ssid


def _enqueue_generic_message_payload(
    payload: dict[str, Any],
    station_settings: dict[str, Any],
    *,
    scheduled_for: datetime | None = None,
) -> tuple[bool, str]:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    if not callsign:
        return False, "Callsign is required."
    target_modems, target_error = _resolve_station_target_modems(station_settings)
    if not target_modems:
        return False, str(target_error or "Interface is required.")
    scheduled_at = scheduled_for.astimezone(timezone.utc).replace(microsecond=0).isoformat() if scheduled_for else utc_now()
    job_ids = _enqueue_jobs_for_modems(
        kind=OUTBOUND_KIND_MESSAGE,
        payload=payload,
        modems=target_modems,
        scheduled_at=scheduled_at,
        aprs_message_id=payload.get("aprs_message_id"),
    )
    modem_names = ", ".join(str(modem["name"]) for modem in target_modems)
    if len(job_ids) == 1:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} message job #{job_ids[0]} for interface {modem_names}")
    else:
        log_event("INFO", "outbound", f"Queued {payload['trigger']} message jobs {job_ids} for interfaces: {modem_names}")
    return True, _format_queue_result("Message", job_ids)


def _coerce_wx_number(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is required for WX frame generation.") from exc
    if result != result:
        raise ValueError(f"{label} is required for WX frame generation.")
    return result


def _format_wx_required_three_digits(value: Any) -> str:
    if value in {None, ""}:
        return "..."
    number = int(round(float(value)))
    if number < 0:
        return "..."
    return f"{min(number, 999):03d}"


def _format_wx_optional_three_digits(prefix: str, value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = int(round(float(value)))
    if number < 0:
        return ""
    return f"{prefix}{min(number, 999):03d}"


def _format_wx_temperature(value: Any) -> str:
    if value in {None, ""}:
        return "t..."
    number = int(round(_coerce_wx_number(value, label="Temperature")))
    if number < -99:
        number = -99
    if number > 999:
        number = 999
    if number < 0:
        return f"t-{abs(number):02d}"
    return f"t{number:03d}"


def _format_wx_hundredths_inches(prefix: str, value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = int(round(float(value) * 100.0))
    if number < 0:
        return ""
    return f"{prefix}{min(number, 999):03d}"


def _format_wx_humidity(value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = int(round(float(value)))
    if number <= 0:
        return ""
    if number >= 100:
        return "h00"
    return f"h{number:02d}"


def _format_wx_pressure(value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = int(round(float(value) * 10.0))
    if number < 0:
        return ""
    return f"b{min(number, 99999):05d}"


def _format_wx_snow(value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = float(value)
    if number < 0:
        return ""
    if number < 10:
        return f"s{number:03.1f}"
    return f"s{min(int(round(number)), 999):03d}"


def _format_wx_luminosity(value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = int(round(float(value)))
    if number < 0:
        return ""
    if number <= 999:
        return f"L{number:03d}"
    return f"l{min(number - 1000, 999):03d}"


def _format_wx_counter(value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = int(round(float(value)))
    if number < 0:
        return ""
    return f"#{number % 1000:03d}"


def _format_wx_water_height(prefix: str, value: Any) -> str:
    if value in {None, ""}:
        return ""
    tenths = int(round(float(value) * 10.0))
    if tenths < -999:
        tenths = -999
    if tenths > 9999:
        tenths = 9999
    if tenths < 0:
        return f"{prefix}{tenths:04d}"
    return f"{prefix}{tenths:04d}"


def _format_wx_voltage(value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = int(round(float(value) * 10.0))
    if number < 0:
        return ""
    return f"V{min(number, 999):03d}"


def _format_wx_radiation(value: Any) -> str:
    if value in {None, ""}:
        return ""
    number = float(value)
    if number <= 0:
        return ""
    exponent = 0
    mantissa = number
    while mantissa >= 100 and exponent < 9:
        mantissa /= 10.0
        exponent += 1
    while mantissa < 10 and exponent > 0:
        mantissa *= 10.0
        exponent -= 1
    rounded_mantissa = int(round(mantissa))
    if rounded_mantissa >= 100 and exponent < 9:
        rounded_mantissa //= 10
        exponent += 1
    if rounded_mantissa < 10:
        rounded_mantissa = 10
    return f"X{rounded_mantissa:02d}{exponent}"
