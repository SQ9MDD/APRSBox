from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import fetch_all, fetch_one, get_connection, utc_now
from app.services.aprsis_rf import (
    MESSAGE_DELIVERY_STEP_TYPE,
)
from app.services.mqtt_url import TX_CAPABLE_MODEM_TYPES


_AX25_ADDRESS_RE = re.compile(r"^[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?$")
_MESSAGE_PACKET_TYPES = frozenset({"message", "ack", "reject"})
ASSOCIATED_POSITION_WINDOW_MINUTES = 30
IGATE_STATE_RETENTION_MINUTES = 120
LOCAL_HEARD_WINDOW_MINUTES = 60
MAX_LOCAL_CONSUMED_HOPS = 0


def normalize_station_key(value: Any) -> str:
    station_key = str(value or "").strip().upper()
    if station_key.endswith("-0"):
        station_key = station_key[:-2]
    return station_key if _AX25_ADDRESS_RE.fullmatch(station_key) else ""


def record_rf_heard_station(
    parsed: dict[str, Any] | None,
    *,
    interface_id: int | None,
    timestamp: str,
) -> None:
    if not parsed or interface_id is None:
        return
    station_key = normalize_station_key(parsed.get("source"))
    if not station_key:
        return
    path = str(parsed.get("path") or "").strip()
    consumed_hops = _consumed_hop_count(path)
    occurred_at = _normalized_timestamp(timestamp)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO aprsis_igate_rf_heard(
                station_key, interface_id, last_heard_at, last_path, consumed_hops
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(station_key, interface_id) DO UPDATE SET
                last_heard_at = CASE
                    WHEN excluded.last_heard_at >= aprsis_igate_rf_heard.last_heard_at
                    THEN excluded.last_heard_at
                    ELSE aprsis_igate_rf_heard.last_heard_at
                END,
                last_path = CASE
                    WHEN excluded.last_heard_at >= aprsis_igate_rf_heard.last_heard_at
                    THEN excluded.last_path
                    ELSE aprsis_igate_rf_heard.last_path
                END,
                consumed_hops = CASE
                    WHEN excluded.last_heard_at >= aprsis_igate_rf_heard.last_heard_at
                    THEN excluded.consumed_hops
                    ELSE aprsis_igate_rf_heard.consumed_hops
                END
            """,
            (station_key, int(interface_id), occurred_at, path, consumed_hops),
        )

        internet_source = _third_party_internet_source(parsed)
        if internet_source:
            connection.execute(
                """
                INSERT INTO aprsis_igate_station_state(station_key, last_internet_origin_at)
                VALUES (?, ?)
                ON CONFLICT(station_key) DO UPDATE SET
                    last_internet_origin_at = MAX(
                        aprsis_igate_station_state.last_internet_origin_at,
                        excluded.last_internet_origin_at
                    )
                """,
                (internet_source, occurred_at),
            )


def record_aprsis_station_presence(
    parsed: dict[str, Any] | None,
    *,
    timestamp: str,
) -> None:
    if not parsed or not _is_direct_internet_origin(parsed):
        return
    station_key = normalize_station_key(parsed.get("source"))
    if not station_key:
        return
    occurred_at = _normalized_timestamp(timestamp)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO aprsis_igate_station_state(station_key, last_internet_origin_at)
            VALUES (?, ?)
            ON CONFLICT(station_key) DO UPDATE SET
                last_internet_origin_at = MAX(
                    aprsis_igate_station_state.last_internet_origin_at,
                    excluded.last_internet_origin_at
                )
            """,
            (station_key, occurred_at),
        )


