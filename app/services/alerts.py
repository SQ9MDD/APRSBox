from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from app.datetime_utils import format_display_datetime, parse_datetime
from app.db import fetch_all, fetch_one, get_connection, log_event, utc_now
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


def process_emergency_frame(
    connection: sqlite3.Connection,
    *,
    frame_id: int,
    parsed: dict[str, Any],
    frame_row: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Create or update one logical emergency alert inside the frame transaction."""

    line = str(frame_row.get("line") or "")
    emergency_data = build_emergency_frame_data(parsed=parsed, row=frame_row, line=line)
    if emergency_data is None:
        return None

    source_callsign = _normalized_source_callsign(parsed)
    if not source_callsign:
        return None

    received_at = str(frame_row.get("created_at") or utc_now())
    alert_type = str(
        emergency_data.get("emergency_code")
        or emergency_data.get("mice_message")
        or emergency_data.get("emergency_source")
        or "EMERGENCY"
    ).strip().upper()
    message = str(emergency_data.get("summary") or emergency_data.get("comment") or "").strip()
    latitude = _float_or_none(emergency_data.get("latitude"))
    longitude = _float_or_none(emergency_data.get("longitude"))

    insert_cursor = connection.execute(
        """
        INSERT INTO aprs_alerts(
            source_callsign, alert_type, message,
            first_seen_at, last_seen_at, frame_count,
            initial_frame_id, last_frame_id,
            latitude, longitude,
            muted_until, muted_indefinitely,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, NULL, 0, ?, ?)
        ON CONFLICT(source_callsign) DO NOTHING
        """,
        (
            source_callsign,
            alert_type,
            message,
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
        "SELECT id FROM aprs_alerts WHERE source_callsign = ? COLLATE NOCASE",
        (source_callsign,),
    ).fetchone()
    if alert_row is None:
        raise RuntimeError(f"Emergency alert upsert failed for {source_callsign}")
    alert_id = int(alert_row["id"])

    relation_cursor = connection.execute(
        """
        INSERT INTO aprs_alert_frames(alert_id, frame_id, received_at)
        VALUES (?, ?, ?)
        ON CONFLICT(frame_id) DO NOTHING
        """,
        (alert_id, frame_id, received_at),
    )
    relation_created = int(relation_cursor.rowcount or 0) == 1

    if not created:
        connection.execute(
            """
            UPDATE aprs_alerts
            SET alert_type = ?,
                message = ?,
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
                received_at,
                1 if relation_created else 0,
                frame_id,
                latitude,
                longitude,
                received_at,
                alert_id,
            ),
        )

    return {
        "alert_id": alert_id,
        "source_callsign": source_callsign,
        "created": created,
        "notification_required": created,
    }


def attention_alert_count(*, now: str | None = None) -> int:
    timestamp = now or utc_now()
    try:
        row = fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM aprs_alerts
            WHERE muted_indefinitely = 0
              AND (muted_until IS NULL OR julianday(muted_until) <= julianday(?))
            """,
            (timestamp,),
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
    item.update(
        {
            "id": int(item["id"]),
            "frame_count": int(item.get("frame_count") or 0),
            "muted": muted,
            "muted_until_label": format_display_datetime(muted_until) if muted_until else "",
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
    return item


def list_alerts(*, page: int = 1, page_size: int = ALERT_PAGE_SIZE) -> dict[str, Any]:
    normalized_page_size = min(max(1, int(page_size)), 100)
    count_row = fetch_one("SELECT COUNT(*) AS total FROM aprs_alerts")
    total = int(count_row["total"] or 0) if count_row is not None else 0
    total_pages = max(1, (total + normalized_page_size - 1) // normalized_page_size)
    normalized_page = min(max(1, int(page)), total_pages)
    offset = (normalized_page - 1) * normalized_page_size
    rows = fetch_all(
        """
        SELECT
            alerts.*,
            frames.line AS last_frame_line
        FROM aprs_alerts AS alerts
        LEFT JOIN traffic_frames AS frames ON frames.id = alerts.last_frame_id
        ORDER BY alerts.last_seen_at DESC, alerts.id DESC
        LIMIT ? OFFSET ?
        """,
        (normalized_page_size, offset),
    )
    now = datetime.now(timezone.utc)
    return {
        "items": [_serialize_alert(dict(row), now=now) for row in rows],
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


def get_alert(alert_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT
            alerts.*,
            frames.line AS last_frame_line
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
