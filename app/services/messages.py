from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app import get_version
from app.db import fetch_all, fetch_one, get_app_setting, get_connection, log_event, set_app_setting, utc_now
from app.i18n import get_app_language, get_translator
from app.services.content import get_visible_station_snapshots
from app.services.alarm_groups import (
    get_aprs_alarm_enabled,
    get_aprs_alarm_groups,
    is_configured_aprs_alarm_group,
    normalize_aprs_alarm_groups,
)
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
from app.services.notifications import queue_aprs_message_notification
from app.services.radio_activity import TRAFFIC_STATISTICS_RANGE_24H, get_traffic_direct_heard_statistics

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
MESSAGE_DEFAULT_PATH_SETTING_KEY = "messages.default_path"
MESSAGE_RECEIVE_ANY_SSID_SETTING_KEY = "messages.receive_any_ssid"
MESSAGE_TARGET_GROUPS_SETTING_KEY = "messages.target_groups"
CONVERSATION_KIND_DIRECT = "direct"
CONVERSATION_KIND_GROUP = "group"
DEFAULT_MESSAGE_TARGET_GROUPS = ("ALL", "QST", "CQ")
MESSAGE_NUMBER_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MESSAGE_MAX_LENGTH = 67
RETRY_DELAYS_SECONDS = (8, 16, 32)
MAX_TX_ATTEMPTS = 1 + len(RETRY_DELAYS_SECONDS)
FINAL_ACK_WAIT_SECONDS = 30
HEARD_FRESH_SECONDS = 10 * 60
HEARD_WARN_SECONDS = 30 * 60
QUERY_RESPONSE_DELAY_SECONDS = 5
INCOMING_UNNUMBERED_DUPLICATE_WINDOW_SECONDS = 30
OUTGOING_BURST_DUPLICATE_WINDOW_SECONDS = 5
STATION_TX_INTERNAL_MODE_SETTING_KEY = "station.tx.internal_mode"

_TNC2_RE = re.compile(r"^(?P<source>[^>]+?)\s*>\s*(?P<destination>[^,:]+?)(?:\s*,\s*(?P<path>[^:]+))?\s*:(?P<info>.*)$")
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?$")
_MESSAGE_SUFFIX_RE = re.compile(r"^(?P<text>.*?)(?:\{(?P<number>[0-9A-Z]{1,5})(?:}(?P<reply_ack>[0-9A-Z]{1,5})?)?)?$")
SUPPORTED_QUERY_TYPES = ("?APRS", "?APRSP", "?APRSS", "?APRSD", "?DX", "?APRSV", "?VER")
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
MESSAGE_PATH_OPTIONS = (
    ("", "Direct (no path)"),
    ("WIDE1-1", "WIDE1-1"),
    ("WIDE2-1", "WIDE2-1"),
    ("WIDE2-2", "WIDE2-2"),
    ("RFONLY", "RFONLY"),
    ("NOGATE", "NOGATE"),
)


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


def normalize_message_target_groups(value: Any) -> list[str]:
    """Normalize user-defined APRS message group addressees.

    APRS addressees are exactly nine characters on air.  Group names are local
    receive filters, so accept ordinary callsign-like aliases but never a
    station SSID or a bulletin address here.
    """
    if isinstance(value, list):
        raw_values = value
    else:
        raw_text = str(value or "").replace("\n", ",")
        if not raw_text.strip():
            return []
        raw_values = raw_text.split(",")
    groups: list[str] = []
    for raw_value in raw_values:
        group = str(raw_value or "").strip().upper()
        if not group:
            raise ValueError(_t("Target groups cannot contain empty entries between commas."))
        if not re.fullmatch(r"[A-Z0-9]{1,9}", group):
            raise ValueError(_t("Target groups must contain 1-9 letters or digits, separated by commas."))
        if group.startswith("BLN"):
            raise ValueError(_t("Bulletin addresses are configured separately from message target groups."))
        if group not in groups:
            groups.append(group)
    return groups


def get_message_settings() -> dict[str, Any]:
    raw_saved_path = get_app_setting(MESSAGE_DEFAULT_PATH_SETTING_KEY)
    saved_path = str(raw_saved_path or "").strip().upper()
    allowed_paths = {value for value, _label in MESSAGE_PATH_OPTIONS}
    if raw_saved_path is None:
        try:
            saved_path = str(_get_station_settings().get("beacon_path") or "").strip().upper()
        except Exception:
            saved_path = ""
    default_path = saved_path if saved_path in allowed_paths else ""
    saved_groups = get_app_setting(MESSAGE_TARGET_GROUPS_SETTING_KEY)
    if saved_groups is None:
        target_groups = list(DEFAULT_MESSAGE_TARGET_GROUPS)
    else:
        try:
            target_groups = normalize_message_target_groups(saved_groups)
        except ValueError:
            target_groups = []
    receive_any_ssid = str(get_app_setting(MESSAGE_RECEIVE_ANY_SSID_SETTING_KEY) or "").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "default_path": default_path,
        "path_options": [{"value": value, "label": label} for value, label in MESSAGE_PATH_OPTIONS],
        "receive_any_ssid": receive_any_ssid,
        "target_groups": target_groups,
    }