def evaluate_message_delivery(
    parsed: dict[str, Any] | None,
    *,
    flow_id: int,
    local_igate: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not parsed:
        return {"route": "drop", "reason": "invalid_aprs"}
    reference = _utc_datetime(now)
    sender = normalize_station_key(parsed.get("source"))
    aprs_data = dict(parsed.get("aprs_data") or {})
    packet_group = str(aprs_data.get("packet_group") or "").strip().lower()
    packet_type = str(aprs_data.get("packet_type_code") or "").strip().lower()

    if (
        sender
        and packet_group == "position"
        and _has_pending_sender_position(flow_id, sender, now=reference)
    ):
        return {
            "route": "associated_position",
            "reason": "associated_sender_position",
            "sender": sender,
            "recipient": "",
        }

    addressee = normalize_station_key(aprs_data.get("addressee"))
    is_directed_query = packet_group == "query" and bool(addressee)
    is_message = packet_group == "message" and packet_type in _MESSAGE_PACKET_TYPES
    if not is_message and not is_directed_query:
        return {
            "route": "not_applicable",
            "reason": "not_message_traffic",
            "sender": sender,
            "recipient": addressee,
        }
    if not sender or not addressee:
        return {
            "route": "drop",
            "reason": "message_invalid_address",
            "sender": sender,
            "recipient": addressee,
        }
    if addressee == normalize_station_key(local_igate):
        return {
            "route": "drop",
            "reason": "message_recipient_is_igate",
            "sender": sender,
            "recipient": addressee,
        }

    interface_ids = _active_tx_enabled_rf_interface_ids()
    cutoff = reference - timedelta(minutes=LOCAL_HEARD_WINDOW_MINUTES)
    recipient_heard = _recent_rf_heard(
        addressee,
        interface_ids=interface_ids,
        cutoff=cutoff,
    )
    if recipient_heard is None:
        return {
            "route": "drop",
            "reason": "message_recipient_not_heard_rf",
            "sender": sender,
            "recipient": addressee,
        }
    if _recent_internet_origin(addressee, cutoff=cutoff):
        return {
            "route": "drop",
            "reason": "message_recipient_seen_internet",
            "sender": sender,
            "recipient": addressee,
        }
    if _recent_rf_heard(
        sender,
        interface_ids=interface_ids,
        cutoff=cutoff,
    ) is not None:
        return {
            "route": "drop",
            "reason": "message_sender_heard_local_rf",
            "sender": sender,
            "recipient": addressee,
        }

    heard_at = str(recipient_heard["last_heard_at"] or "")
    heard_age_seconds = max(
        0,
        int((reference - _parse_timestamp(heard_at, fallback=reference)).total_seconds()),
    )
    return {
        "route": "message",
        "reason": "local_message_recipient",
        "sender": sender,
        "recipient": addressee,
        "heard_interface_id": int(recipient_heard["interface_id"]),
        "heard_interface": str(recipient_heard["interface_name"] or ""),
        "heard_age_seconds": heard_age_seconds,
        "consumed_hops": int(recipient_heard["consumed_hops"] or 0),
    }


def mark_pending_sender_position(
    *,
    flow_id: int,
    sender_key: str,
    now: datetime | None = None,
) -> None:
    sender = normalize_station_key(sender_key)
    if not sender:
        return
    reference = _utc_datetime(now)
    expires_at = reference + timedelta(minutes=ASSOCIATED_POSITION_WINDOW_MINUTES)
    with get_connection() as connection:
        _prune_pending_positions(connection, now=reference)
        connection.execute(
            """
            INSERT INTO aprsis_igate_pending_position(flow_id, sender_key, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(flow_id, sender_key) DO UPDATE SET
                expires_at = excluded.expires_at,
                created_at = excluded.created_at
            """,
            (int(flow_id), sender, expires_at.isoformat(), reference.isoformat()),
        )


def clear_pending_sender_position(*, flow_id: int, sender_key: str) -> None:
    sender = normalize_station_key(sender_key)
    if not sender:
        return
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM aprsis_igate_pending_position WHERE flow_id = ? AND sender_key = ?",
            (int(flow_id), sender),
        )


def message_return_capable_for_rf_source(
    rf_source_ref: str,
    *,
    consumed_hops: int = 0,
) -> tuple[bool, str]:
    source_ref = str(rf_source_ref or "").strip()
    if not source_ref:
        return False, "missing_rf_source"
    source_row = fetch_one(
        f"""
        SELECT 1
        FROM modems
        WHERE name = ?
          AND enabled = 1
          AND tx_blocked = 0
          AND UPPER(modem_type) IN ({", ".join("?" for _ in TX_CAPABLE_MODEM_TYPES)})
        LIMIT 1
        """,
        (source_ref, *TX_CAPABLE_MODEM_TYPES),
    )
    if source_row is None:
        return False, "rf_source_not_tx_enabled"
    if int(consumed_hops) > MAX_LOCAL_CONSUMED_HOPS:
        return False, "rf_source_not_direct"
    rows = fetch_all(
        f"""
        SELECT f.id AS flow_id,
               source_modem.enabled AS source_enabled,
               m.enabled AS target_enabled, m.tx_blocked AS target_tx_blocked
        FROM digi_flows AS f
        JOIN digi_flow_steps AS s
          ON s.flow_id = f.id
         AND s.step_type = ?
         AND s.enabled = 1
        LEFT JOIN modems AS source_modem ON source_modem.name = f.source_ref
        LEFT JOIN modems AS m ON m.name = f.target_ref
        WHERE f.enabled = 1
          AND f.source_kind = 'receiver_aprsis'
          AND f.target_kind = 'tx_rf'
          AND UPPER(m.modem_type) IN ({", ".join("?" for _ in TX_CAPABLE_MODEM_TYPES)})
        ORDER BY f.id ASC
        """,
        (MESSAGE_DELIVERY_STEP_TYPE, *TX_CAPABLE_MODEM_TYPES),
    )
    for row in rows:
        if int(row["source_enabled"] or 0) != 1:
            continue
        if int(row["target_enabled"] or 0) != 1 or int(row["target_tx_blocked"] or 0) == 1:
            continue
        return True, f"message_return_flow:{int(row['flow_id'])}"
    return False, "no_message_return_flow"


