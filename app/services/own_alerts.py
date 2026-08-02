from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.datetime_utils import format_display_datetime, parse_datetime
from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.services.alert_areas import (
    find_alarm_group_area_for_point,
    list_alarm_group_areas,
)
from app.services.aprs_warning_identity import (
    CAWF_CANCEL_EVENT_CODE,
    cawf_comment_capacity,
    format_aprs_expiry,
    generate_aprs_group_warning_parts,
    generate_cawf_alert_id,
    generate_cawf_message_id,
    normalize_cawf_comment,
)
from app.services.alerts import process_local_aprs_warning_frame
from app.services.content import get_station_settings
from app.services.outbound import build_message_tnc2, enqueue_alarm_group_frames
from app.services.tx_scope import TX_SCOPE_ALL_ACTIVE, normalize_tx_scope
from app.services.warning_groups import (
    get_warning_group_profile,
    list_supported_warning_group_profiles,
    list_supported_warning_groups,
    warning_event_is_supported,
    warning_event_options,
    warning_hazard_options,
    warning_level_options,
)


OWN_ALERT_VALIDITY_HOURS = (1, 3, 6, 12, 24, 48)
OWN_ALERT_REPEAT_INTERVALS = (15, 30, 60)
OWN_ALERT_STATUSES = ("active", "expired", "cancelled", "error")