def get_effective_message_target_groups(
    message_target_groups: Any | None = None,
    alarm_groups: Any | None = None,
) -> list[str]:
    standard_groups = (
        get_message_settings()["target_groups"]
        if message_target_groups is None
        else normalize_message_target_groups(message_target_groups)
    )
    configured_alarm_groups = (
        get_aprs_alarm_groups()
        if alarm_groups is None
        else normalize_aprs_alarm_groups(alarm_groups)
    )
    if not get_aprs_alarm_enabled():
        configured_alarm_groups = []
    return list(dict.fromkeys([*standard_groups, *configured_alarm_groups]))


def save_message_settings(payload: dict[str, Any]) -> dict[str, Any]:
    path = normalize_aprs_path(str(payload.get("default_path") or ""))
    if path not in {value for value, _label in MESSAGE_PATH_OPTIONS}:
        raise ValueError(_t("Choose a default path from the list."))
    groups = normalize_message_target_groups(payload.get("target_groups") or [])
    receive_any_ssid = bool(payload.get("receive_any_ssid"))
    set_app_setting(MESSAGE_DEFAULT_PATH_SETTING_KEY, path)
    set_app_setting(MESSAGE_RECEIVE_ANY_SSID_SETTING_KEY, "1" if receive_any_ssid else "0")
    set_app_setting(MESSAGE_TARGET_GROUPS_SETTING_KEY, ",".join(groups))
    reconcile_effective_message_group_conversations(message_target_groups=groups)
    return get_message_settings()


def reconcile_effective_message_group_conversations(
    message_target_groups: Any | None = None,
    alarm_groups: Any | None = None,
) -> None:
    configured_alarm_groups = set(
        get_aprs_alarm_groups()
        if alarm_groups is None
        else normalize_aprs_alarm_groups(alarm_groups)
    )
    _reconcile_message_group_conversations(
        [
            group
            for group in get_effective_message_target_groups(
                message_target_groups=message_target_groups,
                alarm_groups=list(configured_alarm_groups),
            )
            if group not in configured_alarm_groups
        ]
    )


