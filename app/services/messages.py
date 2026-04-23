from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app import get_version
from app.db import fetch_all, fetch_one, get_app_setting, get_connection, log_event, set_app_setting, utc_now
from app.i18n import get_app_language, get_translator
from app.services.outbound import (
    _format_aprs_latitude,
    _format_aprs_longitude,
    enqueue_ack_job,
    enqueue_beacon_job,
    enqueue_direct_message_job,
    enqueue_query_message_job,
    enqueue_query_response_job,
    enqueue_status_job,
    mark_outbound_job_cancelled,
)

MESSAGE_DIRECTION_RX = "rx"
MESSAGE_DIRECTION_TX = "tx"
MESSAGE_STATUS_QUEUED = "queued"
MESSAGE_STATUS_SENT = "sent"
MESSAGE_STATUS_ACKED = "acked"
MESSAGE_STATUS_REJECTED = "rejected"
MESSAGE_STATUS_FAILED = "failed"
MESSAGE_STATUS_RECEIVED = "received"
DIRECT_MESSAGE_KIND = "direct_message"
QUERY_MESSAGE_KIND = "query"
ACK_MESSAGE_KIND = "ack"
MESSAGE_NUMBER_KEY = "messages.next_message_number"
MESSAGE_NUMBER_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MESSAGE_MAX_LENGTH = 67
RETRY_DELAYS_SECONDS = (8, 16, 32)
MAX_TX_ATTEMPTS = 1 + len(RETRY_DELAYS_SECONDS)
FINAL_ACK_WAIT_SECONDS = 30
HEARD_FRESH_SECONDS = 10 * 60
HEARD_WARN_SECONDS = 30 * 60
QUERY_RESPONSE_DELAY_SECONDS = 5

_TNC2_RE = re.compile(r"^(?P<source>[^>]+?)\s*>\s*(?P<destination>[^,:]+?)(?:\s*,\s*(?P<path>[^:]+))?\s*:(?P<info>.*)$")
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?$")
_MESSAGE_SUFFIX_RE = re.compile(r"^(?P<text>.*?)(?:\{(?P<number>[0-9A-Z]{1,2})(?:}(?P<reply_ack>[0-9A-Z]{1,2})?)?)?$")
SUPPORTED_QUERY_TYPES = ("?APRS", "?APRSP", "?APRSS", "?APRSV", "?VER")
APRS_SERVICE_DESTINATIONS = (
    "ANSRVR",
    "AVRS",
    "CQ",
    "CQSRVR",
    "E",
    "EMAIL",
    "QRU",
    "QRZ",
    "SMSGTE",
    "WHERE",
    "WHERE-IS",
    "WHO-15",
    "WHO-IS",
    "WLNK-1",
    "WXBOT",
)
_APRS_SERVICE_DESTINATION_SET = frozenset(APRS_SERVICE_DESTINATIONS)


def _t(message: str) -> str:
    return get_translator(get_app_language())(message)


