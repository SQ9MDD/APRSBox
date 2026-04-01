from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import fetch_all, fetch_one, get_app_setting, get_connection, log_event, set_app_setting, utc_now
from app.services.outbound import enqueue_ack_job, enqueue_direct_message_job, mark_outbound_job_cancelled

MESSAGE_DIRECTION_RX = "rx"
MESSAGE_DIRECTION_TX = "tx"
MESSAGE_STATUS_QUEUED = "queued"
MESSAGE_STATUS_SENT = "sent"
MESSAGE_STATUS_ACKED = "acked"
MESSAGE_STATUS_FAILED = "failed"
MESSAGE_STATUS_RECEIVED = "received"
DIRECT_MESSAGE_KIND = "direct_message"
ACK_MESSAGE_KIND = "ack"
MESSAGE_NUMBER_KEY = "messages.next_message_number"
MESSAGE_NUMBER_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MESSAGE_MAX_LENGTH = 67
RETRY_DELAYS_SECONDS = (8, 16, 32)
MAX_TX_ATTEMPTS = 1 + len(RETRY_DELAYS_SECONDS)
FINAL_ACK_WAIT_SECONDS = 30

_TNC2_RE = re.compile(r"^(?P<source>[^>]+?)\s*>\s*(?P<destination>[^,:]+?)(?:\s*,\s*(?P<path>[^:]+))?\s*:(?P<info>.*)$")
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?$")
_MESSAGE_SUFFIX_RE = re.compile(r"^(?P<text>.*?)(?:\{(?P<number>[0-9A-Z]{2})(?:}(?P<reply_ack>[0-9A-Z]{2}))?)?$")


def build_local_callsign_family() -> set[str]:
    station_row = fetch_one("SELECT callsign FROM station_settings WHERE id = 1")
    base_callsign = str(station_row["callsign"] if station_row is not None else "").strip().upper()
    if not base_callsign:
        return set()
    family = {base_callsign}
    for ssid in range(16):
        family.add(f"{base_callsign}-{ssid}")
    return family


def normalize_aprs_destination_callsign(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError("Destination callsign is required.")
    if not _CALLSIGN_RE.fullmatch(normalized):
        raise ValueError("Destination callsign must be an AX.25/APRS callsign with optional SSID 0-15.")
    return normalized


def normalize_aprs_message_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Message text is required.")
    if len(text) > MESSAGE_MAX_LENGTH:
        raise ValueError("Message text must be 67 ASCII characters or fewer.")
    for char in text:
        codepoint = ord(char)
        if codepoint < 32 or codepoint > 126 or char in {"{", "}", "|", "~"}:
            raise ValueError("Message text may contain only APRS-safe printable ASCII characters.")
    return text


def normalize_aprs_path(value: str) -> str:
    path = str(value or "").strip().upper()
    if len(path) > 64:
        raise ValueError("Future RF path must be 64 printable ASCII characters or fewer.")
    for char in path:
        codepoint = ord(char)
        if codepoint < 32 or codepoint > 126:
            raise ValueError("Future RF path must use printable ASCII only.")
    return path


def create_or_update_conversation(callsign: str, *, path: str = "") -> dict[str, Any]:
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
                (remote_callsign, remote_ssid, path, timestamp, timestamp),
            )
            conversation_id = int(cursor.lastrowid)
        else:
            conversation_id = int(row["id"])
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


def queue_outgoing_message(*, callsign: str, message_text: str, path: str = "") -> dict[str, Any]:
    normalized_callsign = normalize_aprs_destination_callsign(callsign)
    normalized_text = normalize_aprs_message_text(message_text)
    normalized_path = normalize_aprs_path(path)
    message_number = next_message_number()
    timestamp = utc_now()
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
                normalized_callsign,
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
    success, error = enqueue_direct_message_job(
        {
            "id": message_id,
            "addressee": normalized_callsign,
            "message_text": normalized_text,
            "path": normalized_path,
            "message_number": message_number,
        },
        station_settings,
        trigger="manual",
    )
    if not success:
        mark_message_failed(message_id, error or "Failed to queue outbound APRS message.")
        raise ValueError(error or "Failed to queue outbound APRS message.")

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
        raise ValueError("Queued message could not be loaded.")
    return message