def _reconcile_message_group_conversations(target_groups: list[str]) -> None:
    """Move previously stored group traffic into its destination-group thread."""
    groups = list(
        dict.fromkeys(
            str(group or "").strip().upper()
            for group in target_groups
            if str(group or "").strip()
        )
    )
    for group in groups:
        message_rows = fetch_all(
            """
            SELECT id, conversation_id
            FROM aprs_messages
            WHERE direction = ? AND UPPER(TRIM(addressee)) = ?
            """,
            (MESSAGE_DIRECTION_RX, group),
        )
        existing_group_conversation = _get_conversation(group)
        if not message_rows and existing_group_conversation is None:
            continue
        group_conversation = create_or_update_conversation(
            group,
            conversation_kind=CONVERSATION_KIND_GROUP,
        )
        group_conversation_id = int(group_conversation["id"])
        source_conversation_ids = {
            int(row["conversation_id"])
            for row in message_rows
            if int(row["conversation_id"]) != group_conversation_id
        }
        if not source_conversation_ids:
            continue
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE aprs_messages
                SET conversation_id = ?
                WHERE direction = ? AND UPPER(TRIM(addressee)) = ? AND conversation_id <> ?
                """,
                (group_conversation_id, MESSAGE_DIRECTION_RX, group, group_conversation_id),
            )
            connection.execute(
                """
                UPDATE aprs_message_conversations
                SET updated_at = COALESCE(
                    (SELECT MAX(created_at) FROM aprs_messages WHERE conversation_id = ?),
                    updated_at
                )
                WHERE id = ?
                """,
                (group_conversation_id, group_conversation_id),
            )
            for source_conversation_id in source_conversation_ids:
                connection.execute(
                    """
                    DELETE FROM aprs_message_conversations
                    WHERE id = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM aprs_messages WHERE conversation_id = aprs_message_conversations.id
                      )
                    """,
                    (source_conversation_id,),
                )


def create_or_update_conversation(
    callsign: str,
    *,
    path: str | None = None,
    conversation_kind: str | None = None,
) -> dict[str, Any]:
    requested_kind = str(conversation_kind or "").strip().lower()
    if requested_kind and requested_kind not in {CONVERSATION_KIND_DIRECT, CONVERSATION_KIND_GROUP}:
        raise ValueError(_t("Unsupported message conversation type."))
    normalized_candidate = str(callsign or "").strip().upper()
    effective_groups = set(get_effective_message_target_groups())
    if requested_kind == CONVERSATION_KIND_GROUP or normalized_candidate in effective_groups:
        normalized_groups = normalize_aprs_alarm_groups([normalized_candidate])
        if not normalized_groups:
            raise ValueError(_t("Destination callsign is required."))
        normalized_callsign = normalized_groups[0]
    else:
        normalized_callsign = normalize_aprs_destination_callsign(normalized_candidate)
    remote_callsign, remote_ssid = split_callsign_ssid(normalized_callsign)
    timestamp = utc_now()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, remote_callsign, remote_ssid, conversation_kind, path, created_at, updated_at
            FROM aprs_message_conversations
            WHERE remote_callsign = ? AND remote_ssid = ?
            """,
            (remote_callsign, remote_ssid),
        ).fetchone()
        if row is None:
            normalized_kind = requested_kind or (
                CONVERSATION_KIND_GROUP
                if normalized_callsign in effective_groups
                else CONVERSATION_KIND_DIRECT
            )
            cursor = connection.execute(
                """
                INSERT INTO aprs_message_conversations(
                    remote_callsign, remote_ssid, conversation_kind, path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (remote_callsign, remote_ssid, normalized_kind, path or "", timestamp, timestamp),
            )
            conversation_id = int(cursor.lastrowid)
        else:
            conversation_id = int(row["id"])
            normalized_kind = requested_kind or str(row["conversation_kind"] or CONVERSATION_KIND_DIRECT)
            if path is not None or str(row["conversation_kind"] or "") != normalized_kind:
                connection.execute(
                    """
                    UPDATE aprs_message_conversations
                    SET path = ?, conversation_kind = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (str(row["path"] or "") if path is None else path, normalized_kind, timestamp, conversation_id),
                )
    conversation = fetch_one(
        """
        SELECT id, remote_callsign, remote_ssid, conversation_kind, path, created_at, updated_at
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
    normalized_candidate = str(callsign or "").strip().upper()
    if normalized_candidate in set(get_effective_message_target_groups()):
        normalized_groups = normalize_aprs_alarm_groups([normalized_candidate])
        normalized_callsign = normalized_groups[0] if normalized_groups else ""
    else:
        normalized_callsign = normalize_aprs_destination_callsign(normalized_candidate)
    remote_callsign, remote_ssid = split_callsign_ssid(normalized_callsign)
    row = fetch_one(
        """
        SELECT id, remote_callsign, remote_ssid, conversation_kind, path, created_at, updated_at
        FROM aprs_message_conversations
        WHERE remote_callsign = ? AND remote_ssid = ?
        LIMIT 1
        """,
        (remote_callsign, remote_ssid),
    )
    return dict(row) if row else None


def _resolve_auto_ack_path(*, sender: str, station_settings: dict[str, Any]) -> str:
    # The message setting is the default for automatic responses. A saved
    # conversation path remains an explicit peer-specific override.
    default_path = str(get_message_settings()["default_path"])
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
    normalized_candidate = str(callsign or "").strip().upper()
    effective_groups = set(get_effective_message_target_groups())
    if normalized_candidate in effective_groups:
        normalized_groups = normalize_aprs_alarm_groups([normalized_candidate])
        normalized_callsign = normalized_groups[0] if normalized_groups else ""
    else:
        normalized_callsign = normalize_aprs_destination_callsign(normalized_candidate)
    normalized_text = normalize_aprs_message_text(message_text)
    normalized_path = normalize_aprs_path(path)
    timestamp = utc_now()
    local_sender = _local_station_identity()
    if not local_sender:
        raise ValueError(_t("Local station callsign is required."))
    duplicate = _find_recent_outgoing_message_duplicate(
        sender=local_sender,
        addressee=normalized_callsign,
        message_text=normalized_text,
        path=normalized_path,
        timestamp=timestamp,
    )
    if duplicate is not None:
        log_event("INFO", "messages", f"Ignored duplicate outbound APRS send burst to {normalized_callsign}")
        return duplicate
    existing_conversation = _get_conversation(normalized_callsign)
    is_group = (
        normalized_callsign in effective_groups
        or str((existing_conversation or {}).get("conversation_kind") or "") == CONVERSATION_KIND_GROUP
    )
    message_kind = QUERY_MESSAGE_KIND if normalized_text.startswith("?") else DIRECT_MESSAGE_KIND
    message_number = next_message_number() if message_kind == DIRECT_MESSAGE_KIND and not is_group else None
    conversation = create_or_update_conversation(
        normalized_callsign,
        path=normalized_path,
        conversation_kind=CONVERSATION_KIND_GROUP if is_group else CONVERSATION_KIND_DIRECT,
    )
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
    message_settings = get_message_settings()
    try:
        reconcile_effective_message_group_conversations()
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to reconcile APRS message group conversations: {exc}")
    try:
        heard_by_key = _heard_station_lookup()
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to load heard station snapshot: {exc}")
        heard_by_key = {}
    try:
        conversation_rows = fetch_all(
            """
            SELECT c.id, c.remote_callsign, c.remote_ssid, c.conversation_kind, c.path, c.created_at, c.updated_at
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
    alarm_groups = set(get_aprs_alarm_groups())
    for row in conversation_rows:
        display_callsign = format_display_callsign(str(row["remote_callsign"]), str(row["remote_ssid"]))
        conversation_kind = str(row["conversation_kind"] or CONVERSATION_KIND_DIRECT)
        if local_sender and _callsign_identity_matches(display_callsign, local_sender):
            continue
        if display_callsign.strip().upper() in alarm_groups:
            continue
        conversation_id = int(row["id"])
        stored_messages = [dict(item) for item in fetch_all(
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
        messages = [
            item
            for item in stored_messages
            if str(item.get("addressee") or "").strip().upper() not in alarm_groups
        ]
        if stored_messages and not messages:
            continue
        heard_snapshot = None
        if conversation_kind != CONVERSATION_KIND_GROUP:
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
                "kind": conversation_kind,
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
    return {
        "conversations": conversations,
        "active_conversation_id": active_conversation_id,
        "composer_limit": MESSAGE_MAX_LENGTH,
        "recently_heard_window_minutes": HEARD_WARN_SECONDS // 60,
        "default_path": message_settings["default_path"],
        "message_settings": message_settings,
        "service_destinations": list(APRS_SERVICE_DESTINATIONS),
    }


def get_unread_inbox_count() -> int:
    try:
        rows = fetch_all(
            """
            SELECT c.remote_callsign, c.remote_ssid, m.addressee,
                   COUNT(m.id) AS unread_count
            FROM aprs_message_conversations c
            JOIN aprs_messages m ON m.conversation_id = c.id
            WHERE m.direction = ? AND m.is_unread = 1
            GROUP BY c.id, c.remote_callsign, c.remote_ssid, m.addressee
            """,
            (MESSAGE_DIRECTION_RX,),
        )
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to load unread inbox count: {exc}")
        return 0
    local_sender = _local_station_identity()
    alarm_groups = set(get_aprs_alarm_groups())
    unread_total = 0
    for row in rows:
        display_callsign = format_display_callsign(str(row["remote_callsign"]), str(row["remote_ssid"]))
        if local_sender and _callsign_identity_matches(display_callsign, local_sender):
            continue
        if display_callsign.strip().upper() in alarm_groups:
            continue
        if str(row["addressee"] or "").strip().upper() in alarm_groups:
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
    delete_conversations([conversation_id])


def delete_conversations(conversation_ids: list[int]) -> dict[str, int]:
    normalized_ids = sorted(
        {int(conversation_id) for conversation_id in conversation_ids if int(conversation_id) > 0}
    )
    if not normalized_ids:
        return {"conversation_count": 0, "message_count": 0}
    placeholders = ", ".join("?" for _ in normalized_ids)
    message_ids = [
        int(row["id"])
        for row in fetch_all(
            f"SELECT id FROM aprs_messages WHERE conversation_id IN ({placeholders}) ORDER BY id ASC",
            tuple(normalized_ids),
        )
    ]
    conversation_row = fetch_one(
        f"SELECT COUNT(*) AS total FROM aprs_message_conversations WHERE id IN ({placeholders})",
        tuple(normalized_ids),
    )
    for message_id in message_ids:
        cancel_pending_message_jobs(message_id)
    with get_connection() as connection:
        connection.execute(
            f"DELETE FROM aprs_message_conversations WHERE id IN ({placeholders})",
            tuple(normalized_ids),
        )
    return {
        "conversation_count": int(conversation_row["total"] or 0) if conversation_row is not None else 0,
        "message_count": len(message_ids),
    }


def clear_message_inbox() -> dict[str, int]:
    message_ids = [int(row["id"]) for row in fetch_all("SELECT id FROM aprs_messages ORDER BY id ASC")]
    conversation_row = fetch_one("SELECT COUNT(*) AS total FROM aprs_message_conversations")
    conversation_count = int(conversation_row["total"] or 0) if conversation_row is not None else 0
    for message_id in message_ids:
        cancel_pending_message_jobs(message_id)
    with get_connection() as connection:
        connection.execute("DELETE FROM aprs_message_conversations")
    return {
        "conversation_count": conversation_count,
        "message_count": len(message_ids),
    }


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


def _count_message_transmission_rounds(message_id: int) -> int:
    row = fetch_one(
        """
        SELECT COUNT(DISTINCT scheduled_at) AS round_count
        FROM outbound_jobs
        WHERE aprs_message_id = ?
          AND status IN ('processing', 'sent')
        """,
        (message_id,),
    )
    if row is None:
        return 0
    try:
        return max(0, int(row["round_count"] or 0))
    except (TypeError, ValueError, KeyError):
        return 0


def _register_outbound_message_transmission(message_id: int, job_id: int, *, allow_retry: bool) -> None:
    message = get_message(message_id)
    if message is None:
        return
    current_status = str(message.get("status") or "")
    if current_status not in {MESSAGE_STATUS_QUEUED, MESSAGE_STATUS_SENT}:
        return
    now = utc_now()
    next_attempt = max(
        int(message.get("tx_attempt_count") or 0),
        _count_message_transmission_rounds(message_id),
    )
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
    delay_index = next_attempt - 1
    expects_ack = bool(str(message.get("message_number") or "").strip())
    if allow_retry and expects_ack and next_attempt < MAX_TX_ATTEMPTS and 0 <= delay_index < len(RETRY_DELAYS_SECONDS):
        schedule_message_retry(message_id, RETRY_DELAYS_SECONDS[delay_index])


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


def mark_message_failed_if_round_exhausted(message_id: int, scheduled_at: str | None, reason: str) -> bool:
    normalized_scheduled_at = str(scheduled_at or "").strip()
    if not normalized_scheduled_at:
        mark_message_failed(message_id, reason)
        return True
    pending_row = fetch_one(
        """
        SELECT COUNT(*) AS pending
        FROM outbound_jobs
        WHERE aprs_message_id = ?
          AND scheduled_at = ?
          AND status IN ('queued', 'processing')
        """,
        (message_id, normalized_scheduled_at),
    )
    if pending_row is not None and int(pending_row["pending"] or 0) > 0:
        return False
    sent_row = fetch_one(
        """
        SELECT COUNT(*) AS sent
        FROM outbound_jobs
        WHERE aprs_message_id = ?
          AND scheduled_at = ?
          AND status = 'sent'
        """,
        (message_id, normalized_scheduled_at),
    )
    sent_count = int(sent_row["sent"] or 0) if sent_row is not None else 0
    if sent_count > 0:
        message = get_message(message_id)
        if message is not None:
            current_attempt = int(message.get("tx_attempt_count") or 0)
            delay_index = current_attempt - 1
            if 0 <= delay_index < len(RETRY_DELAYS_SECONDS) and current_attempt < MAX_TX_ATTEMPTS:
                schedule_message_retry(message_id, RETRY_DELAYS_SECONDS[delay_index])
        return False
    mark_message_failed(message_id, reason)
    return True


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
    refreshed_text = str(refreshed.get("message_text") or "").strip()
    if refreshed_text.startswith("?"):
        success, error = enqueue_query_message_job(refreshed, station_settings, trigger="manual-retry")
    else:
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
    if not str(message.get("message_number") or "").strip():
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
          AND message_number IS NOT NULL
          AND TRIM(message_number) <> ''
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


def process_incoming_tnc2_message(
    line: str,
    *,
    timestamp: str | None = None,
    allow_automatic_responses: bool = True,
    automatic_response_internal_tx_only: bool = False,
) -> None:
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

    # Configured alarm groups are consumed by the shared alert intake before
    # this message path runs.  Keep them out of user conversations and message
    # notification transports while preserving their Traffic Monitor frame.
    if is_configured_aprs_alarm_group(addressee):
        return

    local_sender = _local_station_identity()
    recipient_kind = _incoming_message_recipient_kind(addressee, local_sender)
    if recipient_kind is None:
        return

    if local_sender and _callsign_identity_matches(sender, local_sender):
        return
    received_at = _normalize_timestamp(timestamp)
    # Only the configured callsign-SSID is a true local addressee.  APRS
    # message groups and the optional same-callsign/other-SSID receive mode
    # are display filters; they must never ACK or trigger a query response.
    if recipient_kind != "local":
        suffix_match = _MESSAGE_SUFFIX_RE.fullmatch(text_field)
        if suffix_match is None:
            return
        store_incoming_message(
            sender=sender,
            addressee=addressee.upper(),
            message_text=suffix_match.group("text") or "",
            message_number=_normalize_message_number(suffix_match.group("number")),
            path=parsed["path"],
            timestamp=received_at,
            acknowledge=False,
            conversation_callsign=addressee.upper() if recipient_kind == "group" else sender,
            conversation_kind=CONVERSATION_KIND_GROUP if recipient_kind == "group" else CONVERSATION_KIND_DIRECT,
        )
        return
    if text_field.startswith("?"):
        query_text, query_number = _parse_query_text(text_field)
        if not query_text:
            return
        is_new_query = store_incoming_query(
            sender=sender,
            addressee=addressee.upper(),
            query_text=query_text,
            query_number=query_number,
            path=parsed["path"],
            timestamp=received_at,
        )
        if is_new_query and allow_automatic_responses:
            _handle_incoming_query(
                sender=sender,
                query_text=query_text,
                query_number=query_number,
                timestamp=received_at,
                automatic_response_internal_tx_only=automatic_response_internal_tx_only,
            )
        return
    ack_match = re.fullmatch(r"ack(?P<number>[0-9A-Z]{1,5})(?:}(?P<reply_ack>[0-9A-Z]{1,5})?)?", text_field, flags=re.IGNORECASE)
    reject_match = re.fullmatch(r"rej(?P<number>[0-9A-Z]{1,5})(?:}(?P<reply_ack>[0-9A-Z]{1,5})?)?", text_field, flags=re.IGNORECASE)
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
        acknowledge=allow_automatic_responses,
        automatic_response_internal_tx_only=automatic_response_internal_tx_only,
    )


def _handle_incoming_query(
    *,
    sender: str,
    query_text: str,
    query_number: str | None,
    timestamp: str,
    automatic_response_internal_tx_only: bool = False,
) -> None:
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
            internal_tx_only=automatic_response_internal_tx_only,
        )
        return
    if query_type == "?APRSP":
        success, error = enqueue_automatic_query_position_response(
            sender=sender,
            station_settings=station_settings,
            trigger="query-aprsp",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
            internal_tx_only=automatic_response_internal_tx_only,
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
            internal_tx_only=automatic_response_internal_tx_only,
        )
        if not success:
            log_event("INFO", "messages", f"Ignored ?APRSS from {sender}: {error or 'status unavailable'}")
        return
    if query_type == "?APRSD":
        enqueue_automatic_query_text_response(
            sender=sender,
            station_settings=station_settings,
            message_text=_build_query_direct_stations_text(),
            trigger="query-aprsd",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
            internal_tx_only=automatic_response_internal_tx_only,
        )
        return
    if query_type == "?DX":
        enqueue_automatic_query_text_response(
            sender=sender,
            station_settings=station_settings,
            message_text=_build_query_dx_text(),
            trigger="query-dx",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
            internal_tx_only=automatic_response_internal_tx_only,
        )
        return
    if query_type in {"?APRSV", "?VER"}:
        enqueue_automatic_query_text_response(
            sender=sender,
            station_settings=station_settings,
            message_text=f"APRSBox {get_version()}",
            trigger="query-version",
            scheduled_for=scheduled_for,
            timestamp=timestamp,
            internal_tx_only=automatic_response_internal_tx_only,
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
    internal_tx_only: bool = False,
) -> None:
    response_text = normalize_aprs_message_text(message_text)
    response_path = str(get_message_settings()["default_path"])
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
        internal_tx_only=internal_tx_only,
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
    internal_tx_only: bool = False,
) -> tuple[bool, str | None]:
    response_text = _build_query_position_text(station_settings)
    response_path = str(get_message_settings()["default_path"])
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
        beacon_path_override=response_path,
        scheduled_for=scheduled_for,
        internal_tx_only=internal_tx_only,
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
    internal_tx_only: bool = False,
) -> tuple[bool, str | None]:
    response_text = _build_query_status_text(station_settings)
    response_path = str(get_message_settings()["default_path"])
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
        path=response_path,
        scheduled_for=scheduled_for,
        internal_tx_only=internal_tx_only,
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
    acknowledge: bool = True,
    automatic_response_internal_tx_only: bool = False,
    conversation_callsign: str | None = None,
    conversation_kind: str = CONVERSATION_KIND_DIRECT,
) -> None:
    if is_configured_aprs_alarm_group(addressee):
        return
    station_settings = _get_station_settings()
    ack_path = _resolve_auto_ack_path(sender=sender, station_settings=station_settings)
    conversation = create_or_update_conversation(
        conversation_callsign or sender,
        conversation_kind=conversation_kind,
    )
    duplicate_unnumbered = (
        not message_number
        and _has_recent_unnumbered_incoming_message_duplicate(
            sender=sender,
            addressee=addressee,
            message_text=message_text,
            timestamp=timestamp,
        )
    )
    existing = None
    if message_number:
        existing = fetch_one(
            """
            SELECT id
            FROM aprs_messages
            WHERE direction = ?
              AND sender = ?
              AND message_number = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (MESSAGE_DIRECTION_RX, sender, message_number),
        )
    if existing is None and not duplicate_unnumbered:
        with get_connection() as connection:
            cursor = connection.execute(
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
            message_id = int(cursor.lastrowid)
        log_event("INFO", "messages", f"Stored incoming APRS message from {sender} to {addressee}")
        queue_aprs_message_notification(
            sender=sender,
            destination=addressee,
            text=message_text,
            message_id=message_id,
            message_number=message_number,
            timestamp=timestamp,
        )
    ack_number_for_tx = _normalize_ack_number(ack_number if ack_number is not None else message_number)
    if not acknowledge or not ack_number_for_tx:
        return
    enqueue_ack_job(
        sender,
        ack_number_for_tx,
        station_settings,
        path=ack_path,
        trigger="ack-now",
        internal_tx_only=automatic_response_internal_tx_only,
    )
    enqueue_ack_job(
        sender,
        ack_number_for_tx,
        station_settings,
        path=ack_path,
        trigger="ack-delayed",
        scheduled_for=datetime.now(timezone.utc) + timedelta(seconds=FINAL_ACK_WAIT_SECONDS),
        internal_tx_only=automatic_response_internal_tx_only,
    )


def store_incoming_query(
    *,
    sender: str,
    addressee: str,
    query_text: str,
    query_number: str | None,
    path: str,
    timestamp: str,
) -> bool:
    conversation = create_or_update_conversation(sender, conversation_kind=CONVERSATION_KIND_DIRECT)
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
        # multiple times through nearby digipeaters. APRS queries are one-shot
        # transmissions and are never acknowledged, so duplicates are dropped silently.
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
    return True


def store_incoming_bulletin(
    *,
    sender: str,
    addressee: str,
    message_text: str,
    path: str,
    timestamp: str,
) -> None:
    conversation = create_or_update_conversation(sender, conversation_kind=CONVERSATION_KIND_DIRECT)
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
    conversation = create_or_update_conversation(sender, conversation_kind=CONVERSATION_KIND_DIRECT)
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


def _parse_query_text(text_field: str) -> tuple[str, str | None]:
    suffix_match = _MESSAGE_SUFFIX_RE.fullmatch(text_field)
    if suffix_match is None:
        return "", None
    query_text = str(suffix_match.group("text") or "").strip()
    message_number = _normalize_message_number(suffix_match.group("number"))
    return query_text, message_number


def _normalize_ack_number(value: str | None) -> str | None:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return None
    if not re.fullmatch(r"[0-9A-Z]{1,5}", normalized):
        return None
    return normalized


def _normalize_message_number(value: str | None) -> str | None:
    normalized = _normalize_ack_number(value)
    if normalized is None:
        return None
    if len(normalized) == 1:
        return f"0{normalized}"
    return normalized


def _find_recent_outgoing_message_duplicate(
    *,
    sender: str,
    addressee: str,
    message_text: str,
    path: str,
    timestamp: str,
    window_seconds: int = OUTGOING_BURST_DUPLICATE_WINDOW_SECONDS,
) -> dict[str, Any] | None:
    normalized_sender = str(sender or "").strip().upper()
    normalized_addressee = str(addressee or "").strip().upper()
    normalized_text = str(message_text or "")
    normalized_path = normalize_aprs_path(path)
    if not normalized_sender or not normalized_addressee or not normalized_text:
        return None
    reference_timestamp = _parse_iso_timestamp_utc(timestamp) or datetime.now(timezone.utc)
    window_seconds = max(1, int(window_seconds))
    window_start = (reference_timestamp - timedelta(seconds=window_seconds)).replace(microsecond=0).isoformat()
    window_end = reference_timestamp.replace(microsecond=0).isoformat()
    row = fetch_one(
        """
        SELECT id
        FROM aprs_messages
        WHERE direction = ?
          AND sender = ?
          AND addressee = ?
          AND message_text = ?
          AND path = ?
          AND status IN (?, ?, ?, ?)
          AND created_at >= ?
          AND created_at <= ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            MESSAGE_DIRECTION_TX,
            normalized_sender,
            normalized_addressee,
            normalized_text,
            normalized_path,
            MESSAGE_STATUS_QUEUED,
            MESSAGE_STATUS_SENT,
            MESSAGE_STATUS_ACKED,
            MESSAGE_STATUS_REJECTED,
            window_start,
            window_end,
        ),
    )
    if row is None:
        return None
    return get_message(int(row["id"]))