def normalize_aprs_destination_callsign(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError(_t("Destination callsign is required."))
    if not _CALLSIGN_RE.fullmatch(normalized) and normalized not in _APRS_SERVICE_DESTINATION_SET:
        raise ValueError(_t("Destination callsign must be an AX.25/APRS callsign with optional SSID 0-15."))
    return normalized


def normalize_aprs_message_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(_t("Message text is required."))
    if len(text) > MESSAGE_MAX_LENGTH:
        raise ValueError(_t("Message text must be 67 ASCII characters or fewer."))
    for char in text:
        codepoint = ord(char)
        if codepoint < 32 or codepoint > 126:
            raise ValueError(_t("Message text may contain only printable ASCII characters."))
    return text


def normalize_aprs_path(value: str) -> str:
    path = str(value or "").strip().upper()
    if len(path) > 64:
        raise ValueError(_t("Future RF path must be 64 printable ASCII characters or fewer."))
    for char in path:
        codepoint = ord(char)
        if codepoint < 32 or codepoint > 126:
            raise ValueError(_t("Future RF path must use printable ASCII only."))
    return path


def create_or_update_conversation(callsign: str, *, path: str | None = None) -> dict[str, Any]:
    remote_callsign, remote_ssid = split_callsign_ssid(normalize_aprs_destination_callsign(callsign))
    timestamp = utc_now()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, remote_callsign, remote_ssid, path, created_at, updated_at
            FROM aprs_message_conversations
            WHERE remote_callsign = ? AND remote_ssid = ?
            """,
            (remote_callsign, remote_ssid),
        ).fetchone()
        if row is None:
            cursor = connection.execute(
                """
                INSERT INTO aprs_message_conversations(remote_callsign, remote_ssid, path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (remote_callsign, remote_ssid, path or "", timestamp, timestamp),
            )
            conversation_id = int(cursor.lastrowid)
        else:
            conversation_id = int(row["id"])
            if path is not None:
                connection.execute(
                    """
                    UPDATE aprs_message_conversations
                    SET path = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (path, timestamp, conversation_id),
                )
    conversation = fetch_one(
        """
        SELECT id, remote_callsign, remote_ssid, path, created_at, updated_at
        FROM aprs_message_conversations
        WHERE id = ?
        """,
        (conversation_id,),
    )
    return dict(conversation) if conversation else {}


def update_conversation_path(conversation_id: int, path: str) -> None:
    normalized_path = normalize_aprs_path(path)
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_message_conversations
            SET path = ?, updated_at = ?
            WHERE id = ?
            """,
            (normalized_path, utc_now(), conversation_id),
        )


def _get_conversation(callsign: str) -> dict[str, Any] | None:
    remote_callsign, remote_ssid = split_callsign_ssid(normalize_aprs_destination_callsign(callsign))
    row = fetch_one(
        """
        SELECT id, remote_callsign, remote_ssid, path, created_at, updated_at
        FROM aprs_message_conversations
        WHERE remote_callsign = ? AND remote_ssid = ?
        LIMIT 1
        """,
        (remote_callsign, remote_ssid),
    )
    return dict(row) if row else None


def _resolve_auto_ack_path(*, sender: str, station_settings: dict[str, Any]) -> str:
    default_path = ""
    try:
        default_path = normalize_aprs_path(str(station_settings.get("beacon_path") or ""))
    except ValueError:
        default_path = ""
    try:
        existing_conversation = _get_conversation(sender)
    except ValueError:
        existing_conversation = None
    if existing_conversation is None:
        return default_path
    try:
        conversation_path = normalize_aprs_path(str(existing_conversation.get("path") or ""))
    except ValueError:
        return default_path
    return conversation_path or default_path


def queue_outgoing_message(*, callsign: str, message_text: str, path: str = "") -> dict[str, Any]:
    normalized_callsign = normalize_aprs_destination_callsign(callsign)
    normalized_text = normalize_aprs_message_text(message_text)
    normalized_path = normalize_aprs_path(path)
    message_kind = QUERY_MESSAGE_KIND if normalized_text.startswith("?") else DIRECT_MESSAGE_KIND
    message_number = next_message_number() if message_kind == DIRECT_MESSAGE_KIND else None
    timestamp = utc_now()
    local_sender = _local_station_identity()
    if not local_sender:
        raise ValueError(_t("Local station callsign is required."))
    conversation = create_or_update_conversation(normalized_callsign, path=normalized_path)
    update_conversation_path(int(conversation["id"]), normalized_path)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO aprs_messages(
                conversation_id, direction, sender, addressee, message_text, path, message_number,
                status, tx_attempt_count, is_unread, outbound_job_id, created_at, updated_at,
                sent_at, acked_at, last_attempt_at, failed_at, failure_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (
                int(conversation["id"]),
                MESSAGE_DIRECTION_TX,
                local_sender,
                normalized_callsign,
                normalized_text,
                normalized_path,
                message_number,
                MESSAGE_STATUS_QUEUED,
                timestamp,
                timestamp,
            ),
        )
        message_id = int(cursor.lastrowid)

    station_settings = _get_station_settings()
    outbound_message = {
        "id": message_id,
        "addressee": normalized_callsign,
        "message_text": normalized_text,
        "path": normalized_path,
        "message_number": message_number,
    }
    if message_kind == QUERY_MESSAGE_KIND:
        success, error = enqueue_query_message_job(outbound_message, station_settings, trigger="manual")
    else:
        success, error = enqueue_direct_message_job(outbound_message, station_settings, trigger="manual")
    if not success:
        mark_message_failed(message_id, error or "Failed to queue outbound APRS message.")
        raise ValueError(error or _t("Failed to queue outbound APRS message."))

    queued_job = fetch_one(
        """
        SELECT id
        FROM outbound_jobs
        WHERE aprs_message_id = ? AND status = 'queued'
        ORDER BY id DESC
        LIMIT 1
        """,
        (message_id,),
    )
    if queued_job is not None:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE aprs_messages
                SET outbound_job_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (int(queued_job["id"]), utc_now(), message_id),
            )

    message = get_message(message_id)
    if message is None:
        raise ValueError(_t("Queued message could not be loaded."))
    return message