def prune_igate_runtime_state(*, now: datetime | None = None) -> dict[str, int]:
    reference = _utc_datetime(now)
    cutoff = reference - timedelta(minutes=IGATE_STATE_RETENTION_MINUTES)
    deleted: dict[str, int] = {}
    with get_connection() as connection:
        for table_name, column_name, threshold in (
            ("aprsis_igate_rf_heard", "last_heard_at", cutoff.isoformat()),
            (
                "aprsis_igate_station_state",
                "last_internet_origin_at",
                cutoff.isoformat(),
            ),
            ("aprsis_igate_pending_position", "expires_at", reference.isoformat()),
        ):
            cursor = connection.execute(
                f'DELETE FROM "{table_name}" WHERE "{column_name}" IS NULL OR "{column_name}" < ?',
                (threshold,),
            )
            deleted[table_name] = max(0, int(cursor.rowcount or 0))
    return deleted


def _has_pending_sender_position(flow_id: int, sender_key: str, *, now: datetime) -> bool:
    with get_connection() as connection:
        _prune_pending_positions(connection, now=now)
        row = connection.execute(
            """
            SELECT 1
            FROM aprsis_igate_pending_position
            WHERE flow_id = ? AND sender_key = ? AND expires_at >= ?
            LIMIT 1
            """,
            (int(flow_id), sender_key, now.isoformat()),
        ).fetchone()
    return row is not None


def _active_tx_enabled_rf_interface_ids() -> list[int]:
    placeholders = ", ".join("?" for _ in TX_CAPABLE_MODEM_TYPES)
    rows = fetch_all(
        f"""
        SELECT id
        FROM modems
        WHERE enabled = 1
          AND tx_blocked = 0
          AND UPPER(modem_type) IN ({placeholders})
        """,
        TX_CAPABLE_MODEM_TYPES,
    )
    return [int(row["id"]) for row in rows]


def _recent_rf_heard(
    station_key: str,
    *,
    interface_ids: list[int],
    cutoff: datetime,
) -> Any | None:
    if not station_key or not interface_ids:
        return None
    placeholders = ", ".join("?" for _ in interface_ids)
    return fetch_one(
        f"""
        SELECT h.interface_id, h.last_heard_at, h.last_path, h.consumed_hops,
               m.name AS interface_name
        FROM aprsis_igate_rf_heard AS h
        JOIN modems AS m ON m.id = h.interface_id
        WHERE h.station_key = ?
          AND h.interface_id IN ({placeholders})
          AND h.last_heard_at >= ?
          AND h.consumed_hops = ?
        ORDER BY h.last_heard_at DESC
        LIMIT 1
        """,
        (
            station_key,
            *interface_ids,
            cutoff.isoformat(),
            MAX_LOCAL_CONSUMED_HOPS,
        ),
    )


def _recent_internet_origin(station_key: str, *, cutoff: datetime) -> bool:
    row = fetch_one(
        """
        SELECT 1
        FROM aprsis_igate_station_state
        WHERE station_key = ?
          AND last_internet_origin_at >= ?
        LIMIT 1
        """,
        (station_key, cutoff.isoformat()),
    )
    return row is not None


def _consumed_hop_count(path: str) -> int:
    return sum(
        1
        for token in str(path or "").split(",")
        if token.strip().endswith("*") and not token.strip().upper().startswith(("TCPIP", "TCPXX"))
    )


def _is_direct_internet_origin(parsed: dict[str, Any]) -> bool:
    tokens = [token.strip().upper() for token in str(parsed.get("path") or "").split(",") if token.strip()]
    if any(token in {"TCPIP*", "TCPXX*"} for token in tokens):
        return True
    return "QAC" in tokens


def _third_party_internet_source(parsed: dict[str, Any]) -> str:
    if not bool(parsed.get("is_third_party")):
        return ""
    aprs_data = dict(parsed.get("aprs_data") or {})
    inner_tokens = [
        token.strip().upper()
        for token in str(aprs_data.get("inner_path") or "").split(",")
        if token.strip()
    ]
    if not any(token.rstrip("*") in {"TCPIP", "TCPXX"} for token in inner_tokens):
        return ""
    return normalize_station_key(aprs_data.get("inner_source_key"))


def _prune_pending_positions(connection: Any, *, now: datetime) -> None:
    connection.execute(
        "DELETE FROM aprsis_igate_pending_position WHERE expires_at < ?",
        (now.isoformat(),),
    )


def _normalized_timestamp(value: str) -> str:
    return _parse_timestamp(value, fallback=datetime.now(timezone.utc)).isoformat()


def _parse_timestamp(value: str, *, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return _parse_timestamp(utc_now(), fallback=datetime.now(timezone.utc))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