def _has_recent_unnumbered_incoming_message_duplicate(
    *,
    sender: str,
    addressee: str,
    message_text: str,
    timestamp: str,
    window_seconds: int = INCOMING_UNNUMBERED_DUPLICATE_WINDOW_SECONDS,
) -> bool:
    normalized_sender = str(sender or "").strip().upper()
    normalized_addressee = str(addressee or "").strip().upper()
    normalized_text = str(message_text or "")
    if not normalized_sender or not normalized_addressee or not normalized_text:
        return False
    reference_timestamp = _parse_iso_timestamp_utc(timestamp) or datetime.now(timezone.utc)
    window_seconds = max(1, int(window_seconds))
    window_start = (reference_timestamp - timedelta(seconds=window_seconds)).replace(microsecond=0).isoformat()
    window_end = reference_timestamp.replace(microsecond=0).isoformat()
    row = fetch_one(
        """
        SELECT id
        FROM aprs_messages
        WHERE direction = ?
          AND sender = ?
          AND addressee = ?
          AND message_number IS NULL
          AND message_text = ?
          AND created_at >= ?
          AND created_at <= ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            MESSAGE_DIRECTION_RX,
            normalized_sender,
            normalized_addressee,
            normalized_text,
            window_start,
            window_end,
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


def _build_query_direct_stations_text() -> str:
    direct_station_keys = _query_direct_station_keys(limit=500)
    if not direct_station_keys:
        return "Directs= none"
    return _build_query_callsign_list_message(prefix="Directs= ", callsigns=direct_station_keys, empty_fallback="Directs= none")


def _build_query_dx_text() -> str:
    distance_rows = _query_distance_station_rows(limit=500)
    if not distance_rows:
        return "DX: D none A none"
    direct_keys = set(_query_direct_station_keys(limit=500))
    farthest_direct = max((row for row in distance_rows if row["callsign"] in direct_keys), key=lambda row: row["distance_km"], default=None)
    farthest_any = max(distance_rows, key=lambda row: row["distance_km"], default=None)
    direct_part = _format_dx_part("D", farthest_direct)
    any_part = _format_dx_part("A", farthest_any)
    return f"DX: {direct_part} {any_part}"


def _build_query_callsign_list_message(*, prefix: str, callsigns: list[str], empty_fallback: str) -> str:
    if not callsigns:
        return empty_fallback
    normalized_prefix = str(prefix or "")
    selected: list[str] = []
    for callsign in callsigns:
        candidate = f"{normalized_prefix}{' '.join([*selected, callsign])}"
        if len(candidate) > MESSAGE_MAX_LENGTH:
            break
        selected.append(callsign)
    if not selected:
        return empty_fallback
    message = f"{normalized_prefix}{' '.join(selected)}"
    if len(selected) < len(callsigns):
        ellipsis_candidate = f"{message} ..."
        if len(ellipsis_candidate) <= MESSAGE_MAX_LENGTH:
            return ellipsis_candidate
    return message


def _format_dx_part(label: str, row: dict[str, Any] | None) -> str:
    normalized_label = str(label or "").strip().upper() or "?"
    if row is None:
        return f"{normalized_label} none"
    callsign = str(row.get("callsign") or "").strip().upper()
    distance = _format_distance_km_compact(row.get("distance_km"))
    if not callsign or not distance:
        return f"{normalized_label} none"
    return f"{normalized_label} {callsign} {distance}km"


def _format_distance_km_compact(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{numeric:.1f}".rstrip("0").rstrip(".")


def _query_direct_station_keys(*, limit: int) -> list[str]:
    normalized_limit = max(1, int(limit or 0))
    try:
        payload = get_traffic_direct_heard_statistics(
            range_value=TRAFFIC_STATISTICS_RANGE_24H,
            top_limit=normalized_limit,
        )
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to load direct-heard statistics for APRSD query: {exc}")
        return []
    except Exception as exc:
        _safe_messages_warning(f"Failed to build APRSD query response: {exc}")
        return []
    items = list(payload.get("items") or [])
    callsigns: list[str] = []
    seen: set[str] = set()
    for item in items:
        callsign = str(item.get("key") or "").strip().upper()
        if not callsign or callsign in seen or _CALLSIGN_RE.fullmatch(callsign) is None:
            continue
        seen.add(callsign)
        callsigns.append(callsign)
    return callsigns


def _query_distance_station_rows(*, limit: int) -> list[dict[str, Any]]:
    normalized_limit = max(1, int(limit or 0))
    try:
        snapshots = get_visible_station_snapshots(limit=normalized_limit)
    except sqlite3.Error as exc:
        _safe_messages_warning(f"Failed to load station snapshots for ?DX query: {exc}")
        return []
    except Exception as exc:
        _safe_messages_warning(f"Failed to build ?DX station snapshot list: {exc}")
        return []
    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        callsign = str(snapshot.get("display_callsign") or "").strip().upper()
        if not callsign or _CALLSIGN_RE.fullmatch(callsign) is None:
            continue
        distance_raw = snapshot.get("distance_km")
        try:
            distance_km = float(distance_raw)
        except (TypeError, ValueError):
            continue
        rows.append({"callsign": callsign, "distance_km": distance_km})
    return rows


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
        "sender": str(row.get("sender") or ""),
        "addressee": str(row.get("addressee") or ""),
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
        SELECT callsign, ssid, beacon_interface_id, beacon_tx_scope, beacon_path,
               latitude, longitude, symbol_table, symbol_code,
               beacon_comment, status_text
        FROM station_settings
        WHERE id = 1
        """
    )
    if row is None:
        return {}
    result = dict(row)
    internal_mode = str(get_app_setting(STATION_TX_INTERNAL_MODE_SETTING_KEY) or "").strip().lower()
    result["beacon_internal_tx"] = internal_mode in {"1", "true", "yes", "on"}
    return result


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


def _incoming_message_recipient_kind(addressee: str, local_sender: str) -> str | None:
    normalized_addressee = _canonical_callsign_identity(addressee)
    normalized_local = _canonical_callsign_identity(local_sender)
    if not normalized_addressee or not normalized_local:
        return None
    if normalized_addressee == normalized_local:
        return "local"

    local_callsign, _local_ssid = split_callsign_ssid(normalized_local)
    addressee_callsign, _addressee_ssid = split_callsign_ssid(normalized_addressee)
    if get_message_settings()["receive_any_ssid"] and local_callsign == addressee_callsign:
        return "other_ssid"

    if normalized_addressee in set(get_effective_message_target_groups()):
        return "group"
    return None


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