def get_messages_page_data() -> dict[str, Any]:
    try:
        expire_direct_message_timeouts()
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to expire direct message timeouts: {exc}")
    try:
        heard_by_key = _heard_station_lookup()
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to load heard station snapshot: {exc}")
        heard_by_key = {}
    try:
        conversation_rows = fetch_all(
            """
            SELECT c.id, c.remote_callsign, c.remote_ssid, c.path, c.created_at, c.updated_at
            FROM aprs_message_conversations c
            ORDER BY c.updated_at DESC, c.id DESC
            """
        )
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to load APRS message conversations: {exc}")
        conversation_rows = []
    conversations: list[dict[str, Any]] = []
    active_conversation_id: str | None = None
    local_sender = _local_station_identity()
    for row in conversation_rows:
        display_callsign = format_display_callsign(str(row["remote_callsign"]), str(row["remote_ssid"]))
        if local_sender and _callsign_identity_matches(display_callsign, local_sender):
            continue
        conversation_id = int(row["id"])
        messages = [dict(item) for item in fetch_all(
            """
            SELECT id, direction, sender, addressee, message_text, path, message_number, status,
                   tx_attempt_count, is_unread, created_at, updated_at, sent_at, acked_at,
                   last_attempt_at, failed_at, failure_reason
            FROM aprs_messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id,),
        )]
        heard_snapshot = heard_by_key.get(display_callsign.casefold()) or heard_by_key.get(str(row["remote_callsign"]).casefold())
        unread_count = sum(1 for item in messages if item["direction"] == MESSAGE_DIRECTION_RX and int(item["is_unread"] or 0))
        if active_conversation_id is None and unread_count > 0:
            active_conversation_id = str(conversation_id)
        prepared_messages = [_serialize_message_row(item) for item in messages]
        last_activity_at = prepared_messages[-1]["timestamp"] if prepared_messages else str(row["created_at"])
        recently_heard = False
        heard_recently_label = ""
        heard_recently_state = "none"
        if heard_snapshot is not None:
            age_s = heard_snapshot.get("last_heard_age_s")
            heard_recently_state = _heard_recently_state(age_s)
            recently_heard = heard_recently_state != "none"
            heard_label = str(heard_snapshot.get("last_heard_label") or "").strip()
            heard_relative = str(heard_snapshot.get("last_heard_relative") or "").strip()
            if heard_label and heard_relative:
                heard_recently_label = f"{heard_label} ({heard_relative})"
            else:
                heard_recently_label = heard_relative or heard_label
        conversations.append(
            {
                "id": str(conversation_id),
                "callsign": display_callsign,
                "messages": prepared_messages,
                "created_at": str(row["created_at"]),
                "last_activity_at": last_activity_at,
                "unread_count": unread_count,
                "message_state": "unread" if unread_count else "read",
                "recently_heard": recently_heard,
                "heard_recently_state": heard_recently_state,
                "heard_recently_label": heard_recently_label,
                "path": str(row["path"] or ""),
            }
        )
    if active_conversation_id is None and conversations:
        active_conversation_id = conversations[0]["id"]
    station_settings = _get_station_settings()
    return {
        "conversations": conversations,
        "active_conversation_id": active_conversation_id,
        "composer_limit": MESSAGE_MAX_LENGTH,
        "recently_heard_window_minutes": HEARD_WARN_SECONDS // 60,
        "default_path": str(station_settings.get("beacon_path") or "").strip(),
        "service_destinations": list(APRS_SERVICE_DESTINATIONS),
    }


def get_unread_inbox_count() -> int:
    try:
        rows = fetch_all(
            """
            SELECT c.remote_callsign, c.remote_ssid, COUNT(m.id) AS unread_count
            FROM aprs_message_conversations c
            JOIN aprs_messages m ON m.conversation_id = c.id
            WHERE m.direction = ? AND m.is_unread = 1
            GROUP BY c.id, c.remote_callsign, c.remote_ssid
            """,
            (MESSAGE_DIRECTION_RX,),
        )
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to load unread inbox count: {exc}")
        return 0
    local_sender = _local_station_identity()
    unread_total = 0
    for row in rows:
        display_callsign = format_display_callsign(str(row["remote_callsign"]), str(row["remote_ssid"]))
        if local_sender and _callsign_identity_matches(display_callsign, local_sender):
            continue
        unread_total += int(row["unread_count"] or 0)
    return unread_total


def mark_conversation_read(conversation_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET is_unread = 0,
                updated_at = ?
            WHERE conversation_id = ? AND direction = ?
            """,
            (utc_now(), conversation_id, MESSAGE_DIRECTION_RX),
        )


def delete_conversation(conversation_id: int) -> None:
    message_ids = [int(row["id"]) for row in fetch_all("SELECT id FROM aprs_messages WHERE conversation_id = ?", (conversation_id,))]
    for message_id in message_ids:
        cancel_pending_message_jobs(message_id)
    with get_connection() as connection:
        connection.execute("DELETE FROM aprs_message_conversations WHERE id = ?", (conversation_id,))


def get_message(message_id: int) -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, conversation_id, direction, sender, addressee, message_text, path, message_number, status,
               tx_attempt_count, is_unread, outbound_job_id, created_at, updated_at, sent_at, acked_at,
               last_attempt_at, failed_at, failure_reason
        FROM aprs_messages
        WHERE id = ?
        """,
        (message_id,),
    )
    return dict(row) if row else None


def register_outbound_job_link(message_id: int, job_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET outbound_job_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (job_id, utc_now(), message_id),
        )


def _register_outbound_message_transmission(message_id: int, job_id: int, *, allow_retry: bool) -> None:
    message = get_message(message_id)
    if message is None:
        return
    current_status = str(message.get("status") or "")
    if current_status not in {MESSAGE_STATUS_QUEUED, MESSAGE_STATUS_SENT}:
        return
    now = utc_now()
    next_attempt = int(message.get("tx_attempt_count") or 0) + 1
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET status = ?,
                tx_attempt_count = ?,
                outbound_job_id = ?,
                sent_at = COALESCE(sent_at, ?),
                last_attempt_at = ?,
                updated_at = ?,
                failure_reason = NULL
            WHERE id = ?
            """,
            (MESSAGE_STATUS_SENT, next_attempt, job_id, now, now, now, message_id),
        )
        connection.execute(
            """
            UPDATE aprs_message_conversations
            SET updated_at = ?
            WHERE id = ?
            """,
            (now, int(message["conversation_id"])),
        )
    if allow_retry and next_attempt < MAX_TX_ATTEMPTS:
        schedule_message_retry(message_id, RETRY_DELAYS_SECONDS[next_attempt - 1])


def register_direct_message_transmission(message_id: int, job_id: int) -> None:
    _register_outbound_message_transmission(message_id, job_id, allow_retry=True)


def register_query_message_transmission(message_id: int, job_id: int) -> None:
    _register_outbound_message_transmission(message_id, job_id, allow_retry=False)


def mark_message_failed(message_id: int, reason: str) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET status = ?, failed_at = ?, failure_reason = ?, updated_at = ?
            WHERE id = ? AND status NOT IN (?, ?)
            """,
            (
                MESSAGE_STATUS_FAILED,
                now,
                str(reason or "").strip()[:500],
                now,
                message_id,
                MESSAGE_STATUS_ACKED,
                MESSAGE_STATUS_REJECTED,
            ),
        )


def retry_failed_message(message_id: int) -> dict[str, Any]:
    message = get_message(message_id)
    if message is None:
        raise ValueError(_t("Message does not exist."))
    if str(message.get("direction") or "") != MESSAGE_DIRECTION_TX:
        raise ValueError(_t("Only outbound messages can be retried."))
    if str(message.get("status") or "") != MESSAGE_STATUS_FAILED:
        raise ValueError(_t("Only failed messages can be retried."))

    cancel_pending_message_jobs(message_id)
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET status = ?,
                tx_attempt_count = 0,
                outbound_job_id = NULL,
                updated_at = ?,
                acked_at = NULL,
                last_attempt_at = NULL,
                failed_at = NULL,
                failure_reason = NULL
            WHERE id = ?
            """,
            (MESSAGE_STATUS_QUEUED, now, message_id),
        )

    refreshed = get_message(message_id)
    if refreshed is None:
        raise ValueError(_t("Message could not be reloaded."))
    station_settings = _get_station_settings()
    success, error = enqueue_direct_message_job(refreshed, station_settings, trigger="manual-retry")
    if not success:
        mark_message_failed(message_id, error or "Failed to queue manual retry.")
        raise ValueError(error or _t("Failed to queue manual retry."))

    queued_job = fetch_one(
        """
        SELECT id
        FROM outbound_jobs
        WHERE aprs_message_id = ? AND status = 'queued'
        ORDER BY id DESC
        LIMIT 1
        """,
        (message_id,),
    )
    if queued_job is not None:
        register_outbound_job_link(message_id, int(queued_job["id"]))
    result = get_message(message_id)
    if result is None:
        raise ValueError(_t("Retried message could not be loaded."))
    return result


