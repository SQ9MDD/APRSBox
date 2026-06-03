from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import re
import sqlite3
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.db import fetch_all, fetch_one, get_connection, get_app_setting, log_event, set_app_setting, utc_now
from app.services.content import get_station_settings, get_visible_station_snapshots
from app.services.wx import get_wx_config

NOTIFICATION_TRANSPORT_TYPE_WEBHOOK = "webhook"
NOTIFICATION_TRANSPORT_TYPE_TELEGRAM = "telegram"
NOTIFICATION_MESSAGES_ENABLED_KEY = "messages_enabled"
NOTIFICATION_MESSAGES_INCLUDE_CONTENT_KEY = "messages_include_content"
NOTIFICATION_RADAR_ENABLED_KEY = "radar_enabled"
NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT = 5

_NOTIFICATION_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aprsbox-notify")


def _t(value: object) -> str:
    return str(value or "")


def ensure_notification_defaults() -> None:
    for key in (
        NOTIFICATION_MESSAGES_ENABLED_KEY,
        NOTIFICATION_MESSAGES_INCLUDE_CONTENT_KEY,
        NOTIFICATION_RADAR_ENABLED_KEY,
    ):
        if get_app_setting(key) is None:
            set_app_setting(key, "0")


def get_notification_settings() -> dict[str, bool]:
    ensure_notification_defaults()
    return {
        "messages_enabled": _setting_flag(get_app_setting(NOTIFICATION_MESSAGES_ENABLED_KEY)),
        "messages_include_content": _setting_flag(get_app_setting(NOTIFICATION_MESSAGES_INCLUDE_CONTENT_KEY)),
        "radar_enabled": _setting_flag(get_app_setting(NOTIFICATION_RADAR_ENABLED_KEY)),
    }


def save_notification_settings(payload: dict[str, Any]) -> None:
    ensure_notification_defaults()
    set_app_setting(NOTIFICATION_MESSAGES_ENABLED_KEY, "1" if _setting_flag(payload.get("messages_enabled")) else "0")
    set_app_setting(
        NOTIFICATION_MESSAGES_INCLUDE_CONTENT_KEY,
        "1" if _setting_flag(payload.get("messages_include_content")) else "0",
    )
    set_app_setting(NOTIFICATION_RADAR_ENABLED_KEY, "1" if _setting_flag(payload.get("radar_enabled")) else "0")
    log_event("INFO", "notifications", "Updated notification settings")