def get_messages_page_data() -> dict[str, Any]:
    expire_direct_message_timeouts()
    heard_by_key = _heard_station_lookup()
    conversation_rows = fetch_all(
        """
        SELECT c.id, c.remote_callsign, c.remote_ssid, c.path, c.created_at, c.updated_at
        FROM aprs_message_conversations c
        ORDER BY c.updated_at DESC, c.id DESC
        """
    )
    conversations: list[dict[str, Any]] = []
    active_conversation_id: str | None = None
    for row in conversation_rows:
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
        display_callsign = format_display_callsign(str(row["remote_callsign"]), str(row["remote_ssid"]))
        heard_snapshot = heard_by_key.get(display_callsign.casefold()) or heard_by_key.get(str(row["remote_callsign"]).casefold())
        unread_count = sum(1 for item in messages if item["direction"] == MESSAGE_DIRECTION_RX and int(item["is_unread"] or 0))
        if active_conversation_id is None and unread_count > 0:
            active_conversation_id = str(conversation_id)
        prepared_messages = [_serialize_message_row(item) for item in messages]
        last_activity_at = prepared_messages[-1]["timestamp"] if prepared_messages else str(row["created_at"])
        recently_heard = False
        heard_recently_label = ""
        if heard_snapshot is not None:
            age_s = heard_snapshot.get("last_heard_age_s")
            recently_heard = bool(age_s is not None and age_s <= 30 * 60)
            heard_recently_label = str(heard_snapshot.get("last_heard_relative") or heard_snapshot.get("last_heard_label") or "").strip()
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
        "recently_heard_window_minutes": 30,
        "default_path": str(station_settings.get("beacon_path") or "").strip(),
    }


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


def register_direct_message_transmission(message_id: int, job_id: int) -> None:
    message = get_message(message_id)
    if message is None or str(message.get("status")) == MESSAGE_STATUS_ACKED:
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
    if next_attempt < MAX_TX_ATTEMPTS:
        schedule_message_retry(message_id, RETRY_DELAYS_SECONDS[next_attempt - 1])