def cancel_pending_message_jobs(message_id: int) -> None:
    rows = fetch_all(
        """
        SELECT id
        FROM outbound_jobs
        WHERE aprs_message_id = ?
          AND status = 'queued'
        ORDER BY id ASC
        """,
        (message_id,),
    )
    for row in rows:
        mark_outbound_job_cancelled(int(row["id"]))


def schedule_message_retry(message_id: int, delay_seconds: int) -> None:
    message = get_message(message_id)
    if message is None or str(message.get("status")) in {MESSAGE_STATUS_ACKED, MESSAGE_STATUS_REJECTED, MESSAGE_STATUS_FAILED}:
        return
    existing = fetch_one(
        """
        SELECT id
        FROM outbound_jobs
        WHERE aprs_message_id = ?
          AND status = 'queued'
        ORDER BY id DESC
        LIMIT 1
        """,
        (message_id,),
    )
    if existing is not None:
        return
    station_settings = _get_station_settings()
    scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    success, error = enqueue_direct_message_job(message, station_settings, trigger="retry", scheduled_for=scheduled_for)
    if not success:
        mark_message_failed(message_id, error or "Failed to queue retry.")
        return
    queued_job = fetch_one(
        """
        SELECT id
        FROM outbound_jobs
        WHERE aprs_message_id = ? AND status = 'queued'
        ORDER BY id DESC
        LIMIT 1
        """,
        (message_id,),
    )
    if queued_job is not None:
        register_outbound_job_link(message_id, int(queued_job["id"]))


def expire_direct_message_timeouts() -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=FINAL_ACK_WAIT_SECONDS)).replace(microsecond=0).isoformat()
    rows = fetch_all(
        """
        SELECT id
        FROM aprs_messages
        WHERE direction = ?
          AND status = ?
          AND tx_attempt_count >= ?
          AND last_attempt_at IS NOT NULL
          AND last_attempt_at <= ?
        """,
        (MESSAGE_DIRECTION_TX, MESSAGE_STATUS_SENT, MAX_TX_ATTEMPTS, cutoff),
    )
    for row in rows:
        pending = fetch_one(
            """
            SELECT id
            FROM outbound_jobs
            WHERE aprs_message_id = ?
              AND status = 'queued'
            LIMIT 1
            """,
            (int(row["id"]),),
        )
        if pending is None:
            mark_message_failed(int(row["id"]), "No ACK received after APRS retry window.")


def process_incoming_tnc2_message(line: str, *, timestamp: str | None = None) -> None:
    parsed = _parse_effective_incoming_tnc2_line(line, log_invalid_third_party=True)
    if parsed is None:
        return
    info = parsed["info"]
    if not info.startswith(":") or len(info) < 11:
        return

    addressee = info[1:10].rstrip()
    text_field = info[11:] if len(info) >= 11 and info[10] == ":" else ""
    if not addressee or not text_field:
        return

    try:
        sender = normalize_aprs_destination_callsign(parsed["source"])
    except ValueError:
        _log_invalid_message_frame(
            reason="invalid sender callsign",
            source=str(parsed.get("source") or ""),
            line=line,
        )
        return
    if addressee.upper().startswith("BLN"):
        store_incoming_bulletin(
            sender=sender,
            addressee=addressee.upper(),
            message_text=text_field,
            path=parsed["path"],
            timestamp=_normalize_timestamp(timestamp),
        )
        return

    local_sender = _local_station_identity()
    if not local_sender or not _callsign_identity_matches(addressee.upper(), local_sender):
        return

    if local_sender and _callsign_identity_matches(sender, local_sender):
        return
    received_at = _normalize_timestamp(timestamp)
    if text_field.startswith("?"):
        query_text, query_number, query_ack_number = _parse_query_text(text_field)
        if not query_text:
            return
        is_new_query = store_incoming_query(
            sender=sender,
            addressee=addressee.upper(),
            query_text=query_text,
            query_number=query_number,
            ack_number=query_ack_number,
            path=parsed["path"],
            timestamp=received_at,
        )
        if is_new_query:
            _handle_incoming_query(sender=sender, query_text=query_text, query_number=query_number, timestamp=received_at)
        return
    ack_match = re.fullmatch(r"ack(?P<number>[0-9A-Z]{1,2})(?:}(?P<reply_ack>[0-9A-Z]{1,2})?)?", text_field, flags=re.IGNORECASE)
    reject_match = re.fullmatch(r"rej(?P<number>[0-9A-Z]{1,2})(?:}(?P<reply_ack>[0-9A-Z]{1,2})?)?", text_field, flags=re.IGNORECASE)
    if ack_match:
        message_number = _normalize_message_number(ack_match.group("number"))
        if not message_number:
            return
        acknowledge_outgoing_message(sender=sender, addressee=addressee.upper(), message_number=message_number, timestamp=received_at)
        return
    if reject_match:
        message_number = _normalize_message_number(reject_match.group("number"))
        if not message_number:
            return
        reject_outgoing_message(sender=sender, addressee=addressee.upper(), message_number=message_number, timestamp=received_at)
        return

    suffix_match = _MESSAGE_SUFFIX_RE.fullmatch(text_field)
    if suffix_match is None:
        return
    message_text = suffix_match.group("text") or ""
    raw_message_number = suffix_match.group("number")
    message_number = _normalize_message_number(raw_message_number)
    ack_number = _normalize_ack_number(raw_message_number)
    store_incoming_message(
        sender=sender,
        addressee=addressee.upper(),
        message_text=message_text,
        message_number=message_number,
        ack_number=ack_number,
        path=parsed["path"],
        timestamp=received_at,
    )


