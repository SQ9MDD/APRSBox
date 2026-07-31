from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.datetime_utils import format_display_datetime, parse_datetime
from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
from app.services.alarm_groups import (
    alarm_event_meets_category_threshold,
    get_aprs_alarm_enabled,
    get_aprs_alarm_groups,
)
from app.services.alert_event_icons import resolve_alert_event_icon
from app.services.aprs_warning_identity import (
    build_aprs_alert_identity_key,
    build_aprs_alert_part_identity_key,
    normalize_warning_area_codes,
    parse_aprs_group_warning_content,
    resolve_aprs_expiry_utc,
)
from app.services.content import (
    build_emergency_frame_data,
    build_station_detail_href,
    parse_tnc2_frame,
)


ALERT_PAGE_SIZE = 25
ALERT_MUTE_DURATIONS_HOURS: dict[str, int] = {
    "1h": 1,
    "4h": 4,
    "24h": 24,
}


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalized_source_callsign(parsed: Mapping[str, Any]) -> str:
    return str(parsed.get("logical_source_key") or parsed.get("source_key") or "").strip().upper()


def normalize_alert_area_codes(values: Any) -> list[str]:
    return normalize_warning_area_codes(values)


def extract_aprs_warning_area_codes(raw_content: Any) -> list[str]:
    """Extract only the area-code fields from the current warning envelope.

    Timestamp, event type, severity, and validity remain intentionally opaque.
    The generic alert intake also accepts explicit ``area_codes`` so a future
    parser or Alert Hub adapter can replace this small transport-level helper.
    """

    return list(parse_aprs_group_warning_content(raw_content)["area_codes"])