def mark_message_failed(message_id: int, reason: str) -> None:
    now = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET status = ?, failed_at = ?, failure_reason = ?, updated_at = ?
            WHERE id = ? AND status <> ?
            """,
            (MESSAGE_STATUS_FAILED, now, str(reason or "").strip()[:500], now, message_id, MESSAGE_STATUS_ACKED),
        )


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
    if message is None or str(message.get("status")) in {MESSAGE_STATUS_ACKED, MESSAGE_STATUS_FAILED}:
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
    parsed = _parse_tnc2_line(line)
    if parsed is None:
        return
    info = parsed["info"]
    if not info.startswith(":") or len(info) < 11:
        return

    addressee = info[1:10].rstrip()
    text_field = info[11:] if len(info) >= 11 and info[10] == ":" else ""
    if not addressee or not text_field:
        return
    if addressee.upper().startswith("BLN"):
        return
    local_family = build_local_callsign_family()
    if addressee.upper() not in local_family:
        return

    sender = normalize_aprs_destination_callsign(parsed["source"])
    received_at = _normalize_timestamp(timestamp)
    ack_match = re.fullmatch(r"ack(?P<number>[0-9A-Z]{2})(?:}(?P<reply_ack>[0-9A-Z]{2}))?", text_field, flags=re.IGNORECASE)
    reject_match = re.fullmatch(r"rej(?P<number>[0-9A-Z]{2})(?:}(?P<reply_ack>[0-9A-Z]{2}))?", text_field, flags=re.IGNORECASE)
    if ack_match:
        acknowledge_outgoing_message(sender=sender, addressee=addressee.upper(), message_number=ack_match.group("number").upper(), timestamp=received_at)
        return
    if reject_match:
        reject_outgoing_message(sender=sender, addressee=addressee.upper(), message_number=reject_match.group("number").upper(), timestamp=received_at)
        return

    suffix_match = _MESSAGE_SUFFIX_RE.fullmatch(text_field)
    if suffix_match is None:
        return
    message_text = suffix_match.group("text") or ""
    message_number = suffix_match.group("number")
    if not message_number:
        return
    store_incoming_message(
        sender=sender,
        addressee=addressee.upper(),
        message_text=message_text,
        message_number=message_number.upper(),
        path=parsed["path"],
        timestamp=received_at,
    )


def acknowledge_outgoing_message(*, sender: str, addressee: str, message_number: str, timestamp: str) -> None:
    row = fetch_one(
        """
        SELECT id
        FROM aprs_messages
        WHERE direction = ?
          AND sender = ?
          AND message_number = ?
          AND status IN (?, ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (MESSAGE_DIRECTION_TX, sender, message_number, MESSAGE_STATUS_QUEUED, MESSAGE_STATUS_SENT),
    )
    if row is None:
        return
    message_id = int(row["id"])
    cancel_pending_message_jobs(message_id)
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE aprs_messages
            SET status = ?, acked_at = ?, updated_at = ?, failure_reason = NULL
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
          AND sender = ?
          AND message_number = ?
          AND status IN (?, ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (MESSAGE_DIRECTION_TX, sender, message_number, MESSAGE_STATUS_QUEUED, MESSAGE_STATUS_SENT),
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
            (MESSAGE_STATUS_FAILED, timestamp, f"Remote station {sender} rejected APRS message.", timestamp, message_id),
        )


def store_incoming_message(
    *,
    sender: str,
    addressee: str,
    message_text: str,
    message_number: str,
    path: str,
    timestamp: str,
) -> None:
    conversation = create_or_update_conversation(sender)
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
    station_settings = _get_station_settings()
    enqueue_ack_job(sender, message_number, station_settings, trigger="ack-now")
    enqueue_ack_job(
        sender,
        message_number,
        station_settings,
        trigger="ack-delayed",
        scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=FINAL_ACK_WAIT_SECONDS),
    )


def split_callsign_ssid(value: str) -> tuple[str, str]:
    base, separator, suffix = str(value or "").strip().upper().partition("-")
    if separator and suffix.isdigit():
        return base, suffix
    return base, ""


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


def _serialize_message_row(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = str(row.get("created_at") or row.get("updated_at") or utc_now())
    return {
        "id": str(row["id"]),
        "direction": str(row["direction"]),
        "text": str(row["message_text"] or ""),
        "timestamp": timestamp,
        "unread": bool(int(row.get("is_unread") or 0)),
        "delivery_state": str(row.get("status") or ""),
        "message_number": str(row.get("message_number") or ""),
        "failure_reason": str(row.get("failure_reason") or ""),
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
        parsed = _parse_tnc2_line(str(row["line"] or ""))
        if parsed is None:
            continue
        source = normalize_aprs_destination_callsign(parsed["source"])
        if source.casefold() in snapshots:
            continue
        base_callsign, ssid = split_callsign_ssid(source)
        snapshots[source.casefold()] = {
            "callsign": base_callsign,
            "display_callsign": format_display_callsign(base_callsign, ssid),
            "last_heard_label": str(row["created_at"]),
            "last_heard_relative": str(row["created_at"]),
            "last_heard_age_s": _heard_age_seconds(str(row["created_at"])),
        }
    return snapshots


def _heard_age_seconds(timestamp: str) -> int | None:
    try:
        heard_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((datetime.now(timezone.utc) - heard_at.astimezone(timezone.utc)).total_seconds()))


def _get_station_settings() -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT callsign, ssid, beacon_interface_id, beacon_path
        FROM station_settings
        WHERE id = 1
        """
    )
    return dict(row) if row else {}