def _handle_incoming_query(*, sender: str, query_text: str, query_number: str | None, timestamp: str) -> None:
    query_type = str(query_text or "").strip().upper().split()[0]
    station_settings = _get_station_settings()
    scheduled_for = _query_response_scheduled_for(query_number)
    if query_type in {"?APRS", "?APRS?"}:
        enqueue_automatic_query_text_response(
            sender=sender,
            station_settings=station_settings,
            message_text=f"Queries: {' '.join(SUPPORTED_QUERY_TYPES)}",
            trigger="query-aprs",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
        )
        return
    if query_type == "?APRSP":
        success, error = enqueue_automatic_query_position_response(
            sender=sender,
            station_settings=station_settings,
            trigger="query-aprsp",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
        )
        if not success:
            log_event("INFO", "messages", f"Ignored ?APRSP from {sender}: {error or 'position unavailable'}")
        return
    if query_type == "?APRSS":
        success, error = enqueue_automatic_query_status_response(
            sender=sender,
            station_settings=station_settings,
            trigger="query-aprss",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
        )
        if not success:
            log_event("INFO", "messages", f"Ignored ?APRSS from {sender}: {error or 'status unavailable'}")
        return
    if query_type in {"?APRSV", "?VER"}:
        enqueue_automatic_query_text_response(
            sender=sender,
            station_settings=station_settings,
            message_text=f"APRSBox {get_version()}",
            trigger="query-version",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
        )
        return
    log_event("INFO", "messages", f"Ignored unsupported query from {sender}: {query_text.strip()[:80]}")


def enqueue_automatic_query_text_response(
    *,
    sender: str,
    station_settings: dict[str, Any],
    message_text: str,
    trigger: str,
    scheduled_for: datetime | None,
    timestamp: str,
) -> None:
    response_text = normalize_aprs_message_text(message_text)
    response_path = normalize_aprs_path(str(station_settings.get("beacon_path") or ""))
    message_id = create_automatic_query_response(
        sender=sender,
        message_text=response_text,
        path=response_path,
        timestamp=timestamp,
    )
    success, error = enqueue_query_response_job(
        addressee=sender,
        message_text=response_text,
        station_settings=station_settings,
        trigger=trigger,
        path=response_path,
        aprs_message_id=message_id,
        scheduled_for=scheduled_for,
    )
    if not success:
        mark_message_failed(message_id, error or "Failed to queue automatic APRS query response.")
        log_event("INFO", "messages", f"Ignored {trigger} response to {sender}: {error or 'response unavailable'}")
        return
    _link_latest_outbound_job(message_id)


def enqueue_automatic_query_position_response(
    *,
    sender: str,
    station_settings: dict[str, Any],
    trigger: str,
    scheduled_for: datetime | None,
    timestamp: str,
) -> tuple[bool, str | None]:
    response_text = _build_query_position_text(station_settings)
    response_path = normalize_aprs_path(str(station_settings.get("beacon_path") or ""))
    message_id = create_automatic_query_response(
        sender=sender,
        message_text=response_text,
        path=response_path,
        timestamp=timestamp,
    )
    success, error = enqueue_beacon_job(
        station_settings,
        trigger=trigger,
        aprs_message_id=message_id,
        scheduled_for=scheduled_for,
    )
    if not success:
        mark_message_failed(message_id, error or "Failed to queue automatic APRSP response.")
        return False, error
    _link_latest_outbound_job(message_id)
    return True, None


def enqueue_automatic_query_status_response(
    *,
    sender: str,
    station_settings: dict[str, Any],
    trigger: str,
    scheduled_for: datetime | None,
    timestamp: str,
) -> tuple[bool, str | None]:
    response_text = _build_query_status_text(station_settings)
    response_path = normalize_aprs_path(str(station_settings.get("beacon_path") or ""))
    message_id = create_automatic_query_response(
        sender=sender,
        message_text=response_text,
        path=response_path,
        timestamp=timestamp,
    )
    success, error = enqueue_status_job(
        station_settings,
        trigger=trigger,
        aprs_message_id=message_id,
        scheduled_for=scheduled_for,
    )
    if not success:
        mark_message_failed(message_id, error or "Failed to queue automatic APRSS response.")
        return False, error
    _link_latest_outbound_job(message_id)
    return True, None


def acknowledge_outgoing_message(*, sender: str, addressee: str, message_number: str, timestamp: str) -> None:
    row = fetch_one(
        """
        SELECT id
        FROM aprs_messages
        WHERE direction = ?
          AND message_number = ?
          AND status IN (?, ?, ?)
          AND (addressee = ? OR sender = ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            MESSAGE_DIRECTION_TX,
            message_number,
            MESSAGE_STATUS_QUEUED,
            MESSAGE_STATUS_SENT,
            MESSAGE_STATUS_FAILED,
            sender,
            sender,
        ),
    )
    if row is None:
        return
    message_id = int(row["id"])
    cancel_pending_message_jobs(message_id)
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET status = ?, acked_at = ?, failed_at = NULL, updated_at = ?, failure_reason = NULL
            WHERE id = ?
            """,
            (MESSAGE_STATUS_ACKED, timestamp, timestamp, message_id),
        )
    log_event("INFO", "messages", f"ACK received for APRS message #{message_id} ({message_number}) from {sender}")