def _stored_area_codes(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return normalize_alert_area_codes(value)


def _is_muted(row: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    if bool(int(row.get("muted_indefinitely") or 0)):
        return True
    muted_until = parse_datetime(row.get("muted_until"))
    if muted_until is None:
        return False
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return muted_until.astimezone(timezone.utc) > reference.astimezone(timezone.utc)


def _integer_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalized_utc_datetime(value: Any = None) -> datetime:
    parsed = parse_datetime(value) if value is not None else None
    if parsed is None:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def expire_aprs_alerts(
    *,
    now: datetime | str | None = None,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Deactivate expired alerts while preserving their traffic frames."""

    timestamp = _normalized_utc_datetime(now).replace(microsecond=0).isoformat()

    def expire(target: sqlite3.Connection) -> int:
        cursor = target.execute(
            """
            UPDATE aprs_alerts
            SET is_active = 0,
                updated_at = ?
            WHERE superseded_by_alert_id IS NULL
              AND is_active = 1
              AND (
                    (
                        expires_at IS NOT NULL
                        AND julianday(expires_at) <= julianday(?)
                    )
                    OR (
                        valid_until_utc IS NOT NULL
                        AND julianday(valid_until_utc) <= julianday(?)
                    )
              )
            """,
            (timestamp, timestamp, timestamp),
        )
        return max(0, int(cursor.rowcount or 0))

    if connection is not None:
        return expire(connection)
    with get_connection() as managed_connection:
        return expire(managed_connection)


def _recalculate_logical_alert(
    connection: sqlite3.Connection,
    *,
    alert_id: int,
    updated_at: str,
) -> None:
    parts = connection.execute(
        """
        SELECT part_number, parts_total, area_codes_json
        FROM aprs_alert_parts
        WHERE alert_id = ?
        ORDER BY
            CASE WHEN part_number IS NULL THEN 1 ELSE 0 END,
            part_number ASC,
            id ASC
        """,
        (alert_id,),
    ).fetchall()

    area_codes: list[str] = []
    seen_area_codes: set[str] = set()
    received_part_numbers: set[int] = set()
    declared_totals: list[int] = []
    for part in parts:
        part_number = _integer_or_none(part["part_number"])
        parts_total = _integer_or_none(part["parts_total"])
        if part_number is not None and part_number >= 1:
            received_part_numbers.add(part_number)
        if parts_total is not None and parts_total >= 1:
            declared_totals.append(parts_total)
        for area_code in _stored_area_codes(part["area_codes_json"]):
            comparison_key = area_code.casefold()
            if comparison_key in seen_area_codes:
                continue
            seen_area_codes.add(comparison_key)
            area_codes.append(area_code)

    parts_total = max(declared_totals) if declared_totals else None
    valid_part_numbers = {
        part_number
        for part_number in received_part_numbers
        if parts_total is None or part_number <= parts_total
    }
    complete = bool(parts_total) and set(range(1, parts_total + 1)).issubset(
        valid_part_numbers
    )
    connection.execute(
        """
        UPDATE aprs_alerts
        SET area_codes_json = ?,
            area_code = ?,
            received_parts = ?,
            parts_total = ?,
            completion_status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            json.dumps(area_codes, ensure_ascii=False, separators=(",", ":")),
            area_codes[0] if area_codes else None,
            len(valid_part_numbers),
            parts_total,
            "complete" if complete else "incomplete",
            updated_at,
            alert_id,
        ),
    )


def accept_aprs_warning_frame(
    connection: sqlite3.Connection,
    *,
    frame_id: int,
    parsed: Mapping[str, Any],
    frame_row: Mapping[str, Any],
    warning: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Store a warning in the existing alert model and relate its source frame.

    The warning mapping is intentionally format-neutral so later stages can
    populate parsed event type, severity, validity, areas, and external-source
    metadata without adding a second alert intake path.
    """

    source_callsign = str(
        warning.get("source_callsign")
        or _normalized_source_callsign(parsed)
    ).strip().upper()
    if not source_callsign:
        return None

    received_at = str(
        warning.get("received_at")
        or frame_row.get("created_at")
        or utc_now()
    )
    alert_type = str(
        warning.get("alert_type")
        or warning.get("warning_type")
        or "APRS WARNING"
    ).strip().upper()
    message = str(
        warning.get("raw_content")
        if warning.get("raw_content") is not None
        else warning.get("message") or ""
    )
    latitude = _float_or_none(warning.get("latitude"))
    longitude = _float_or_none(warning.get("longitude"))
    warning_kind = str(warning.get("warning_kind") or "aprs_warning").strip().lower()
    emergency_notification = bool(warning.get("emergency_notification"))
    alarm_group = str(warning.get("alarm_group") or "").strip().upper() or None
    parsed_warning: Mapping[str, Any] = (
        parse_aprs_group_warning_content(message)
        if alarm_group is not None
        else {
            "expiry": "",
            "event_code": "",
            "severity_level": None,
            "logical_alert_id": "",
            "part_number": None,
            "parts_total": None,
            "area_code": "",
            "area_codes": [],
            "message_id": "",
        }
    )
    expiry = str(
        warning.get("expiry")
        if warning.get("expiry") is not None
        else parsed_warning["expiry"]
    ).strip()
    resolved_expiry = resolve_aprs_expiry_utc(expiry, received_at)
    expires_at = str(warning.get("expires_at") or "").strip() or (
        resolved_expiry.replace(microsecond=0).isoformat()
        if resolved_expiry is not None
        else None
    )
    event_code = str(
        warning.get("event_code")
        if warning.get("event_code") is not None
        else parsed_warning["event_code"]
    ).strip()
    message_id = str(
        warning.get("message_id")
        if warning.get("message_id") is not None
        else parsed_warning["message_id"]
    ).strip()
    logical_alert_id = str(
        warning.get("logical_alert_id")
        if warning.get("logical_alert_id") is not None
        else parsed_warning["logical_alert_id"]
    ).strip().upper().removeprefix("@")
    severity_level = _integer_or_none(
        warning.get("severity_level")
        if warning.get("severity_level") is not None
        else parsed_warning["severity_level"]
    )
    part_number = _integer_or_none(
        warning.get("part_number")
        if warning.get("part_number") is not None
        else parsed_warning["part_number"]
    )
    parts_total = _integer_or_none(
        warning.get("parts_total")
        if warning.get("parts_total") is not None
        else parsed_warning["parts_total"]
    )
    if alarm_group is not None and (part_number is None or parts_total is None):
        part_number = 1
        parts_total = 1
    area_codes = normalize_alert_area_codes(
        warning.get("area_codes")
        if warning.get("area_codes") is not None
        else parsed_warning["area_codes"]
    )
    area_code = str(
        warning.get("area_code")
        if warning.get("area_code") is not None
        else (area_codes[0] if area_codes else parsed_warning["area_code"])
    ).strip()
    area_codes_json = json.dumps(area_codes, ensure_ascii=False, separators=(",", ":"))
    is_active = 1 if bool(warning.get("is_active", True)) else 0
    received_datetime = parse_datetime(received_at)
    expires_datetime = parse_datetime(expires_at)
    if (
        is_active
        and received_datetime is not None
        and expires_datetime is not None
        and expires_datetime.astimezone(timezone.utc)
        <= received_datetime.astimezone(timezone.utc)
    ):
        is_active = 0
    valid_until_utc = str(warning.get("valid_until_utc") or "").strip() or None
    identity_key = str(warning.get("identity_key") or "").strip() or build_aprs_alert_identity_key(
        source_callsign=source_callsign,
        alarm_group=alarm_group,
        logical_alert_id=logical_alert_id,
        message_id=message_id,
        raw_content=message,
    )
    part_identity_key = (
        build_aprs_alert_part_identity_key(
            source_callsign=source_callsign,
            alarm_group=alarm_group,
            message_id=message_id,
            raw_content=message,
        )
        if alarm_group is not None
        else None
    )
    existing_part = (
        connection.execute(
            """
            SELECT parts.id, parts.alert_id, alerts.identity_key
            FROM aprs_alert_parts AS parts
            JOIN aprs_alerts AS alerts ON alerts.id = parts.alert_id
            WHERE parts.part_identity_key = ?
            """,
            (part_identity_key,),
        ).fetchone()
        if part_identity_key is not None
        else None
    )

    created = False
    if existing_part is None:
        insert_cursor = connection.execute(
            """
            INSERT INTO aprs_alerts(
                identity_key, source_callsign, alert_type, message,
                alarm_group, area_codes_json, is_active, valid_until_utc,
                expiry, expires_at, event_code, area_code, message_id,
                logical_alert_id, severity_level,
                received_parts, parts_total, completion_status,
                first_seen_at, last_seen_at, frame_count,
                initial_frame_id, last_frame_id,
                latitude, longitude,
                muted_until, muted_indefinitely,
                created_at, updated_at
            )
            VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?,
                0, ?, 'incomplete',
                ?, ?, 1,
                ?, ?,
                ?, ?,
                NULL, 0,
                ?, ?
            )
            ON CONFLICT(identity_key) DO NOTHING
            """,
            (
                identity_key,
                source_callsign,
                alert_type,
                message,
                alarm_group,
                area_codes_json,
                is_active,
                valid_until_utc,
                expiry or None,
                expires_at,
                event_code or None,
                area_code or None,
                message_id or None,
                logical_alert_id or None,
                severity_level,
                parts_total,
                received_at,
                received_at,
                frame_id,
                frame_id,
                latitude,
                longitude,
                received_at,
                received_at,
            ),
        )
        created = int(insert_cursor.rowcount or 0) == 1
        alert_row = connection.execute(
            "SELECT id, identity_key FROM aprs_alerts WHERE identity_key = ?",
            (identity_key,),
        ).fetchone()
    else:
        alert_row = existing_part
        identity_key = str(existing_part["identity_key"])
    if alert_row is None:
        raise RuntimeError(f"APRS warning upsert failed for {source_callsign}")
    alert_id = int(alert_row["alert_id"] if existing_part is not None else alert_row["id"])

    part_id: int | None = None
    if part_identity_key is not None:
        part_cursor = connection.execute(
            """
            INSERT INTO aprs_alert_parts(
                alert_id, part_identity_key,
                part_number, parts_total, aprs_message_id,
                area_codes_json, raw_message,
                first_received_at, last_received_at, received_count,
                initial_frame_id, last_frame_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(part_identity_key) DO NOTHING
            """,
            (
                alert_id,
                part_identity_key,
                part_number,
                parts_total,
                message_id or None,
                area_codes_json,
                message,
                received_at,
                received_at,
                frame_id,
                frame_id,
                received_at,
                received_at,
            ),
        )
        part_created = int(part_cursor.rowcount or 0) == 1
        part_row = connection.execute(
            """
            SELECT id, alert_id
            FROM aprs_alert_parts
            WHERE part_identity_key = ?
            """,
            (part_identity_key,),
        ).fetchone()
        if part_row is None:
            raise RuntimeError(f"APRS warning part upsert failed for {source_callsign}")
        part_id = int(part_row["id"])
        alert_id = int(part_row["alert_id"])
        if not part_created:
            created = False
            connection.execute(
                """
                UPDATE aprs_alert_parts
                SET part_number = ?,
                    parts_total = ?,
                    aprs_message_id = ?,
                    area_codes_json = ?,
                    raw_message = ?,
                    last_received_at = ?,
                    received_count = received_count + 1,
                    last_frame_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    part_number,
                    parts_total,
                    message_id or None,
                    area_codes_json,
                    message,
                    received_at,
                    frame_id,
                    received_at,
                    part_id,
                ),
            )

    relation_cursor = connection.execute(
        """
        INSERT INTO aprs_alert_frames(alert_id, frame_id, part_id, received_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(frame_id) DO NOTHING
        """,
        (alert_id, frame_id, part_id, received_at),
    )
    relation_created = int(relation_cursor.rowcount or 0) == 1

    if not created:
        connection.execute(
            """
            UPDATE aprs_alerts
            SET alert_type = ?,
                message = ?,
                alarm_group = ?,
                area_codes_json = ?,
                is_active = ?,
                valid_until_utc = ?,
                expiry = COALESCE(?, expiry),
                expires_at = COALESCE(?, expires_at),
                event_code = ?,
                area_code = ?,
                message_id = ?,
                logical_alert_id = COALESCE(NULLIF(?, ''), logical_alert_id),
                severity_level = COALESCE(?, severity_level),
                last_seen_at = ?,
                frame_count = frame_count + ?,
                last_frame_id = ?,
                latitude = ?,
                longitude = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                alert_type,
                message,
                alarm_group,
                area_codes_json,
                is_active,
                valid_until_utc,
                expiry or None,
                expires_at,
                event_code or None,
                area_code or None,
                message_id or None,
                logical_alert_id,
                severity_level,
                received_at,
                1 if relation_created else 0,
                frame_id,
                latitude,
                longitude,
                received_at,
                alert_id,
            ),
        )

    if alarm_group is not None:
        _recalculate_logical_alert(
            connection,
            alert_id=alert_id,
            updated_at=received_at,
        )
        expire_aprs_alerts(
            now=received_at,
            connection=connection,
        )

    return {
        "alert_id": alert_id,
        "source_callsign": source_callsign,
        "created": created,
        "warning_kind": warning_kind,
        "identity_key": identity_key,
        "notification_required": emergency_notification and created,
    }


def process_emergency_frame(
    connection: sqlite3.Connection,
    *,
    frame_id: int,
    parsed: dict[str, Any],
    frame_row: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Translate an APRS emergency packet into the shared warning intake."""

    line = str(frame_row.get("line") or "")
    emergency_data = build_emergency_frame_data(parsed=parsed, row=frame_row, line=line)
    if emergency_data is None:
        return None

    alert_type = str(
        emergency_data.get("emergency_code")
        or emergency_data.get("mice_message")
        or emergency_data.get("emergency_source")
        or "EMERGENCY"
    ).strip().upper()
    message = str(emergency_data.get("summary") or emergency_data.get("comment") or "").strip()
    latitude = _float_or_none(emergency_data.get("latitude"))
    longitude = _float_or_none(emergency_data.get("longitude"))
    return accept_aprs_warning_frame(
        connection,
        frame_id=frame_id,
        parsed=parsed,
        frame_row=frame_row,
        warning={
            "alert_type": alert_type,
            "message": message,
            "latitude": latitude,
            "longitude": longitude,
            "warning_kind": "emergency",
            "emergency_notification": True,
        },
    )


def _raw_aprs_message_fields(parsed: Mapping[str, Any]) -> tuple[str, str]:
    info = str(parsed.get("logical_info") or parsed.get("info") or "")
    if not info.startswith(":") or len(info) < 11 or info[10] != ":":
        return "", ""
    return info[1:10].rstrip().upper(), info[11:]


def process_alarm_group_message_frame(
    connection: sqlite3.Connection,
    *,
    frame_id: int,
    parsed: dict[str, Any],
    frame_row: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Route a configured APRS alarm-group message into the shared intake."""

    if not get_aprs_alarm_enabled():
        return None

    aprs_data = dict(parsed.get("aprs_data") or {})
    if str(aprs_data.get("packet_group") or "").strip().lower() != "message":
        return None
    if str(aprs_data.get("packet_type_code") or "").strip().lower() != "message":
        return None

    raw_addressee, raw_content = _raw_aprs_message_fields(parsed)
    addressee = str(aprs_data.get("addressee") or raw_addressee).strip().upper()
    if not addressee or addressee not in set(get_aprs_alarm_groups()):
        return None
    warning_fields = parse_aprs_group_warning_content(raw_content)
    if not alarm_event_meets_category_threshold(
        warning_fields.get("event_code"),
        warning_fields.get("severity_level"),
        target="alerts",
    ):
        return None

    return accept_aprs_warning_frame(
        connection,
        frame_id=frame_id,
        parsed=parsed,
        frame_row=frame_row,
        warning={
            "alert_type": addressee,
            "raw_content": raw_content,
            "alarm_group": addressee,
            **warning_fields,
            "latitude": aprs_data.get("latitude"),
            "longitude": aprs_data.get("longitude"),
            "warning_kind": "alarm_group",
            "emergency_notification": False,
        },
    )


def process_alert_frame(
    connection: sqlite3.Connection,
    *,
    frame_id: int,
    parsed: dict[str, Any],
    frame_row: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Recognize one alert candidate and feed it into the shared intake."""

    emergency_result = process_emergency_frame(
        connection,
        frame_id=frame_id,
        parsed=parsed,
        frame_row=frame_row,
    )
    if emergency_result is not None:
        return emergency_result
    return process_alarm_group_message_frame(
        connection,
        frame_id=frame_id,
        parsed=parsed,
        frame_row=frame_row,
    )


def attention_alert_count(*, now: str | None = None) -> int:
    timestamp = now or utc_now()
    alarm_enabled = 1 if get_aprs_alarm_enabled() else 0
    try:
        expire_aprs_alerts(now=timestamp)
        row = fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM aprs_alerts
            WHERE superseded_by_alert_id IS NULL
              AND is_active = 1
              AND (? = 1 OR alarm_group IS NULL)
              AND (expires_at IS NULL OR julianday(expires_at) > julianday(?))
              AND (
                    valid_until_utc IS NULL
                    OR julianday(valid_until_utc) > julianday(?)
              )
              AND muted_indefinitely = 0
              AND (muted_until IS NULL OR julianday(muted_until) <= julianday(?))
            """,
            (alarm_enabled, timestamp, timestamp, timestamp),
        )
    except sqlite3.OperationalError:
        # Template rendering can happen before the application lifespan has
        # initialized a fresh or just-upgraded database.
        return 0
    return int(row["total"] or 0) if row is not None else 0


def _related_entity(parsed: dict[str, Any] | None, source_callsign: str) -> dict[str, str]:
    aprs_data = dict((parsed or {}).get("aprs_data") or {})
    packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
    entity_name = str(aprs_data.get("entity_name") or "").strip()
    if packet_group in {"object", "item"} and entity_name:
        label = entity_name
        kind = packet_group
    else:
        label = source_callsign
        kind = "station"
    return {
        "label": label,
        "kind": kind,
        "detail_href": build_station_detail_href(label) if label else "",
    }


def _serialize_alert(row: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    item = dict(row)
    parsed = parse_tnc2_frame(str(item.get("last_frame_line") or ""))
    related_entity = _related_entity(parsed, str(item.get("source_callsign") or ""))
    muted = _is_muted(item, now=now)
    muted_until = str(item.get("muted_until") or "").strip()
    area_codes = _stored_area_codes(item.get("area_codes_json"))
    expires_at = parse_datetime(item.get("expires_at"))
    valid_until = parse_datetime(item.get("valid_until_utc"))
    active_reference = now or datetime.now(timezone.utc)
    if active_reference.tzinfo is None:
        active_reference = active_reference.replace(tzinfo=timezone.utc)
    active = bool(int(item.get("is_active") or 0)) and (
        expires_at is None
        or expires_at.astimezone(timezone.utc) > active_reference.astimezone(timezone.utc)
    ) and (
        valid_until is None
        or valid_until.astimezone(timezone.utc) > active_reference.astimezone(timezone.utc)
    )
    item.update(
        {
            "id": int(item["id"]),
            "frame_count": int(item.get("frame_count") or 0),
            "alarm_group": str(item.get("alarm_group") or "").strip().upper(),
            "destination_group": str(item.get("alarm_group") or "").strip().upper(),
            "logical_alert_id": str(item.get("logical_alert_id") or "").strip().upper(),
            "event_icon": resolve_alert_event_icon(
                item.get("event_code"),
                alert_type=item.get("alert_type"),
            ),
            "severity_level": _integer_or_none(item.get("severity_level")),
            "received_parts": int(item.get("received_parts") or 0),
            "parts_total": _integer_or_none(item.get("parts_total")),
            "completion_status": str(
                item.get("completion_status") or "incomplete"
            ).strip().lower(),
            "area_codes": area_codes,
            "area_count": len(area_codes),
            "active": active,
            "muted": muted,
            "muted_until_label": format_display_datetime(muted_until) if muted_until else "",
            "expires_at_label": (
                format_display_datetime(item.get("expires_at"))
                if item.get("expires_at")
                else ""
            ),
            "first_seen_label": format_display_datetime(item.get("first_seen_at")),
            "last_seen_label": format_display_datetime(item.get("last_seen_at")),
            "created_label": format_display_datetime(item.get("created_at")),
            "updated_label": format_display_datetime(item.get("updated_at")),
            "latitude_label": str(item.get("latitude")) if item.get("latitude") is not None else "",
            "longitude_label": str(item.get("longitude")) if item.get("longitude") is not None else "",
            "related_entity": related_entity,
            "detail_href": f"/alerts/{int(item['id'])}",
            "last_frame_href": (
                f"/traffic/frames/{int(item['last_frame_id'])}"
                if item.get("last_frame_id") is not None
                else ""
            ),
        }
    )
    if parsed and item.get("last_frame_id") is not None:
        emergency_data = build_emergency_frame_data(
            parsed=parsed,
            row={
                "source": item.get("last_frame_source"),
                "port": item.get("last_frame_port"),
                "created_at": item.get("last_frame_created_at"),
                "interface_id": item.get("last_frame_interface_id"),
            },
            line=str(item.get("last_frame_line") or ""),
        )
    else:
        emergency_data = None
    if emergency_data:
        full_message = str(
            emergency_data.get("summary")
            or emergency_data.get("comment")
            or ""
        ).strip()
        if full_message:
            item["message"] = full_message
    item["modal_frame"] = {
        "id": int(item["last_frame_id"]) if item.get("last_frame_id") is not None else None,
        "timestamp": str(item.get("last_frame_created_at") or item.get("last_seen_at") or ""),
        "source": str(item.get("last_frame_source") or ""),
        "line": str(item.get("last_frame_line") or ""),
        "display_callsign": str(item.get("source_callsign") or ""),
        "emergency": emergency_data is not None,
        "emergency_data": emergency_data or {},
        "alert_id": int(item["id"]),
        "alert_href": f"/alerts/{int(item['id'])}",
        "alert_muted": muted,
        "alert_should_notify": False,
    }
    return item


def list_alerts(
    *,
    page: int = 1,
    page_size: int = ALERT_PAGE_SIZE,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    reference = _normalized_utc_datetime(now)
    timestamp = reference.replace(microsecond=0).isoformat()
    alarm_enabled = 1 if get_aprs_alarm_enabled() else 0
    expire_aprs_alerts(now=reference)
    normalized_page_size = min(max(1, int(page_size)), 100)
    count_row = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM aprs_alerts
        WHERE superseded_by_alert_id IS NULL
          AND is_active = 1
          AND (? = 1 OR alarm_group IS NULL)
          AND (expires_at IS NULL OR julianday(expires_at) > julianday(?))
          AND (
                valid_until_utc IS NULL
                OR julianday(valid_until_utc) > julianday(?)
          )
        """,
        (alarm_enabled, timestamp, timestamp),
    )
    total = int(count_row["total"] or 0) if count_row is not None else 0
    total_pages = max(1, (total + normalized_page_size - 1) // normalized_page_size)
    normalized_page = min(max(1, int(page)), total_pages)
    offset = (normalized_page - 1) * normalized_page_size
    rows = fetch_all(
        """
        SELECT
            alerts.*,
            frames.line AS last_frame_line,
            frames.source AS last_frame_source,
            frames.port AS last_frame_port,
            frames.created_at AS last_frame_created_at,
            frames.interface_id AS last_frame_interface_id
        FROM aprs_alerts AS alerts
        LEFT JOIN traffic_frames AS frames ON frames.id = alerts.last_frame_id
        WHERE alerts.superseded_by_alert_id IS NULL
          AND alerts.is_active = 1
          AND (? = 1 OR alerts.alarm_group IS NULL)
          AND (
                alerts.expires_at IS NULL
                OR julianday(alerts.expires_at) > julianday(?)
          )
          AND (
                alerts.valid_until_utc IS NULL
                OR julianday(alerts.valid_until_utc) > julianday(?)
          )
        ORDER BY alerts.last_seen_at DESC, alerts.id DESC
        LIMIT ? OFFSET ?
        """,
        (
            alarm_enabled,
            timestamp,
            timestamp,
            normalized_page_size,
            offset,
        ),
    )
    return {
        "items": [_serialize_alert(dict(row), now=reference) for row in rows],
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "total_pages": total_pages,
        "has_previous": normalized_page > 1,
        "has_next": normalized_page < total_pages,
        "previous_page": normalized_page - 1,
        "next_page": normalized_page + 1,
    }


def _serialize_frame(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    line = str(item.get("line") or "")
    parsed = parse_tnc2_frame(line)
    aprs_data = dict((parsed or {}).get("aprs_data") or {})
    latitude = aprs_data.get("latitude")
    longitude = aprs_data.get("longitude")
    item.update(
        {
            "id": int(item["id"]),
            "created_label": format_display_datetime(item.get("created_at")),
            "path": str((parsed or {}).get("logical_path") or (parsed or {}).get("path") or "").strip(),
            "source_callsign": str(
                (parsed or {}).get("logical_source_key")
                or (parsed or {}).get("source_key")
                or ""
            ).strip(),
            "latitude": latitude,
            "longitude": longitude,
            "position_label": f"{latitude}, {longitude}" if latitude not in {None, ""} and longitude not in {None, ""} else "",
            "detail_href": f"/traffic/frames/{int(item['id'])}",
            "emergency": bool(aprs_data.get("emergency")),
            "related_entity": _related_entity(
                parsed,
                str((parsed or {}).get("logical_source_key") or (parsed or {}).get("source_key") or ""),
            ),
        }
    )
    if item.get("alert_id") is not None:
        item["alert_id"] = int(item["alert_id"])
        item["alert_href"] = f"/alerts/{item['alert_id']}"
    else:
        item["alert_href"] = ""
    return item


def _serialize_alert_part(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    area_codes = _stored_area_codes(item.get("area_codes_json"))
    item.update(
        {
            "id": int(item["id"]),
            "alert_id": int(item["alert_id"]),
            "part_number": _integer_or_none(item.get("part_number")),
            "parts_total": _integer_or_none(item.get("parts_total")),
            "aprs_message_id": str(item.get("aprs_message_id") or "").strip(),
            "area_codes": area_codes,
            "area_count": len(area_codes),
            "received_count": int(item.get("received_count") or 0),
            "first_received_label": format_display_datetime(
                item.get("first_received_at")
            ),
            "last_received_label": format_display_datetime(
                item.get("last_received_at")
            ),
            "initial_frame_href": (
                f"/traffic/frames/{int(item['initial_frame_id'])}"
                if item.get("initial_frame_id") is not None
                else ""
            ),
            "last_frame_href": (
                f"/traffic/frames/{int(item['last_frame_id'])}"
                if item.get("last_frame_id") is not None
                else ""
            ),
        }
    )
    return item


def get_alert(alert_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT
            alerts.*,
            frames.line AS last_frame_line,
            frames.source AS last_frame_source,
            frames.port AS last_frame_port,
            frames.created_at AS last_frame_created_at,
            frames.interface_id AS last_frame_interface_id
        FROM aprs_alerts AS alerts
        LEFT JOIN traffic_frames AS frames ON frames.id = alerts.last_frame_id
        WHERE alerts.id = ?
        """,
        (alert_id,),
    )
    if row is None:
        return None
    alert = _serialize_alert(dict(row))
    history_rows = fetch_all(
        """
        SELECT
            frames.*,
            relations.alert_id,
            relations.received_at AS alert_received_at
        FROM aprs_alert_frames AS relations
        JOIN traffic_frames AS frames ON frames.id = relations.frame_id
        WHERE relations.alert_id = ?
        ORDER BY relations.received_at DESC, frames.id DESC
        """,
        (alert_id,),
    )
    alert["frames"] = [_serialize_frame(dict(history_row)) for history_row in history_rows]
    part_rows = fetch_all(
        """
        SELECT parts.*
        FROM aprs_alert_parts AS parts
        WHERE parts.alert_id = ?
        ORDER BY
            CASE WHEN parts.part_number IS NULL THEN 1 ELSE 0 END,
            parts.part_number ASC,
            parts.id ASC
        """,
        (alert_id,),
    )
    alert["parts"] = [
        _serialize_alert_part(dict(part_row))
        for part_row in part_rows
    ]
    return alert


def get_traffic_frame(frame_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT
            frames.*,
            relations.alert_id,
            alerts.source_callsign AS alert_source_callsign
        FROM traffic_frames AS frames
        LEFT JOIN aprs_alert_frames AS relations ON relations.frame_id = frames.id
        LEFT JOIN aprs_alerts AS alerts ON alerts.id = relations.alert_id
        WHERE frames.id = ?
        """,
        (frame_id,),
    )
    return _serialize_frame(dict(row)) if row is not None else None


def mute_alert(alert_id: int, duration: str) -> bool:
    normalized_duration = str(duration or "").strip().lower()
    timestamp = utc_now()
    if normalized_duration == "indefinite":
        muted_until = None
        muted_indefinitely = 1
    elif normalized_duration in ALERT_MUTE_DURATIONS_HOURS:
        muted_until = (
            datetime.now(timezone.utc)
            + timedelta(hours=ALERT_MUTE_DURATIONS_HOURS[normalized_duration])
        ).replace(microsecond=0).isoformat()
        muted_indefinitely = 0
    else:
        raise ValueError("Unsupported mute duration.")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE aprs_alerts
            SET muted_until = ?,
                muted_indefinitely = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (muted_until, muted_indefinitely, timestamp, alert_id),
        )
        changed = int(cursor.rowcount or 0) == 1
    if changed:
        log_event("INFO", "alerts", f"Muted APRS alert {alert_id} ({normalized_duration})")
    return changed


def unmute_alert(alert_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE aprs_alerts
            SET muted_until = NULL,
                muted_indefinitely = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), alert_id),
        )
        changed = int(cursor.rowcount or 0) == 1
    if changed:
        log_event("INFO", "alerts", f"Unmuted APRS alert {alert_id}")
    return changed


def delete_alert(alert_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM aprs_alerts WHERE id = ?", (alert_id,))
        changed = int(cursor.rowcount or 0) == 1
    if changed:
        log_event("INFO", "alerts", f"Deleted APRS alert {alert_id}; traffic frames were preserved")
    return changed


def delete_alerts(alert_ids: list[int]) -> int:
    normalized_ids = sorted({int(alert_id) for alert_id in alert_ids if int(alert_id) > 0})
    if not normalized_ids:
        return 0
    placeholders = ", ".join("?" for _ in normalized_ids)
    with get_connection() as connection:
        cursor = connection.execute(
            f"DELETE FROM aprs_alerts WHERE id IN ({placeholders})",
            tuple(normalized_ids),
        )
        deleted = max(0, int(cursor.rowcount or 0))
    if deleted:
        log_event("INFO", "alerts", f"Deleted {deleted} APRS alerts; traffic frames were preserved")
    return deleted