def _utc_datetime(value: Any = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = parse_datetime(value) if value is not None else None
    if parsed is None:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _station_callsign(station_settings: Mapping[str, Any]) -> str:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    if ssid == "0":
        ssid = ""
    return f"{callsign}-{ssid}" if callsign and ssid else callsign


def own_alert_tx_availability(
    station_settings: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    station = dict(station_settings or get_station_settings())
    if not _station_callsign(station):
        return False, "Callsign is required."
    if not bool(station.get("tx_enabled")):
        return False, "Station TX is disabled."
    if bool(station.get("beacon_internal_tx")):
        return True, ""
    scope = normalize_tx_scope(station.get("beacon_tx_scope"))
    if scope == TX_SCOPE_ALL_ACTIVE:
        row = fetch_one(
            """
            SELECT 1
            FROM modems
            WHERE enabled = 1
              AND COALESCE(tx_blocked, 0) = 0
              AND modem_type IN ('TCP', 'SERIALL', 'SERIAL')
            LIMIT 1
            """
        )
        return (True, "") if row is not None else (
            False,
            "No active TX interface is available.",
        )
    interface_id = station.get("beacon_interface_id")
    if interface_id in {None, ""}:
        return False, "TX interface is required."
    row = fetch_one(
        """
        SELECT 1
        FROM modems
        WHERE id = ?
          AND enabled = 1
          AND COALESCE(tx_blocked, 0) = 0
          AND modem_type IN ('TCP', 'SERIALL', 'SERIAL')
        """,
        (interface_id,),
    )
    return (True, "") if row is not None else (
        False,
        "Selected TX interface is unavailable.",
    )


def _translated_event_options(profile_group: str) -> list[dict[str, Any]]:
    return [dict(option) for option in warning_event_options(profile_group)]


def get_own_alert_compose_context() -> dict[str, Any]:
    station = get_station_settings()
    tx_available, tx_error = own_alert_tx_availability(station)
    latitude = station.get("latitude")
    longitude = station.get("longitude")
    groups: list[dict[str, Any]] = []
    for profile in list_supported_warning_group_profiles():
        default_area = find_alarm_group_area_for_point(
            profile.group,
            latitude=latitude,
            longitude=longitude,
        )
        groups.append(
            {
                "group": profile.group,
                "protocol": profile.protocol,
                "area_encoding": profile.area_encoding,
                "event_options": _translated_event_options(profile.group),
                "hazard_options": warning_hazard_options(profile.group),
                "level_options": warning_level_options(),
                "default_area_code": (
                    str(default_area.get("code") or "") if default_area else ""
                ),
            }
        )
    try:
        position_known = (
            latitude not in {None, ""}
            and longitude not in {None, ""}
            and -90 <= float(latitude) <= 90
            and -180 <= float(longitude) <= 180
        )
    except (TypeError, ValueError):
        position_known = False
    return {
        "groups": groups,
        "validity_hours": list(OWN_ALERT_VALIDITY_HOURS),
        "repeat_intervals": list(OWN_ALERT_REPEAT_INTERVALS),
        "default_validity_hours": 24,
        "default_repeat_interval": 30,
        "station_position_known": position_known,
        "tx_available": tx_available,
        "tx_error": tx_error,
    }


def get_own_alert_area_options(group: Any) -> dict[str, Any]:
    normalized_group = str(group or "").strip().upper()
    if normalized_group not in set(list_supported_warning_groups()):
        raise ValueError("Unsupported alarm group.")
    station = get_station_settings()
    areas = list_alarm_group_areas(normalized_group)
    if not areas:
        raise ValueError("Alarm group GeoJSON is unavailable.")
    default_area = find_alarm_group_area_for_point(
        normalized_group,
        latitude=station.get("latitude"),
        longitude=station.get("longitude"),
    )
    return {
        "group": normalized_group,
        "areas": areas,
        "default_area_code": (
            str(default_area.get("code") or "") if default_area else ""
        ),
        "station_position_known": bool(
            station.get("latitude") not in {None, ""}
            and station.get("longitude") not in {None, ""}
        ),
    }


def _area_for_code(group: str, area_code: Any) -> dict[str, str] | None:
    normalized_code = str(area_code or "").strip().casefold()
    return next(
        (
            area
            for area in list_alarm_group_areas(group)
            if area["code"].casefold() == normalized_code
        ),
        None,
    )


def validate_own_alert_payload(
    payload: Mapping[str, Any],
    *,
    now: Any = None,
    require_tx: bool = True,
    preview_alert_id: str = "0000",
) -> dict[str, Any]:
    reference = _utc_datetime(now)
    group = str(payload.get("target_group") or payload.get("group") or "").strip().upper()
    if get_warning_group_profile(group) is None or group not in set(
        list_supported_warning_groups()
    ):
        raise ValueError("Unsupported alarm group.")
    area = _area_for_code(group, payload.get("area_code"))
    if area is None:
        raise ValueError("Area code does not exist in the alarm group GeoJSON.")
    event_code = str(payload.get("event_code") or "").strip().upper()
    if not event_code:
        event_family = str(
            payload.get("event_family")
            or payload.get("hazard_code")
            or payload.get("hazard")
            or ""
        ).strip().upper()
        try:
            severity_level = int(
                payload.get("severity_level")
                if payload.get("severity_level") is not None
                else payload.get("level")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Unsupported alarm severity level.") from exc
        event_code = f"{event_family}{severity_level}"
    if not warning_event_is_supported(group, event_code):
        raise ValueError("Unsupported alarm event type.")
    try:
        severity_level = int(event_code[-1])
    except (TypeError, ValueError) as exc:
        raise ValueError("Unsupported alarm severity level.") from exc
    event_family = event_code[:-1]
    try:
        validity_hours = int(payload.get("validity_hours"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Unsupported alarm validity.") from exc
    if validity_hours not in OWN_ALERT_VALIDITY_HOURS:
        raise ValueError("Unsupported alarm validity.")
    try:
        repeat_interval = int(payload.get("repeat_interval_minutes"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Unsupported alarm repeat interval.") from exc
    if repeat_interval not in OWN_ALERT_REPEAT_INTERVALS:
        raise ValueError("Unsupported alarm repeat interval.")
    station = get_station_settings()
    if require_tx:
        tx_available, tx_error = own_alert_tx_availability(station)
        if not tx_available:
            raise ValueError(tx_error or "No TX interface is available.")
    valid_until = reference + timedelta(hours=validity_hours)
    expiry = format_aprs_expiry(valid_until)
    comment = normalize_cawf_comment(payload.get("comment"))
    parts = generate_aprs_group_warning_parts(
        expiry=expiry,
        event_code=event_code,
        alert_id=preview_alert_id,
        area_code=area["code"],
        comment=comment,
    )
    capacity = cawf_comment_capacity(
        expiry=expiry,
        event_code=event_code,
        alert_id=preview_alert_id,
        area_code=area["code"],
    )
    path = str(station.get("beacon_path") or "").strip().upper()
    callsign = _station_callsign(station)
    technical_frames = [
        build_message_tnc2(
            {
                "callsign": callsign.partition("-")[0],
                "ssid": callsign.partition("-")[2],
                "message_kind": "alarm_group",
                "addressee": group,
                "path": path,
                "message_text": part["payload"],
            }
        )
        for part in parts
    ]
    return {
        "target_group": group,
        "area": area,
        "event_code": event_code,
        "event_family": event_family,
        "severity_level": severity_level,
        "validity_hours": validity_hours,
        "repeat_interval_minutes": repeat_interval,
        "comment": comment,
        "created_at": reference,
        "valid_until": valid_until,
        "expiry": expiry,
        "parts": parts,
        "parts_total": len(parts),
        "comment_capacity": capacity,
        "remaining_characters": capacity - len(normalize_cawf_comment(comment)),
        "technical_frames": technical_frames,
        "sender_callsign": callsign,
        "tx_path": path,
    }


def preview_own_alert(payload: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    validated = validate_own_alert_payload(
        payload,
        now=now,
        require_tx=False,
        preview_alert_id="0000",
    )
    return {
        "target_group": validated["target_group"],
        "area": validated["area"],
        "event_code": validated["event_code"],
        "event_family": validated["event_family"],
        "severity_level": validated["severity_level"],
        "valid_until": validated["valid_until"].isoformat(),
        "expiry": validated["expiry"],
        "repeat_interval_minutes": validated["repeat_interval_minutes"],
        "comment": validated["comment"],
        "parts_total": validated["parts_total"],
        "remaining_characters": validated["remaining_characters"],
        "technical_frames": validated["technical_frames"],
    }


def _insert_own_alert(validated: Mapping[str, Any]) -> tuple[int, str, list[str]]:
    for _ in range(32):
        alert_id = generate_cawf_alert_id()
        provisional_parts = generate_aprs_group_warning_parts(
            expiry=validated["expiry"],
            event_code=validated["event_code"],
            alert_id=alert_id,
            area_code=validated["area"]["code"],
            comment=validated["comment"],
        )
        message_ids: list[str] = []
        while len(message_ids) < len(provisional_parts):
            candidate = generate_cawf_message_id()
            if candidate not in message_ids:
                message_ids.append(candidate)
        now_text = validated["created_at"].isoformat()
        try:
            with get_connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO own_aprs_alerts(
                        alert_id, sender_callsign, target_group,
                        area_code, area_name, area_parent,
                        event_code, comment, created_at, valid_until,
                        repeat_interval_minutes, next_transmission_at,
                        last_transmission_at, transmission_count, status,
                        cancelled_at, message_ids_json, cancel_message_id,
                        parts_total, tx_path, last_error, updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL,
                        NULL, 0, 'active', NULL, ?, NULL, ?, ?, NULL, ?
                    )
                    """,
                    (
                        alert_id,
                        validated["sender_callsign"],
                        validated["target_group"],
                        validated["area"]["code"],
                        validated["area"]["name"],
                        validated["area"].get("parent", ""),
                        validated["event_code"],
                        validated["comment"],
                        now_text,
                        validated["valid_until"].isoformat(),
                        validated["repeat_interval_minutes"],
                        json.dumps(message_ids, ensure_ascii=True, separators=(",", ":")),
                        len(message_ids),
                        validated["tx_path"],
                        now_text,
                    ),
                )
                return int(cursor.lastrowid), alert_id, message_ids
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError("Could not allocate a unique CAWF alert ID.")


def _row_message_ids(row: Mapping[str, Any]) -> list[str]:
    try:
        values = json.loads(str(row.get("message_ids_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        values = []
    return [str(value).strip().upper() for value in values if str(value).strip()]


def _register_tx_jobs(
    *,
    own_alert_id: int,
    job_ids: list[int],
    dispatch_token: str,
    dispatch_kind: str,
    created_at: str,
) -> None:
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO own_aprs_alert_tx_jobs(
                own_alert_id, outbound_job_id, dispatch_token, dispatch_kind, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (own_alert_id, job_id, dispatch_token, dispatch_kind, created_at)
                for job_id in job_ids
            ],
        )


def _record_local_alert_dispatch(
    frames: list[dict[str, Any]],
    *,
    sender_callsign: str,
    target_group: str,
    path: str,
    occurred_at: datetime,
) -> None:
    callsign, separator, ssid = str(sender_callsign or "").strip().upper().partition("-")
    for frame in frames:
        line = build_message_tnc2(
            {
                "callsign": callsign,
                "ssid": ssid if separator else "",
                "message_kind": "alarm_group",
                "addressee": target_group,
                "path": path,
                "message_text": str(frame.get("payload") or ""),
            }
        )
        result = process_local_aprs_warning_frame(
            line,
            timestamp=occurred_at,
        )
        if result is None:
            raise RuntimeError("Locally generated CAWF frame was not accepted as an alarm.")


def _dispatch_own_alert(
    row: Mapping[str, Any],
    *,
    now: datetime,
    trigger: str,
    cancel: bool = False,
    next_transmission_at: datetime | None = None,
) -> tuple[bool, str, list[str]]:
    def record_error(message: str) -> tuple[bool, str, list[str]]:
        resolved_next = None
        if not cancel:
            resolved_next = next_transmission_at or (
                now + timedelta(minutes=int(row["repeat_interval_minutes"]))
            )
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE own_aprs_alerts
                SET status = 'error', last_error = ?,
                    next_transmission_at = ?,
                    cancelled_at = CASE
                        WHEN ? = 1 THEN COALESCE(cancelled_at, ?)
                        ELSE cancelled_at
                    END,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(message)[:500],
                    resolved_next.isoformat() if resolved_next is not None else None,
                    1 if cancel else 0,
                    now.isoformat(),
                    now.isoformat(),
                    int(row["id"]),
                ),
            )
        return False, message, []

    station = get_station_settings()
    current_sender = _station_callsign(station)
    stored_sender = str(row.get("sender_callsign") or "").strip().upper()
    if current_sender != stored_sender:
        return record_error(
            "Configured station callsign no longer matches the alert sender."
        )
    tx_available, tx_error = own_alert_tx_availability(station)
    if not tx_available:
        return record_error(tx_error or "No TX interface is available.")
    valid_until = _utc_datetime(row.get("valid_until"))
    if not cancel and valid_until <= now:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE own_aprs_alerts
                SET status = 'expired', next_transmission_at = NULL,
                    last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), int(row["id"])),
            )
        return False, "Alarm has expired.", []

    if cancel:
        cancel_message_id = str(row.get("cancel_message_id") or "").strip().upper()
        if not cancel_message_id:
            used_message_ids = set(_row_message_ids(row))
            while not cancel_message_id or cancel_message_id in used_message_ids:
                cancel_message_id = generate_cawf_message_id()
        frames = generate_aprs_group_warning_parts(
            expiry=format_aprs_expiry(valid_until),
            event_code=CAWF_CANCEL_EVENT_CODE,
            alert_id=row["alert_id"],
            area_code=row["area_code"],
            message_ids=[cancel_message_id],
        )
    else:
        cancel_message_id = ""
        frames = generate_aprs_group_warning_parts(
            expiry=format_aprs_expiry(valid_until),
            event_code=row["event_code"],
            alert_id=row["alert_id"],
            area_code=row["area_code"],
            comment=row.get("comment", ""),
            message_ids=_row_message_ids(row),
        )
    dispatch_token = uuid.uuid4().hex
    success, message, job_ids = enqueue_alarm_group_frames(
        frames,
        station,
        sender_callsign=stored_sender,
        target_group=str(row["target_group"]),
        path=str(row.get("tx_path") or ""),
        own_alert_id=int(row["id"]),
        dispatch_token=dispatch_token,
        trigger=trigger,
        scheduled_for=now,
    )
    now_text = now.isoformat()
    if success:
        try:
            _record_local_alert_dispatch(
                frames,
                sender_callsign=stored_sender,
                target_group=str(row["target_group"]),
                path=str(row.get("tx_path") or ""),
                occurred_at=now,
            )
        except Exception as exc:
            log_event(
                "WARNING",
                "alerts",
                (
                    f"Could not register own APRS alarm {row['alert_id']} in the alert list: "
                    f"{str(exc).strip() or exc.__class__.__name__}"
                ),
            )
        _register_tx_jobs(
            own_alert_id=int(row["id"]),
            job_ids=job_ids,
            dispatch_token=dispatch_token,
            dispatch_kind="cancel" if cancel else "alert",
            created_at=now_text,
        )
        with get_connection() as connection:
            if cancel:
                connection.execute(
                    """
                    UPDATE own_aprs_alerts
                    SET status = 'cancelled', cancelled_at = ?,
                        next_transmission_at = NULL, cancel_message_id = ?,
                        last_error = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (now_text, cancel_message_id, now_text, int(row["id"])),
                )
            else:
                resolved_next = next_transmission_at or (
                    now + timedelta(minutes=int(row["repeat_interval_minutes"]))
                )
                connection.execute(
                    """
                    UPDATE own_aprs_alerts
                    SET status = 'active', last_transmission_at = ?,
                        next_transmission_at = ?,
                        transmission_count = transmission_count + 1,
                        last_error = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (now_text, resolved_next.isoformat(), now_text, int(row["id"])),
                )
        return True, message, [str(frame["payload"]) for frame in frames]

    return record_error(message)


def create_own_alert(payload: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    reference = _utc_datetime(now)
    validated = validate_own_alert_payload(payload, now=reference)
    own_alert_id, logical_alert_id, message_ids = _insert_own_alert(validated)
    row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (own_alert_id,))
    if row is None:
        raise RuntimeError("Own alarm could not be loaded after creation.")
    success, message, frames = _dispatch_own_alert(
        dict(row),
        now=reference,
        trigger="manual-alert-create",
    )
    if not success:
        raise ValueError(message)
    log_event(
        "INFO",
        "alerts",
        f"Created own APRS alarm {logical_alert_id} for {validated['target_group']}.",
    )
    return {
        "id": own_alert_id,
        "alert_id": logical_alert_id,
        "message_ids": message_ids,
        "parts_total": len(frames),
        "frames": frames,
        "status": "active",
        "message": message,
    }


def expire_own_alerts(*, now: Any = None) -> int:
    timestamp = _utc_datetime(now).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE own_aprs_alerts
            SET status = 'expired', next_transmission_at = NULL,
                updated_at = ?
            WHERE status IN ('active', 'error')
              AND julianday(valid_until) <= julianday(?)
            """,
            (timestamp, timestamp),
        )
        return max(0, int(cursor.rowcount or 0))


def _serialize_own_alert(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.update(
        {
            "id": int(item["id"]),
            "repeat_interval_minutes": int(item["repeat_interval_minutes"]),
            "transmission_count": int(item.get("transmission_count") or 0),
            "parts_total": int(item.get("parts_total") or 1),
            "created_label": format_display_datetime(item.get("created_at")),
            "valid_until_label": format_display_datetime(item.get("valid_until")),
            "next_transmission_label": (
                format_display_datetime(item.get("next_transmission_at"))
                if item.get("next_transmission_at")
                else ""
            ),
            "last_transmission_label": (
                format_display_datetime(item.get("last_transmission_at"))
                if item.get("last_transmission_at")
                else ""
            ),
        }
    )
    item.pop("message_ids_json", None)
    return item


def list_active_own_alerts(*, now: Any = None) -> list[dict[str, Any]]:
    expire_own_alerts(now=now)
    return [
        _serialize_own_alert(row)
        for row in fetch_all(
            """
            SELECT *
            FROM own_aprs_alerts
            WHERE status IN ('active', 'error')
            ORDER BY created_at DESC, id DESC
            """
        )
    ]


def get_own_alert(own_alert_id: int) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (own_alert_id,))
    return _serialize_own_alert(row) if row is not None else None


def send_own_alert_now(own_alert_id: int, *, now: Any = None) -> tuple[bool, str]:
    reference = _utc_datetime(now)
    expire_own_alerts(now=reference)
    row = fetch_one(
        """
        SELECT * FROM own_aprs_alerts
        WHERE id = ? AND status IN ('active', 'error') AND cancelled_at IS NULL
        """,
        (own_alert_id,),
    )
    if row is None:
        return False, "Active own alarm not found."
    success, message, _ = _dispatch_own_alert(
        dict(row),
        now=reference,
        trigger="manual-alert-send-now",
        next_transmission_at=(
            reference + timedelta(minutes=int(row["repeat_interval_minutes"]))
        ),
    )
    return success, message


def cancel_own_alert(
    own_alert_id: int,
    *,
    sender_callsign: str | None = None,
    now: Any = None,
) -> tuple[bool, str]:
    reference = _utc_datetime(now)
    row = fetch_one(
        "SELECT * FROM own_aprs_alerts WHERE id = ? AND status IN ('active', 'error')",
        (own_alert_id,),
    )
    if row is None:
        return False, "Active own alarm not found."
    expected_sender = str(row["sender_callsign"] or "").strip().upper()
    actual_sender = str(sender_callsign or _station_callsign(get_station_settings())).strip().upper()
    if actual_sender != expected_sender:
        return False, "Alarm sender does not match the configured station callsign."
    success, message, _ = _dispatch_own_alert(
        dict(row),
        now=reference,
        trigger="manual-alert-cancel",
        cancel=True,
    )
    if success:
        log_event(
            "INFO",
            "alerts",
            f"Cancelled own APRS alarm {row['alert_id']} for {row['target_group']}.",
        )
    return success, message


def cancel_station_aprs_alert(
    alert_id: int,
    *,
    now: Any = None,
) -> tuple[bool, str]:
    """Cancel a CAWF alert only when its source is the configured station."""

    reference = _utc_datetime(now)
    alert = fetch_one(
        """
        SELECT *
        FROM aprs_alerts
        WHERE id = ?
          AND superseded_by_alert_id IS NULL
          AND is_active = 1
          AND alarm_group IS NOT NULL
        """,
        (alert_id,),
    )
    if alert is None:
        return False, "Active APRS alarm not found."

    station = get_station_settings()
    current_sender = _station_callsign(station)
    alert_sender = str(alert["source_callsign"] or "").strip().upper()
    if not current_sender or current_sender != alert_sender:
        return False, "Alarm sender does not match the configured station callsign."

    target_group = str(alert["alarm_group"] or "").strip().upper()
    logical_alert_id = str(alert["logical_alert_id"] or "").strip().upper()
    area_code = str(alert["area_code"] or "").strip().upper()
    if not target_group or not logical_alert_id or not area_code:
        return False, "Alarm does not contain the CAWF identity required for cancellation."

    own_alert = fetch_one(
        """
        SELECT id
        FROM own_aprs_alerts
        WHERE sender_callsign = ? COLLATE NOCASE
          AND target_group = ? COLLATE NOCASE
          AND alert_id = ? COLLATE NOCASE
          AND status IN ('active', 'error')
        ORDER BY id DESC
        LIMIT 1
        """,
        (alert_sender, target_group, logical_alert_id),
    )
    if own_alert is not None:
        return cancel_own_alert(
            int(own_alert["id"]),
            sender_callsign=current_sender,
            now=reference,
        )

    tx_available, tx_error = own_alert_tx_availability(station)
    if not tx_available:
        return False, tx_error or "No TX interface is available."
    expiry = str(alert["expiry"] or "").strip()
    if not expiry:
        expires_at = parse_datetime(alert["expires_at"])
        if expires_at is None:
            return False, "Alarm expiry is unavailable."
        expiry = format_aprs_expiry(expires_at)
    try:
        cancel_frames = generate_aprs_group_warning_parts(
            expiry=expiry,
            event_code=CAWF_CANCEL_EVENT_CODE,
            alert_id=logical_alert_id,
            area_code=area_code,
        )
    except ValueError as exc:
        return False, str(exc)

    path = str(station.get("beacon_path") or "").strip().upper()
    success, message, _job_ids = enqueue_alarm_group_frames(
        cancel_frames,
        station,
        sender_callsign=current_sender,
        target_group=target_group,
        path=path,
        own_alert_id=None,
        dispatch_token=uuid.uuid4().hex,
        trigger="manual-alert-cancel",
        scheduled_for=reference,
    )
    if not success:
        return False, message
    try:
        _record_local_alert_dispatch(
            cancel_frames,
            sender_callsign=current_sender,
            target_group=target_group,
            path=path,
            occurred_at=reference,
        )
    except Exception as exc:
        log_event(
            "WARNING",
            "alerts",
            (
                f"Could not register CAWF cancellation for alert #{alert_id}: "
                f"{str(exc).strip() or exc.__class__.__name__}"
            ),
        )
    log_event(
        "INFO",
        "alerts",
        f"Cancelled APRS alarm {logical_alert_id} for {target_group}.",
    )
    return True, message


def restore_own_alert_schedules(*, now: Any = None) -> int:
    reference = _utc_datetime(now)
    expire_own_alerts(now=reference)
    changed = 0
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, repeat_interval_minutes, next_transmission_at
            FROM own_aprs_alerts
            WHERE status IN ('active', 'error')
              AND cancelled_at IS NULL
            """
        ).fetchall()
        for row in rows:
            next_at = _utc_datetime(row["next_transmission_at"] or reference)
            interval = timedelta(minutes=int(row["repeat_interval_minutes"]))
            while next_at <= reference:
                next_at += interval
            if str(row["next_transmission_at"] or "") != next_at.isoformat():
                connection.execute(
                    """
                    UPDATE own_aprs_alerts
                    SET next_transmission_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (next_at.isoformat(), reference.isoformat(), int(row["id"])),
                )
                changed += 1
    return changed


def dispatch_due_own_alerts(*, now: Any = None) -> int:
    reference = _utc_datetime(now)
    expire_own_alerts(now=reference)
    rows = fetch_all(
        """
        SELECT *
        FROM own_aprs_alerts
        WHERE status IN ('active', 'error')
          AND cancelled_at IS NULL
          AND next_transmission_at IS NOT NULL
          AND julianday(next_transmission_at) <= julianday(?)
        ORDER BY next_transmission_at ASC, id ASC
        """,
        (reference.isoformat(),),
    )
    dispatched = 0
    for raw_row in rows:
        row = dict(raw_row)
        scheduled = _utc_datetime(row["next_transmission_at"])
        interval = timedelta(minutes=int(row["repeat_interval_minutes"]))
        next_at = scheduled + interval
        while next_at <= reference:
            next_at += interval
        success, _, _ = _dispatch_own_alert(
            row,
            now=reference,
            trigger="scheduled-alert-repeat",
            next_transmission_at=next_at,
        )
        if success:
            dispatched += 1
    return dispatched


def reconcile_own_alert_job(
    outbound_job_id: int,
    *,
    successful: bool,
    error: str = "",
) -> None:
    relation = fetch_one(
        """
        SELECT own_alert_id, dispatch_token, dispatch_kind
        FROM own_aprs_alert_tx_jobs
        WHERE outbound_job_id = ?
        """,
        (outbound_job_id,),
    )
    if relation is None:
        return
    timestamp = utc_now()
    if not successful:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE own_aprs_alerts
                SET status = CASE
                        WHEN ? = 'alert' AND status = 'cancelled' THEN status
                        ELSE 'error'
                    END,
                    next_transmission_at = CASE
                        WHEN ? = 'cancel' THEN NULL
                        ELSE next_transmission_at
                    END,
                    last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(relation["dispatch_kind"]),
                    str(relation["dispatch_kind"]),
                    str(error or "Transmission failed.")[:500],
                    timestamp,
                    int(relation["own_alert_id"]),
                ),
            )
            if str(relation["dispatch_kind"]) == "cancel":
                connection.execute(
                    """
                    UPDATE aprs_alerts
                    SET is_active = 1,
                        cancelled_at = NULL,
                        updated_at = ?
                    WHERE superseded_by_alert_id IS NULL
                      AND (
                            expires_at IS NULL
                            OR julianday(expires_at) > julianday(?)
                      )
                      AND (
                            valid_until_utc IS NULL
                            OR julianday(valid_until_utc) > julianday(?)
                      )
                      AND EXISTS (
                            SELECT 1
                            FROM own_aprs_alerts AS own
                            WHERE own.id = ?
                              AND own.sender_callsign = aprs_alerts.source_callsign COLLATE NOCASE
                              AND own.target_group = aprs_alerts.alarm_group COLLATE NOCASE
                              AND own.alert_id = aprs_alerts.logical_alert_id COLLATE NOCASE
                      )
                    """,
                    (
                        timestamp,
                        timestamp,
                        timestamp,
                        int(relation["own_alert_id"]),
                    ),
                )
        return
    jobs = fetch_all(
        """
        SELECT outbound.status
        FROM own_aprs_alert_tx_jobs AS relations
        JOIN outbound_jobs AS outbound ON outbound.id = relations.outbound_job_id
        WHERE relations.dispatch_token = ?
        """,
        (relation["dispatch_token"],),
    )
    if jobs and all(str(job["status"]) == "sent" for job in jobs):
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE own_aprs_alerts
                SET status = CASE
                        WHEN ? = 'cancel' THEN 'cancelled'
                        WHEN status = 'cancelled' THEN status
                        ELSE 'active'
                    END,
                    last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(relation["dispatch_kind"]),
                    timestamp,
                    int(relation["own_alert_id"]),
                ),
            )