def reject_outgoing_message(*, sender: str, addressee: str, message_number: str, timestamp: str) -> None:
    row = fetch_one(
        """
        SELECT id
        FROM aprs_messages
        WHERE direction = ?
          AND message_number = ?
          AND status IN (?, ?)
          AND (addressee = ? OR sender = ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (MESSAGE_DIRECTION_TX, message_number, MESSAGE_STATUS_QUEUED, MESSAGE_STATUS_SENT, sender, sender),
    )
    if row is None:
        return
    message_id = int(row["id"])
    cancel_pending_message_jobs(message_id)
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET status = ?, failed_at = ?, failure_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                MESSAGE_STATUS_REJECTED,
                timestamp,
                f"Remote station {sender} rejected APRS message (REJ).",
                timestamp,
                message_id,
            ),
        )
    log_event("INFO", "messages", f"REJ received for APRS message #{message_id} ({message_number}) from {sender}")


def store_incoming_message(
    *,
    sender: str,
    addressee: str,
    message_text: str,
    message_number: str | None,
    ack_number: str | None = None,
    path: str,
    timestamp: str,
) -> None:
    station_settings = _get_station_settings()
    ack_path = _resolve_auto_ack_path(sender=sender, station_settings=station_settings)
    conversation = create_or_update_conversation(sender)
    existing = None
    if message_number:
        existing = fetch_one(
            """
            SELECT id
            FROM aprs_messages
            WHERE conversation_id = ?
              AND direction = ?
              AND sender = ?
              AND message_number = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(conversation["id"]), MESSAGE_DIRECTION_RX, sender, message_number),
        )
    if existing is None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO aprs_messages(
                    conversation_id, direction, sender, addressee, message_text, path, message_number,
                    status, tx_attempt_count, is_unread, outbound_job_id, created_at, updated_at,
                    sent_at, acked_at, last_attempt_at, failed_at, failure_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL)
                """,
                (
                    int(conversation["id"]),
                    MESSAGE_DIRECTION_RX,
                    sender,
                    addressee,
                    message_text,
                    normalize_aprs_path(path),
                    message_number,
                    MESSAGE_STATUS_RECEIVED,
                    timestamp,
                    timestamp,
                ),
            )
        log_event("INFO", "messages", f"Stored incoming APRS message from {sender} to {addressee}")
    ack_number_for_tx = _normalize_ack_number(ack_number if ack_number is not None else message_number)
    if not ack_number_for_tx:
        return
    enqueue_ack_job(sender, ack_number_for_tx, station_settings, path=ack_path, trigger="ack-now")
    enqueue_ack_job(
        sender,
        ack_number_for_tx,
        station_settings,
        path=ack_path,
        trigger="ack-delayed",
        scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=FINAL_ACK_WAIT_SECONDS),
    )


def store_incoming_query(
    *,
    sender: str,
    addressee: str,
    query_text: str,
    query_number: str | None,
    ack_number: str | None = None,
    path: str,
    timestamp: str,
) -> bool:
    station_settings = _get_station_settings()
    ack_path = _resolve_auto_ack_path(sender=sender, station_settings=station_settings)
    ack_number_for_tx = _normalize_ack_number(ack_number if ack_number is not None else query_number)
    conversation = create_or_update_conversation(sender)
    existing = None
    if query_number:
        existing = fetch_one(
            """
            SELECT id
            FROM aprs_messages
            WHERE conversation_id = ?
              AND direction = ?
              AND sender = ?
              AND message_number = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(conversation["id"]), MESSAGE_DIRECTION_RX, sender, query_number),
        )
    if existing is not None:
        # Duplicate bursts for the same query number can appear when a frame is heard
        # multiple times through nearby digipeaters. Limit duplicate ACKs to one short-window
        # transmission per sender/query-number pair to keep TX serialization predictable.
        if ack_number_for_tx and not _has_recent_duplicate_ack(sender=sender, query_number=ack_number_for_tx):
            enqueue_ack_job(sender, ack_number_for_tx, station_settings, path=ack_path, trigger="ack-duplicate")
        return False
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO aprs_messages(
                conversation_id, direction, sender, addressee, message_text, path, message_number,
                status, tx_attempt_count, is_unread, outbound_job_id, created_at, updated_at,
                sent_at, acked_at, last_attempt_at, failed_at, failure_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (
                int(conversation["id"]),
                MESSAGE_DIRECTION_RX,
                sender,
                addressee,
                query_text,
                normalize_aprs_path(path),
                query_number,
                MESSAGE_STATUS_RECEIVED,
                timestamp,
                timestamp,
            ),
        )
    log_event("INFO", "messages", f"Stored incoming APRS query from {sender} to {addressee}")
    if not ack_number_for_tx:
        return True
    enqueue_ack_job(sender, ack_number_for_tx, station_settings, path=ack_path, trigger="ack-now")
    enqueue_ack_job(
        sender,
        ack_number_for_tx,
        station_settings,
        path=ack_path,
        trigger="ack-delayed",
        scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=FINAL_ACK_WAIT_SECONDS),
    )
    return True