def safe_save_notification_settings(payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        save_notification_settings(payload)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def list_notification_transports() -> list[dict[str, Any]]:
    ensure_notification_defaults()
    rows = fetch_all(
        """
        SELECT *
        FROM notification_transports
        ORDER BY name COLLATE NOCASE ASC, id ASC
        """
    )
    return [_serialize_transport_row(dict(row)) for row in rows]


def get_notification_transport(transport_id: int | None) -> dict[str, Any] | None:
    if transport_id is None:
        return None
    row = fetch_one("SELECT * FROM notification_transports WHERE id = ?", (transport_id,))
    return _serialize_transport_row(dict(row)) if row is not None else None


def save_notification_transport(payload: dict[str, Any], *, transport_id: int | None = None) -> int:
    normalized = _normalize_transport_payload(payload, transport_id=transport_id)
    timestamp = utc_now()
    if transport_id is None:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO notification_transports(
                    name, transport_type, enabled, url, secret_header_name, secret_token,
                    bot_token, chat_id, timeout_s, last_test_status, last_test_error, last_test_at,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', NULL, ?, ?)
                """,
                (
                    normalized["name"],
                    normalized["transport_type"],
                    normalized["enabled"],
                    normalized["url"],
                    normalized["secret_header_name"],
                    normalized["secret_token"],
                    normalized["bot_token"],
                    normalized["chat_id"],
                    normalized["timeout_s"],
                    timestamp,
                    timestamp,
                ),
            )
            transport_id = int(cursor.lastrowid)
    else:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE notification_transports
                SET name = :name,
                    transport_type = :transport_type,
                    enabled = :enabled,
                    url = :url,
                    secret_header_name = :secret_header_name,
                    secret_token = :secret_token,
                    bot_token = :bot_token,
                    chat_id = :chat_id,
                    timeout_s = :timeout_s,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                {**normalized, "id": transport_id, "updated_at": timestamp},
            )
    log_event("INFO", "notifications", f"Saved notification transport {normalized['name']}")
    return transport_id


def safe_save_notification_transport(payload: dict[str, Any], *, transport_id: int | None = None) -> tuple[bool, str | None, int | None]:
    try:
        saved_id = save_notification_transport(payload, transport_id=transport_id)
    except (ValueError, sqlite3.IntegrityError) as exc:
        return False, str(exc), transport_id
    return True, None, saved_id


def delete_notification_transport(transport_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM notification_transports WHERE id = ?", (transport_id,))
    log_event("INFO", "notifications", f"Deleted notification transport {transport_id}")


def test_notification_transport(transport_id: int) -> dict[str, Any]:
    transport = get_notification_transport(transport_id)
    if transport is None:
        return {"ok": False, "error": "Transport not found."}
    event = build_test_notification_event()
    ok, error = _deliver_event_to_transport(transport, event)
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE notification_transports
            SET last_test_status = ?,
                last_test_error = ?,
                last_test_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            ("ok" if ok else "error", error or "", timestamp, timestamp, transport_id),
        )
    if ok:
        log_event("INFO", "notifications", f"Notification transport {transport['name']} test succeeded")
        return {"ok": True}
    log_event("WARNING", "notifications", f"Notification transport {transport['name']} test failed: {error or 'unknown error'}")
    return {"ok": False, "error": error or "Notification test failed."}


def list_notification_radar_rules() -> list[dict[str, Any]]:
    ensure_notification_defaults()
    rows = fetch_all(
        """
        SELECT *
        FROM notification_radar_rules
        ORDER BY id ASC
        """
    )
    return [_serialize_radar_rule_row(dict(row)) for row in rows]


def get_notification_radar_rule(rule_id: int | None) -> dict[str, Any] | None:
    if rule_id is None:
        return None
    row = fetch_one("SELECT * FROM notification_radar_rules WHERE id = ?", (rule_id,))
    return _serialize_radar_rule_row(dict(row)) if row is not None else None


def save_notification_radar_rule(payload: dict[str, Any], *, rule_id: int | None = None) -> int:
    normalized = _normalize_radar_rule_payload(payload)
    timestamp = utc_now()
    if rule_id is None:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO notification_radar_rules(enabled, pattern, distance_m, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized["enabled"], normalized["pattern"], normalized["distance_m"], timestamp, timestamp),
            )
            rule_id = int(cursor.lastrowid)
    else:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE notification_radar_rules
                SET enabled = :enabled,
                    pattern = :pattern,
                    distance_m = :distance_m,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                {**normalized, "id": rule_id, "updated_at": timestamp},
            )
    log_event("INFO", "notifications", f"Saved radar rule {normalized['pattern']}")
    return rule_id


def safe_save_notification_radar_rule(payload: dict[str, Any], *, rule_id: int | None = None) -> tuple[bool, str | None, int | None]:
    try:
        saved_id = save_notification_radar_rule(payload, rule_id=rule_id)
    except (ValueError, sqlite3.IntegrityError) as exc:
        return False, str(exc), rule_id
    return True, None, saved_id


def delete_notification_radar_rule(rule_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM notification_radar_rules WHERE id = ?", (rule_id,))
    log_event("INFO", "notifications", f"Deleted radar rule {rule_id}")


def get_notifications_page_data(*, edit_transport_id: int | None = None, edit_rule_id: int | None = None) -> dict[str, Any]:
    ensure_notification_defaults()
    transport = get_notification_transport(edit_transport_id)
    rule = get_notification_radar_rule(edit_rule_id)
    transports = list_notification_transports()
    rules = list_notification_radar_rules()
    settings = get_notification_settings()
    return {
        "notification_settings": settings,
        "notification_transports": transports,
        "notification_transport_type_options": [
            {"value": NOTIFICATION_TRANSPORT_TYPE_WEBHOOK, "label": "Webhook"},
            {"value": NOTIFICATION_TRANSPORT_TYPE_TELEGRAM, "label": "Telegram"},
        ],
        "notification_transport_form": _build_transport_form(transport),
        "notification_radar_rules": rules,
        "notification_radar_rule_form": _build_radar_rule_form(rule),
        "notification_has_transports": bool(transports),
        "notification_has_radar_rules": bool(rules),
    }


def build_aprs_message_event(
    *,
    sender: str,
    destination: str,
    text: str,
    include_content: bool,
    message_id: int | None = None,
    message_number: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    normalized_sender = str(sender or "").strip().upper()
    normalized_destination = str(destination or "").strip().upper()
    content = str(text or "")
    safe_message = f"APRS message from {normalized_sender or 'unknown'}"
    data: dict[str, Any] = {
        "source": normalized_sender,
        "destination": normalized_destination,
        "text": content if include_content else None,
        "content_included": bool(include_content),
    }
    if message_id is not None:
        data["message_id"] = int(message_id)
    if message_number:
        data["message_number"] = str(message_number)
    return {
        "event_type": "aprs_message",
        "timestamp": timestamp or utc_now(),
        "node": _notification_node_payload(),
        "message": safe_message,
        "data": data,
    }


def build_radar_station_match_event(
    *,
    station: str,
    matched_rule: dict[str, Any],
    distance_m: int | None,
    threshold_m: int,
    latitude: str | None,
    longitude: str | None,
    reference_latitude: str | None,
    reference_longitude: str | None,
    reference_station: str,
    reference_my_station_id: int = 1,
    timestamp: str | None = None,
) -> dict[str, Any]:
    station_name = str(station or "").strip().upper()
    distance_part = f"{distance_m} m" if distance_m is not None else "unknown distance"
    rule_pattern = str(matched_rule.get("pattern") or "").strip().upper() or "*"
    message = f"Radar: {station_name or 'unknown'} is nearby ({distance_part}, rule {rule_pattern})"
    return {
        "event_type": "radar_station_match",
        "timestamp": timestamp or utc_now(),
        "node": _notification_node_payload(),
        "message": message,
        "data": {
            "station": station_name,
            "matched_rule": {
                "id": int(matched_rule["id"]),
                "pattern": rule_pattern,
            },
            "distance_m": distance_m,
            "threshold_m": int(threshold_m),
            "latitude": latitude,
            "longitude": longitude,
            "reference_my_station_id": int(reference_my_station_id),
            "reference_station": reference_station,
            "reference_latitude": reference_latitude,
            "reference_longitude": reference_longitude,
        },
    }


def build_test_notification_event(*, timestamp: str | None = None) -> dict[str, Any]:
    return {
        "event_type": "notification_test",
        "timestamp": timestamp or utc_now(),
        "node": _notification_node_payload(),
        "message": "APRSBox notification test",
        "data": {},
    }


def queue_aprs_message_notification(
    *,
    sender: str,
    destination: str,
    text: str,
    message_id: int | None = None,
    message_number: str | None = None,
    timestamp: str | None = None,
) -> None:
    settings = get_notification_settings()
    if not settings["messages_enabled"]:
        return
    event = build_aprs_message_event(
        sender=sender,
        destination=destination,
        text=text,
        include_content=settings["messages_include_content"],
        message_id=message_id,
        message_number=message_number,
        timestamp=timestamp,
    )
    _NOTIFICATION_EXECUTOR.submit(_send_notification_event, event)


def queue_radar_notifications(*, timestamp: str | None = None) -> None:
    settings = get_notification_settings()
    events = evaluate_radar_notifications(timestamp=timestamp)
    if not settings["radar_enabled"]:
        return
    for event in events:
        _NOTIFICATION_EXECUTOR.submit(_send_notification_event, event)


def evaluate_radar_notifications(*, timestamp: str | None = None) -> list[dict[str, Any]]:
    ensure_notification_defaults()
    rules = list_notification_radar_rules()
    if not rules:
        return []

    station_settings = get_station_settings()
    ignored_station_keys = _notification_radar_ignored_station_keys(station_settings)
    reference_latitude = _parse_coordinate(station_settings.get("latitude"))
    reference_longitude = _parse_coordinate(station_settings.get("longitude"))
    reference_station = _reference_station_label(station_settings)
    snapshots = [
        snapshot
        for snapshot in get_visible_station_snapshots(limit=500)
        if str(snapshot.get("origin") or "").strip().lower() == "heard"
    ]

    state_rows = fetch_all(
        """
        SELECT rule_id, station_key, is_inside, last_matched_at
        FROM notification_radar_state
        """
    )
    state_by_rule: dict[int, dict[str, dict[str, Any]]] = {}
    for row in state_rows:
        rule_id = int(row["rule_id"])
        state_by_rule.setdefault(rule_id, {})[str(row["station_key"]).casefold()] = dict(row)

    now = timestamp or utc_now()
    events: list[dict[str, Any]] = []
    with get_connection() as connection:
        for rule in rules:
            rule_id = int(rule["id"])
            rule_pattern = str(rule.get("pattern") or "").strip().upper()
            threshold_m = int(rule.get("distance_m") or 0)
            current_matches: dict[str, dict[str, Any]] = {}
            for snapshot in snapshots:
                station_key = str(snapshot.get("display_callsign") or snapshot.get("callsign") or "").strip().upper()
                if not station_key or not pattern_matches_callsign(rule_pattern, station_key):
                    continue
                if station_key.casefold() in ignored_station_keys:
                    continue
                distance_m = _snapshot_distance_m(snapshot, reference_latitude, reference_longitude)
                if threshold_m > 0 and (distance_m is None or distance_m > threshold_m):
                    continue
                current_matches[station_key.casefold()] = {
                    "snapshot": snapshot,
                    "distance_m": distance_m,
                    "station_key": station_key,
                }

            previous_states = state_by_rule.get(rule_id, {})
            current_inside_keys = set(current_matches)
            previous_inside_keys = {
                station_key
                for station_key, row in previous_states.items()
                if bool(int(row.get("is_inside") or 0))
            }

            for station_key, match in current_matches.items():
                was_inside = station_key in previous_inside_keys
                _upsert_radar_state(
                    connection,
                    rule_id=rule_id,
                    station_key=match["station_key"],
                    is_inside=1,
                    last_matched_at=now,
                )
                if not was_inside and bool(int(rule.get("enabled") or 0)):
                    snapshot = match["snapshot"]
                    events.append(
                        build_radar_station_match_event(
                            station=match["station_key"],
                            matched_rule=rule,
                            distance_m=match["distance_m"],
                            threshold_m=threshold_m,
                            latitude=str(snapshot.get("latitude") or "") or None,
                            longitude=str(snapshot.get("longitude") or "") or None,
                            reference_latitude=reference_latitude,
                            reference_longitude=reference_longitude,
                            reference_station=reference_station,
                            timestamp=now,
                        )
                    )

            for station_key in previous_inside_keys - current_inside_keys:
                _upsert_radar_state(
                    connection,
                    rule_id=rule_id,
                    station_key=previous_states[station_key]["station_key"] if station_key in previous_states else station_key,
                    is_inside=0,
                    last_matched_at=None,
                )
    return events


def pattern_matches_callsign(pattern: str, callsign: str) -> bool:
    normalized_pattern = normalize_notification_pattern(pattern)
    normalized_callsign = str(callsign or "").strip().upper()
    if not normalized_pattern or not normalized_callsign:
        return False
    if normalized_pattern == "*":
        return True
    escaped = re.escape(normalized_pattern).replace(r"\*", ".*")
    return re.fullmatch(escaped, normalized_callsign) is not None


def normalize_notification_pattern(value: str) -> str:
    return str(value or "").strip().upper()


def normalize_notification_distance_m(value: Any) -> int:
    raw = "" if value is None else str(value).strip()
    if not raw:
        raise ValueError("Distance is required.")
    try:
        distance_m = int(raw)
    except ValueError as exc:
        raise ValueError("Distance must be a whole number of meters.") from exc
    if distance_m < 0:
        raise ValueError("Distance must be zero or greater.")
    return distance_m


def _send_notification_event(event: dict[str, Any]) -> None:
    if not isinstance(event, dict):
        return
    event_type = str(event.get("event_type") or "").strip()
    settings = get_notification_settings()
    if event_type == "aprs_message" and not settings["messages_enabled"]:
        return
    if event_type == "radar_station_match" and not settings["radar_enabled"]:
        return
    transports = [transport for transport in list_notification_transports() if bool(transport.get("enabled"))]
    for transport in transports:
        ok, error = _deliver_event_to_transport(transport, event)
        if not ok:
            log_event(
                "WARNING",
                "notifications",
                f"Notification transport {transport['name']} failed for {event_type}: {error or 'unknown error'}",
            )


def _deliver_event_to_transport(transport: dict[str, Any], event: dict[str, Any]) -> tuple[bool, str | None]:
    transport_type = str(transport.get("transport_type") or "").strip().lower()
    timeout_s = max(1, min(60, int(transport.get("timeout_s") or NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT)))
    if transport_type == NOTIFICATION_TRANSPORT_TYPE_TELEGRAM:
        bot_token = str(transport.get("bot_token") or "").strip()
        chat_id = str(transport.get("chat_id") or "").strip()
        if not bot_token or not chat_id:
            return False, "Telegram transport is missing bot token or chat ID."
        text = str(event.get("message") or "").strip()
        data = dict(event.get("data") or {})
        content = str(data.get("text") or "").strip()
        if content:
            text = f"{text}\n{content}" if text else content
        payload = {
            "chat_id": chat_id,
            "text": text or "APRSBox notification",
        }
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        return _send_json_request(url, payload, timeout_s=timeout_s)

    if transport_type == NOTIFICATION_TRANSPORT_TYPE_WEBHOOK:
        url = str(transport.get("url") or "").strip()
        if not url:
            return False, "Webhook URL is missing."
        payload = dict(event)
        headers: dict[str, str] = {}
        header_name = str(transport.get("secret_header_name") or "").strip()
        secret_token = str(transport.get("secret_token") or "").strip()
        if header_name and secret_token:
            headers[header_name] = secret_token
        return _send_json_request(url, payload, timeout_s=timeout_s, headers=headers)

    return False, f"Unsupported transport type: {transport_type or 'unknown'}"


def _send_json_request(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: int,
    headers: dict[str, str] | None = None,
) -> tuple[bool, str | None]:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_s) as response:
            response.read()
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except URLError:
        return False, "Request failed"
    except TimeoutError:
        return False, "Request timed out"
    return True, None


def _serialize_transport_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    item = dict(row)
    item["transport_type_label"] = {
        NOTIFICATION_TRANSPORT_TYPE_WEBHOOK: "Webhook",
        NOTIFICATION_TRANSPORT_TYPE_TELEGRAM: "Telegram",
    }.get(str(item.get("transport_type") or "").strip().lower(), str(item.get("transport_type") or ""))
    item["enabled"] = bool(item.get("enabled"))
    item["timeout_s"] = int(item.get("timeout_s") or NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT)
    item["bot_token_masked"] = _mask_secret(str(item.get("bot_token") or ""))
    item["secret_token_masked"] = _mask_secret(str(item.get("secret_token") or ""))
    return item


def _serialize_radar_rule_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["pattern"] = str(item.get("pattern") or "").strip().upper()
    item["distance_m"] = int(item.get("distance_m") or 0)
    return item


def _build_transport_form(transport: dict[str, Any] | None) -> dict[str, Any]:
    item = _serialize_transport_row(transport or {})
    return {
        "id": item.get("id"),
        "name": str(item.get("name") or ""),
        "transport_type": str(item.get("transport_type") or NOTIFICATION_TRANSPORT_TYPE_WEBHOOK),
        "enabled": bool(item.get("enabled")),
        "url": str(item.get("url") or ""),
        "secret_header_name": str(item.get("secret_header_name") or ""),
        "secret_token": "",
        "bot_token": "",
        "chat_id": str(item.get("chat_id") or ""),
        "timeout_s": str(item.get("timeout_s") or NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT),
    }


def _build_radar_rule_form(rule: dict[str, Any] | None) -> dict[str, Any]:
    item = _serialize_radar_rule_row(rule or {})
    return {
        "id": item.get("id"),
        "enabled": bool(item.get("enabled")),
        "pattern": str(item.get("pattern") or ""),
        "distance_m": str(item.get("distance_m") or 0),
    }


def _normalize_transport_payload(payload: dict[str, Any], *, transport_id: int | None) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Transport name is required.")
    transport_type = str(payload.get("transport_type") or "").strip().lower()
    if transport_type not in {NOTIFICATION_TRANSPORT_TYPE_WEBHOOK, NOTIFICATION_TRANSPORT_TYPE_TELEGRAM}:
        raise ValueError("Transport type must be Telegram or Generic Webhook.")
    enabled = _setting_flag(payload.get("enabled"))
    timeout_s = _normalize_timeout_seconds(payload.get("timeout_s"))
    existing = get_notification_transport(transport_id) if transport_id is not None else None

    url = str(payload.get("url") or "").strip()
    secret_header_name = str(payload.get("secret_header_name") or "").strip()
    secret_token = str(payload.get("secret_token") or "").strip()
    bot_token = str(payload.get("bot_token") or "").strip()
    chat_id = str(payload.get("chat_id") or "").strip()

    if existing is not None:
        if not url and str(existing.get("url") or "").strip():
            url = str(existing.get("url") or "").strip()
        if not secret_header_name and str(existing.get("secret_header_name") or "").strip():
            secret_header_name = str(existing.get("secret_header_name") or "").strip()
        if not secret_token and str(existing.get("secret_token") or "").strip():
            secret_token = str(existing.get("secret_token") or "").strip()
        if not bot_token and str(existing.get("bot_token") or "").strip():
            bot_token = str(existing.get("bot_token") or "").strip()
        if not chat_id and str(existing.get("chat_id") or "").strip():
            chat_id = str(existing.get("chat_id") or "").strip()

    if transport_type == NOTIFICATION_TRANSPORT_TYPE_TELEGRAM:
        if enabled and not bot_token:
            raise ValueError("Telegram transport requires bot_token when enabled.")
        if enabled and not chat_id:
            raise ValueError("Telegram transport requires chat_id when enabled.")
        url = ""
        secret_header_name = ""
        secret_token = ""
    else:
        if enabled and not url:
            raise ValueError("Webhook transport requires URL when enabled.")
        if url:
            _validate_http_url(url)
        bot_token = ""
        chat_id = ""

    return {
        "name": name,
        "transport_type": transport_type,
        "enabled": 1 if enabled else 0,
        "url": url,
        "secret_header_name": secret_header_name,
        "secret_token": secret_token,
        "bot_token": bot_token,
        "chat_id": chat_id,
        "timeout_s": timeout_s,
    }


def _normalize_timeout_seconds(value: Any) -> int:
    raw = str(value or "").strip()
    if not raw:
        return NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT
    try:
        timeout = int(raw)
    except ValueError as exc:
        raise ValueError("Timeout must be a whole number of seconds.") from exc
    if timeout < 1 or timeout > 60:
        raise ValueError("Timeout must be between 1 and 60 seconds.")
    return timeout


def _normalize_radar_rule_payload(payload: dict[str, Any]) -> dict[str, Any]:
    pattern = normalize_notification_pattern(payload.get("pattern") or "")
    if not pattern:
        raise ValueError("Pattern is required.")
    distance_m = normalize_notification_distance_m(payload.get("distance_m"))
    return {
        "enabled": 1 if _setting_flag(payload.get("enabled")) else 0,
        "pattern": pattern,
        "distance_m": distance_m,
    }


def _validate_http_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Webhook URL must use http or https.")


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"


def _setting_flag(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _parse_coordinate(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _snapshot_distance_m(snapshot: dict[str, Any], reference_latitude: float | None, reference_longitude: float | None) -> int | None:
    latitude = _parse_coordinate(snapshot.get("latitude"))
    longitude = _parse_coordinate(snapshot.get("longitude"))
    if None in {reference_latitude, reference_longitude, latitude, longitude}:
        return None
    earth_radius_m = 6_371_000.0
    phi_1 = math.radians(float(reference_latitude))
    phi_2 = math.radians(float(latitude))
    delta_phi = math.radians(float(latitude) - float(reference_latitude))
    delta_lambda = math.radians(float(longitude) - float(reference_longitude))
    haversine = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0) ** 2
    )
    arc = 2.0 * math.atan2(math.sqrt(haversine), math.sqrt(1.0 - haversine))
    return int(round(earth_radius_m * arc))


def _reference_station_label(station_settings: dict[str, Any]) -> str:
    callsign = str(station_settings.get("callsign") or "").strip().upper()
    ssid = str(station_settings.get("ssid") or "").strip()
    return f"{callsign}-{ssid}" if callsign and ssid else callsign or "My Station"


def _notification_radar_ignored_station_keys(station_settings: dict[str, Any]) -> set[str]:
    ignored_keys: set[str] = set()
    main_station_key = _reference_station_label(station_settings).strip().casefold()
    if main_station_key and main_station_key != "my station":
        ignored_keys.add(main_station_key)
    wx_station_key = str(get_wx_config().get("full_callsign") or "").strip().upper().casefold()
    if wx_station_key:
        ignored_keys.add(wx_station_key)
    return ignored_keys


def _notification_node_payload() -> dict[str, Any]:
    station_settings = get_station_settings()
    return {
        "callsign": str(station_settings.get("callsign") or "").strip().upper(),
        "ssid": str(station_settings.get("ssid") or "").strip(),
        "full_callsign": _reference_station_label(station_settings),
    }


def _upsert_radar_state(
    connection,
    *,
    rule_id: int,
    station_key: str,
    is_inside: int,
    last_matched_at: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO notification_radar_state(rule_id, station_key, is_inside, last_matched_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(rule_id, station_key) DO UPDATE SET
            is_inside = excluded.is_inside,
            last_matched_at = COALESCE(excluded.last_matched_at, notification_radar_state.last_matched_at),
            updated_at = excluded.updated_at
        """,
        (rule_id, station_key, int(is_inside), last_matched_at, utc_now()),
    )