def store_incoming_bulletin(
    *,
    sender: str,
    addressee: str,
    message_text: str,
    path: str,
    timestamp: str,
) -> None:
    conversation = create_or_update_conversation(sender)
    display_text = _format_bulletin_display_text(addressee, message_text)
    existing = fetch_one(
        """
        SELECT id
        FROM aprs_messages
        WHERE conversation_id = ?
          AND direction = ?
          AND sender = ?
          AND addressee = ?
          AND message_text = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(conversation["id"]), MESSAGE_DIRECTION_RX, sender, addressee, display_text),
    )
    if existing is not None:
        return
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO aprs_messages(
                conversation_id, direction, sender, addressee, message_text, path, message_number,
                status, tx_attempt_count, is_unread, outbound_job_id, created_at, updated_at,
                sent_at, acked_at, last_attempt_at, failed_at, failure_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, 1, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (
                int(conversation["id"]),
                MESSAGE_DIRECTION_RX,
                sender,
                addressee,
                display_text,
                normalize_aprs_path(path),
                MESSAGE_STATUS_RECEIVED,
                timestamp,
                timestamp,
            ),
        )
    log_event("INFO", "messages", f"Stored inbound APRS bulletin from {sender} to {addressee}")


def create_automatic_query_response(*, sender: str, message_text: str, path: str, timestamp: str) -> int:
    local_sender = _local_station_identity()
    if not local_sender:
        raise ValueError(_t("Local station callsign is required."))
    conversation = create_or_update_conversation(sender)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO aprs_messages(
                conversation_id, direction, sender, addressee, message_text, path, message_number,
                status, tx_attempt_count, is_unread, outbound_job_id, created_at, updated_at,
                sent_at, acked_at, last_attempt_at, failed_at, failure_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 0, 0, NULL, ?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (
                int(conversation["id"]),
                MESSAGE_DIRECTION_TX,
                local_sender,
                sender,
                message_text,
                path,
                MESSAGE_STATUS_QUEUED,
                timestamp,
                timestamp,
            ),
        )
    return int(cursor.lastrowid)


def _link_latest_outbound_job(message_id: int) -> None:
    queued_job = fetch_one(
        """
        SELECT id
        FROM outbound_jobs
        WHERE aprs_message_id = ? AND status = 'queued'
        ORDER BY id DESC
        LIMIT 1
        """,
        (message_id,),
    )
    if queued_job is not None:
        register_outbound_job_link(message_id, int(queued_job["id"]))


def _parse_query_text(text_field: str) -> tuple[str, str | None, str | None]:
    suffix_match = _MESSAGE_SUFFIX_RE.fullmatch(text_field)
    if suffix_match is None:
        return "", None, None
    query_text = str(suffix_match.group("text") or "").strip()
    raw_number = _normalize_ack_number(suffix_match.group("number"))
    message_number = _normalize_message_number(raw_number)
    return query_text, message_number, raw_number


def _normalize_ack_number(value: str | None) -> str | None:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return None
    if not re.fullmatch(r"[0-9A-Z]{1,2}", normalized):
        return None
    return normalized


def _normalize_message_number(value: str | None) -> str | None:
    normalized = _normalize_ack_number(value)
    if normalized is None:
        return None
    if len(normalized) == 1:
        return f"0{normalized}"
    return normalized


def _has_recent_duplicate_ack(*, sender: str, query_number: str, window_seconds: int = QUERY_RESPONSE_DELAY_SECONDS) -> bool:
    normalized_sender = str(sender or "").strip().upper()
    normalized_number = _normalize_ack_number(query_number)
    if not normalized_sender or not normalized_number:
        return False
    window_start = (datetime.now(timezone.utc) - timedelta(seconds=max(1, int(window_seconds)))).replace(microsecond=0).isoformat()
    row = fetch_one(
        """
        SELECT id
        FROM outbound_jobs
        WHERE kind = 'message'
          AND created_at >= ?
          AND payload_json LIKE '%"message_kind":"ack"%'
          AND payload_json LIKE '%"trigger":"ack-duplicate"%'
          AND payload_json LIKE ?
          AND payload_json LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            window_start,
            f'%\"addressee\":\"{normalized_sender}\"%',
            f'%\"message_text\":\"ack{normalized_number}\"%',
        ),
    )
    return row is not None


def _build_query_position_text(station_settings: dict[str, Any]) -> str:
    latitude = float(station_settings["latitude"])
    longitude = float(station_settings["longitude"])
    symbol_table = str(station_settings.get("symbol_table") or "/")
    symbol_code = str(station_settings.get("symbol_code") or ">")
    comment = str(station_settings.get("beacon_comment") or "").strip()
    return (
        f"={_format_aprs_latitude(latitude)}{symbol_table}{_format_aprs_longitude(longitude)}"
        f"{symbol_code}{comment}"
    )


def _build_query_status_text(station_settings: dict[str, Any]) -> str:
    return f">{str(station_settings.get('status_text') or '').strip()}"


def _query_response_scheduled_for(query_number: str | None) -> datetime | None:
    if not query_number:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=QUERY_RESPONSE_DELAY_SECONDS)


def _format_bulletin_display_text(addressee: str, message_text: str) -> str:
    target = str(addressee or "").strip().upper()
    text = str(message_text or "").strip()
    return f"{target}: {text}" if target else text


def split_callsign_ssid(value: str) -> tuple[str, str]:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return "", ""
    base, separator, suffix = normalized.partition("-")
    if separator and suffix.isdigit():
        return base, suffix
    return normalized, ""


def format_display_callsign(callsign: str, ssid: str) -> str:
    return f"{callsign}-{ssid}" if str(ssid or "").strip() else callsign


def next_message_number() -> str:
    current = str(get_app_setting(MESSAGE_NUMBER_KEY) or "00").strip().upper()
    if len(current) != 2 or any(char not in MESSAGE_NUMBER_ALPHABET for char in current):
        current = "00"
    next_value = _increment_message_number(current)
    set_app_setting(MESSAGE_NUMBER_KEY, next_value)
    return current


def _increment_message_number(value: str) -> str:
    first = MESSAGE_NUMBER_ALPHABET.index(value[0])
    second = MESSAGE_NUMBER_ALPHABET.index(value[1])
    numeric = (first * len(MESSAGE_NUMBER_ALPHABET)) + second
    numeric = (numeric + 1) % (len(MESSAGE_NUMBER_ALPHABET) ** 2)
    return (
        MESSAGE_NUMBER_ALPHABET[numeric // len(MESSAGE_NUMBER_ALPHABET)]
        + MESSAGE_NUMBER_ALPHABET[numeric % len(MESSAGE_NUMBER_ALPHABET)]
    )


def _parse_tnc2_line(line: str) -> dict[str, str] | None:
    match = _TNC2_RE.match(line.strip())
    if not match:
        return None
    parsed = match.groupdict(default="")
    return {key: value.strip() for key, value in parsed.items()}


def _parse_effective_incoming_tnc2_line(line: str, *, log_invalid_third_party: bool = False) -> dict[str, str] | None:
    parsed = _parse_tnc2_line(line)
    if parsed is None:
        return None
    info = str(parsed.get("info") or "")
    if not info.startswith("}"):
        return parsed
    encapsulated = info[1:].lstrip()
    embedded = _parse_tnc2_line(encapsulated)
    if embedded is not None:
        return embedded
    if log_invalid_third_party:
        outer_source = str(parsed.get("source") or "").strip() or "unknown"
        _log_invalid_message_frame(
            reason="malformed third-party APRS message frame",
            source=outer_source,
            line=line,
        )
    return None


def _serialize_message_row(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = str(row.get("created_at") or row.get("updated_at") or utc_now())
    has_message_number = bool(str(row.get("message_number") or "").strip())
    return {
        "id": str(row["id"]),
        "direction": str(row["direction"]),
        "text": str(row["message_text"] or ""),
        "timestamp": timestamp,
        "unread": bool(int(row.get("is_unread") or 0)),
        "delivery_state": str(row.get("status") or ""),
        "message_number": str(row.get("message_number") or ""),
        "failure_reason": str(row.get("failure_reason") or ""),
        "tx_attempt_count": int(row.get("tx_attempt_count") or 0),
        "tx_attempt_limit": MAX_TX_ATTEMPTS if has_message_number else 0,
    }


def _normalize_timestamp(value: str | None) -> str:
    if not value:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return utc_now()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _heard_station_lookup() -> dict[str, dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT source, line, created_at
        FROM traffic_frames
        WHERE format = 'TNC2'
        ORDER BY created_at DESC, id DESC
        LIMIT 500
        """
    )
    snapshots: dict[str, dict[str, Any]] = {}
    for row in rows:
        parsed = _parse_effective_incoming_tnc2_line(str(row["line"] or ""))
        if parsed is None:
            continue
        try:
            source = normalize_aprs_destination_callsign(parsed["source"])
        except ValueError:
            # Ignore malformed source callsigns in historical traffic rows.
            continue
        if source.casefold() in snapshots:
            continue
        base_callsign, ssid = split_callsign_ssid(source)
        timestamp = str(row["created_at"])
        heard_label, heard_relative = _format_heard_parts(timestamp)
        snapshots[source.casefold()] = {
            "callsign": base_callsign,
            "display_callsign": format_display_callsign(base_callsign, ssid),
            "last_heard_label": heard_label,
            "last_heard_relative": heard_relative,
            "last_heard_age_s": _heard_age_seconds(timestamp),
        }
    return snapshots


def _heard_age_seconds(timestamp: str) -> int | None:
    heard_at = _parse_iso_timestamp_utc(timestamp)
    if heard_at is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - heard_at).total_seconds()))


def _format_heard_parts(timestamp: str) -> tuple[str, str]:
    heard_at = _parse_iso_timestamp_utc(timestamp)
    if heard_at is None:
        return timestamp, ""

    delta_seconds = max(0, int((datetime.now(timezone.utc) - heard_at).total_seconds()))
    if delta_seconds < 60:
        relative = "teraz"
    elif delta_seconds < 3600:
        minutes = delta_seconds // 60
        relative = _format_minutes_ago(minutes)
    else:
        hours = delta_seconds // 3600
        relative = _format_hours_ago(hours)
    return heard_at.strftime("%Y.%m.%d %H:%M UTC"), relative


def _parse_iso_timestamp_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_minutes_ago(value: int) -> str:
    if value == 1:
        return "1 minutę temu"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return f"{value} minuty temu"
    return f"{value} minut temu"


def _format_hours_ago(value: int) -> str:
    if value == 1:
        return "1 godzinę temu"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return f"{value} godziny temu"
    return f"{value} godzin temu"


def _heard_recently_state(age_s: Any) -> str:
    try:
        age_seconds = int(age_s)
    except (TypeError, ValueError):
        return "none"
    if age_seconds <= HEARD_FRESH_SECONDS:
        return "fresh"
    if age_seconds <= HEARD_WARN_SECONDS:
        return "warn"
    return "stale"


def _get_station_settings() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT callsign, ssid, beacon_interface_id, beacon_path,
               latitude, longitude, symbol_table, symbol_code,
               beacon_comment, status_text
        FROM station_settings
        WHERE id = 1
        """
    )
    return dict(row) if row else {}


def _local_station_identity() -> str:
    station = _get_station_settings()
    callsign = str(station.get("callsign") or "").strip().upper()
    if not callsign:
        return ""
    ssid = str(station.get("ssid") or "").strip()
    if ssid == "0":
        ssid = ""
    return f"{callsign}-{ssid}" if ssid else callsign


def _canonical_callsign_identity(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return ""
    base, ssid = split_callsign_ssid(normalized)
    if not base:
        return ""
    if ssid == "0":
        return base
    return f"{base}-{ssid}" if ssid else base


def _callsign_identity_matches(left: str, right: str) -> bool:
    left_canonical = _canonical_callsign_identity(left)
    right_canonical = _canonical_callsign_identity(right)
    if not left_canonical or not right_canonical:
        return False
    return left_canonical == right_canonical


def _safe_messages_warning(message: str) -> None:
    try:
        log_event("WARNING", "messages", str(message or "").strip())
    except Exception:
        # Skip secondary logging failures so message UI can still render.
        return


def _frame_log_snippet(line: str, *, limit: int = 220) -> str:
    normalized = str(line or "").replace("\r", " ").replace("\n", " ").strip()
    if not normalized:
        return "<empty>"
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _log_invalid_message_frame(*, reason: str, source: str, line: str) -> None:
    normalized_reason = str(reason or "").strip() or "invalid APRS message frame"
    normalized_source = str(source or "").strip() or "unknown"
    snippet = _frame_log_snippet(line)
    message = (
        f"Ignored APRS message frame ({normalized_reason}); "
        f"source='{normalized_source}'; frame='{snippet}'"
    )
    log_event("WARNING", "messages", message)
    log_event("WARNING", "system", message)
