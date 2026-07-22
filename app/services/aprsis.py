from __future__ import annotations

import asyncio
import contextlib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app import get_version
from app.db import fetch_one, get_app_setting, get_connection, log_event, set_app_setting, utc_now
from app.services.traffic_source import DEFAULT_APRSIS_FILTER, normalize_aprsis_filter

DEFAULT_APRSIS_SERVER = "rotate.aprs2.net"
DEFAULT_APRSIS_PORT = 14580
APRSIS_STATUS_INACTIVE = "inactive"
APRSIS_STATUS_CONNECTING = "connecting"
APRSIS_STATUS_CONNECTED = "connected"
APRSIS_STATUS_ERROR = "error"
_APRSIS_ALLOWED_STATUSES = {
    APRSIS_STATUS_INACTIVE,
    APRSIS_STATUS_CONNECTING,
    APRSIS_STATUS_CONNECTED,
    APRSIS_STATUS_ERROR,
}
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,9}(?:-(?:[0-9]|1[0-5]))?$")
_PASSCODE_RE = re.compile(r"^-?[0-9]{1,5}$")
APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX = "blocked_tcpip_tcpxx"
APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY = "blocked_nogate_rfonly"
APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY = "malformed_third_party"
APRSIS_STRICT_REASON_OTHER = "other"
_APRSIS_STRICT_REASON_KEYS = {
    APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX,
    APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY,
    APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY,
    APRSIS_STRICT_REASON_OTHER,
}
_APRSIS_MINUTE_STATS_RETENTION_HOURS = 24 * 365
APRSIS_TX_DRAIN_TIMEOUT_SECONDS = 0.25


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _monotonic_delta_ms(start: Any, *, end: float | None = None) -> float | None:
    if not isinstance(start, (int, float)):
        return None
    reference = end if end is not None else time.monotonic()
    delta_ms = (reference - float(start)) * 1000.0
    if delta_ms < 0:
        return 0.0
    return delta_ms


def _normalize_callsign(value: Any) -> str:
    return _normalize_text(value).upper()


def _station_callsign_and_ssid() -> tuple[str, str]:
    row = fetch_one("SELECT callsign, ssid FROM station_settings WHERE id = 1")
    if row is None:
        return "", ""
    callsign = _normalize_callsign(row["callsign"])
    ssid = _normalize_text(row["ssid"])
    if ssid == "0":
        ssid = ""
    if ssid and (not ssid.isdigit() or int(ssid) < 0 or int(ssid) > 15):
        ssid = ""
    return callsign, ssid


def station_login_default() -> str:
    callsign, ssid = _station_callsign_and_ssid()
    if not callsign:
        return ""
    return f"{callsign}-{ssid}" if ssid else callsign


def derive_aprsis_passcode(callsign: str) -> str:
    normalized = _normalize_callsign(callsign)
    base, _, _ = normalized.partition("-")
    if not base or not re.fullmatch(r"[A-Z0-9]{1,9}", base):
        return ""
    value = 0x73E2
    for index, char in enumerate(base):
        if index % 2 == 0:
            value ^= ord(char) << 8
        else:
            value ^= ord(char)
    return str(value & 0x7FFF)


def _stored_aprsis_port() -> int:
    raw = _normalize_text(get_app_setting("aprsis_port"))
    if not raw:
        return DEFAULT_APRSIS_PORT
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_APRSIS_PORT
    if parsed < 1 or parsed > 65535:
        return DEFAULT_APRSIS_PORT
    return parsed


def get_aprsis_config() -> dict[str, Any]:
    host = _normalize_text(get_app_setting("aprsis_server")) or DEFAULT_APRSIS_SERVER
    port = _stored_aprsis_port()

    login_override = _normalize_callsign(get_app_setting("aprsis_login"))
    if login_override and not _CALLSIGN_RE.fullmatch(login_override):
        login_override = ""
    login_default = station_login_default()
    login = login_override or login_default

    passcode_override = _normalize_text(get_app_setting("aprsis_passcode"))
    if passcode_override and not _PASSCODE_RE.fullmatch(passcode_override):
        passcode_override = ""
    passcode_default = derive_aprsis_passcode(login or login_default)
    passcode = passcode_override or passcode_default

    return {
        "server": host,
        "port": port,
        "login": login,
        "passcode": passcode,
        "station_login_default": login_default,
        "passcode_default": passcode_default,
        "login_is_default": not bool(login_override),
        "passcode_is_default": not bool(passcode_override),
    }


def _normalize_aprsis_server(value: Any) -> str:
    host = _normalize_text(value)
    if not host:
        raise ValueError("APRS-IS server is required.")
    if any(char.isspace() for char in host):
        raise ValueError("APRS-IS server cannot contain spaces.")
    return host


def _normalize_aprsis_port(value: Any) -> int:
    text = _normalize_text(value)
    if not text:
        return DEFAULT_APRSIS_PORT
    try:
        port = int(text)
    except ValueError as exc:
        raise ValueError("APRS-IS port must be a whole number between 1 and 65535.") from exc
    if port < 1 or port > 65535:
        raise ValueError("APRS-IS port must be a whole number between 1 and 65535.")
    return port


def _normalize_aprsis_login_override(value: Any) -> str:
    login = _normalize_callsign(value)
    if not login:
        return ""
    if not _CALLSIGN_RE.fullmatch(login):
        raise ValueError("APRS-IS login must be a callsign or callsign-SSID.")
    return login


def _normalize_aprsis_passcode_override(value: Any) -> str:
    passcode = _normalize_text(value)
    if not passcode:
        return ""
    if not _PASSCODE_RE.fullmatch(passcode):
        raise ValueError("APRS-IS passcode must be numeric.")
    return passcode


def save_aprsis_config(payload: dict[str, Any]) -> dict[str, Any]:
    server = _normalize_aprsis_server(payload.get("server"))
    port = _normalize_aprsis_port(payload.get("port"))
    login_override = _normalize_aprsis_login_override(payload.get("login"))
    passcode_override = _normalize_aprsis_passcode_override(payload.get("passcode"))

    set_app_setting("aprsis_server", server)
    set_app_setting("aprsis_port", str(port))
    set_app_setting("aprsis_login", login_override)
    set_app_setting("aprsis_passcode", passcode_override)
    log_event("INFO", "config", "Updated APRS-IS Packet Routing settings")
    return get_aprsis_config()


def safe_save_aprsis_config(payload: dict[str, Any]) -> tuple[bool, str | None]:
    try:
        save_aprsis_config(payload)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def has_enabled_aprsis_target_flow() -> bool:
    row = fetch_one(
        """
        SELECT 1
        FROM digi_flows
        WHERE enabled = 1
          AND target_kind = 'tx_aprsis'
        LIMIT 1
        """
    )
    return row is not None


def get_enabled_aprsis_interface() -> dict[str, Any] | None:
    row = fetch_one(
        """
        SELECT id, name, device_path, enabled, updated_at
        FROM modems
        WHERE enabled = 1
          AND UPPER(modem_type) = 'APRSIS'
        ORDER BY id ASC
        LIMIT 1
        """
    )
    if row is None:
        return None
    result = dict(row)
    try:
        result["filter"] = normalize_aprsis_filter(result.get("device_path"))
    except ValueError as exc:
        result["filter"] = DEFAULT_APRSIS_FILTER
        log_event("WARNING", "aprsis", f"Invalid stored APRS-IS filter; using {DEFAULT_APRSIS_FILTER}: {exc}")
    return result


def aprsis_connection_required() -> bool:
    return get_enabled_aprsis_interface() is not None or has_enabled_aprsis_target_flow()


def build_aprsis_login_line(*, login: str, passcode: str, server_filter: str = "") -> str:
    line = f"user {login} pass {passcode or '-1'} vers APRSBox {get_version()}"
    normalized_filter = (
        normalize_aprsis_filter(server_filter)
        if str(server_filter or "").strip()
        else ""
    )
    if normalized_filter:
        line += f" filter {normalized_filter}"
    return line


def persist_aprsis_runtime_status(
    *,
    status: str,
    status_detail: str,
    server: str | None = None,
    port: int | None = None,
    login: str | None = None,
    connected_at: str | None = None,
    last_error: str | None = None,
) -> None:
    normalized_status = _normalize_text(status).lower() or APRSIS_STATUS_INACTIVE
    if normalized_status not in _APRSIS_ALLOWED_STATUSES:
        normalized_status = APRSIS_STATUS_ERROR
    timestamp = utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO aprsis_runtime_state (
                id, status, status_detail, server, port, login,
                connected_at, last_error, updated_at
            )
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                status_detail = excluded.status_detail,
                server = excluded.server,
                port = excluded.port,
                login = excluded.login,
                connected_at = excluded.connected_at,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (
                normalized_status,
                str(status_detail or ""),
                server,
                int(port) if port is not None else None,
                login,
                connected_at,
                last_error,
                timestamp,
            ),
        )


def get_aprsis_runtime_status() -> dict[str, Any]:
    row = fetch_one("SELECT * FROM aprsis_runtime_state WHERE id = 1")
    if row is None:
        return {
            "status": APRSIS_STATUS_INACTIVE,
            "status_detail": "APRS-IS uplink is inactive.",
            "server": None,
            "port": None,
            "login": None,
            "connected_at": None,
            "last_error": None,
            "updated_at": None,
        }
    return {
        "status": str(row["status"] or APRSIS_STATUS_INACTIVE),
        "status_detail": str(row["status_detail"] or ""),
        "server": str(row["server"] or "") or None,
        "port": int(row["port"]) if row["port"] is not None else None,
        "login": str(row["login"] or "") or None,
        "connected_at": str(row["connected_at"] or "") or None,
        "last_error": str(row["last_error"] or "") or None,
        "updated_at": str(row["updated_at"] or "") or None,
    }


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _format_uptime_label(connected_at: str | None) -> str:
    connected_ts = _parse_iso_timestamp(connected_at)
    if connected_ts is None:
        return "-"
    delta = datetime.now(timezone.utc) - connected_ts
    total_seconds = max(0, int(delta.total_seconds()))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _normalize_optional_line(value: Any) -> str | None:
    line = str(value or "").rstrip("\r\n")
    return line if line else None


def _extract_line_suffix(message: Any) -> str | None:
    text = str(message or "")
    marker = "| line="
    marker_index = text.find(marker)
    if marker_index < 0:
        return None
    line = text[marker_index + len(marker) :].rstrip("\r\n")
    return line or None


def _minute_bucket_start(value: str | None = None) -> str:
    timestamp = _parse_iso_timestamp(value)
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return timestamp.replace(second=0, microsecond=0).isoformat()


def _max_timestamp(values: list[str | None]) -> str | None:
    latest: datetime | None = None
    latest_value: str | None = None
    for value in values:
        parsed = _parse_iso_timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            latest_value = value
    return latest_value


def _upsert_aprsis_minute_bucket(
    connection: Any,
    *,
    bucket_minute_utc: str,
    tx_count: int = 0,
    drop_count: int = 0,
    strict_count: int = 0,
    strict_blocked_tcpip_tcpxx_count: int = 0,
    strict_blocked_nogate_rfonly_count: int = 0,
    strict_malformed_third_party_count: int = 0,
    strict_other_count: int = 0,
) -> None:
    updated_at = utc_now()
    connection.execute(
        """
        INSERT INTO aprsis_uplink_minute_stats (
            bucket_minute_utc,
            tx_count,
            drop_count,
            strict_count,
            strict_blocked_tcpip_tcpxx_count,
            strict_blocked_nogate_rfonly_count,
            strict_malformed_third_party_count,
            strict_other_count,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(bucket_minute_utc) DO UPDATE SET
            tx_count = tx_count + excluded.tx_count,
            drop_count = drop_count + excluded.drop_count,
            strict_count = strict_count + excluded.strict_count,
            strict_blocked_tcpip_tcpxx_count = strict_blocked_tcpip_tcpxx_count + excluded.strict_blocked_tcpip_tcpxx_count,
            strict_blocked_nogate_rfonly_count = strict_blocked_nogate_rfonly_count + excluded.strict_blocked_nogate_rfonly_count,
            strict_malformed_third_party_count = strict_malformed_third_party_count + excluded.strict_malformed_third_party_count,
            strict_other_count = strict_other_count + excluded.strict_other_count,
            updated_at = excluded.updated_at
        """,
        (
            bucket_minute_utc,
            int(tx_count),
            int(drop_count),
            int(strict_count),
            int(strict_blocked_tcpip_tcpxx_count),
            int(strict_blocked_nogate_rfonly_count),
            int(strict_malformed_third_party_count),
            int(strict_other_count),
            updated_at,
        ),
    )


def _prune_aprsis_minute_stats(connection: Any) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_APRSIS_MINUTE_STATS_RETENTION_HOURS)).replace(second=0, microsecond=0).isoformat()
    connection.execute(
        """
        DELETE FROM aprsis_uplink_minute_stats
        WHERE bucket_minute_utc < ?
        """,
        (cutoff,),
    )


def _ensure_aprsis_uplink_stats_row(connection: Any) -> None:
    connection.execute(
        """
        INSERT INTO aprsis_uplink_stats (
            id, tx_total, drop_total, strict_total,
            strict_blocked_tcpip_tcpxx_total, strict_blocked_nogate_rfonly_total,
            strict_malformed_third_party_total, strict_other_total,
            last_sent_at, last_sent_line, last_drop_at, last_drop_line,
            last_strict_reject_at, last_strict_reject_line, last_strict_reject_reason, updated_at
        )
        VALUES (1, 0, 0, 0, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (utc_now(),),
    )


def _legacy_event_log_metrics(connection: Any, *, start_1h: str, start_24h: str) -> dict[str, Any]:
    tx_stats_row = connection.execute(
        """
        SELECT
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'tx' THEN 1 ELSE 0 END) AS tx_total,
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'tx' AND l.created_at >= ? THEN 1 ELSE 0 END) AS tx_1h,
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'tx' AND l.created_at >= ? THEN 1 ELSE 0 END) AS tx_24h,
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'drop' THEN 1 ELSE 0 END) AS drop_total,
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'drop' AND l.created_at >= ? THEN 1 ELSE 0 END) AS drop_1h,
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'drop' AND l.created_at >= ? THEN 1 ELSE 0 END) AS drop_24h,
            SUM(CASE WHEN l.event_type = 'strict_filter' AND l.decision = 'rejected' THEN 1 ELSE 0 END) AS strict_total,
            SUM(CASE WHEN l.event_type = 'strict_filter' AND l.decision = 'rejected' AND l.created_at >= ? THEN 1 ELSE 0 END) AS strict_1h,
            SUM(CASE WHEN l.event_type = 'strict_filter' AND l.decision = 'rejected' AND l.created_at >= ? THEN 1 ELSE 0 END) AS strict_24h
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        WHERE f.target_kind = 'tx_aprsis'
        """,
        (start_1h, start_24h, start_1h, start_24h, start_1h, start_24h),
    ).fetchone()
    strict_reasons_row = connection.execute(
        """
        SELECT
            SUM(
                CASE
                    WHEN l.created_at >= ?
                     AND l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND (UPPER(l.message) LIKE '%TCPIP%' OR UPPER(l.message) LIKE '%TCPXX%')
                    THEN 1
                    ELSE 0
                END
            ) AS blocked_tcp,
            SUM(
                CASE
                    WHEN l.created_at >= ?
                     AND l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND (UPPER(l.message) LIKE '%NOGATE%' OR UPPER(l.message) LIKE '%RFONLY%')
                    THEN 1
                    ELSE 0
                END
            ) AS blocked_rfonly,
            SUM(
                CASE
                    WHEN l.created_at >= ?
                     AND l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND UPPER(l.message) LIKE '%MALFORMED OR INVALID%'
                    THEN 1
                    ELSE 0
                END
            ) AS malformed_third_party
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        WHERE f.target_kind = 'tx_aprsis'
        """,
        (start_24h, start_24h, start_24h),
    ).fetchone()
    strict_reasons_total_row = connection.execute(
        """
        SELECT
            SUM(
                CASE
                    WHEN l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND (UPPER(l.message) LIKE '%TCPIP%' OR UPPER(l.message) LIKE '%TCPXX%')
                    THEN 1
                    ELSE 0
                END
            ) AS blocked_tcp_total,
            SUM(
                CASE
                    WHEN l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND (UPPER(l.message) LIKE '%NOGATE%' OR UPPER(l.message) LIKE '%RFONLY%')
                    THEN 1
                    ELSE 0
                END
            ) AS blocked_rfonly_total,
            SUM(
                CASE
                    WHEN l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND UPPER(l.message) LIKE '%MALFORMED OR INVALID%'
                    THEN 1
                    ELSE 0
                END
            ) AS malformed_third_party_total
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        WHERE f.target_kind = 'tx_aprsis'
        """
    ).fetchone()
    last_tx_row = connection.execute(
        """
        SELECT l.created_at, l.message
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        WHERE f.target_kind = 'tx_aprsis'
          AND l.event_type = 'output_action'
          AND l.decision = 'tx'
        ORDER BY l.id DESC
        LIMIT 1
        """
    ).fetchone()
    last_drop_row = connection.execute(
        """
        SELECT l.created_at, l.message
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        WHERE f.target_kind = 'tx_aprsis'
          AND l.event_type = 'output_action'
          AND l.decision = 'drop'
        ORDER BY l.id DESC
        LIMIT 1
        """
    ).fetchone()
    last_strict_row = connection.execute(
        """
        SELECT l.frame_uid, l.created_at, l.message
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        WHERE f.target_kind = 'tx_aprsis'
          AND l.event_type = 'strict_filter'
          AND l.decision = 'rejected'
        ORDER BY l.id DESC
        LIMIT 1
        """
    ).fetchone()

    strict_line = None
    strict_frame_uid = str(_row_value(last_strict_row, "frame_uid", "") or "").strip()
    if strict_frame_uid:
        strict_line_row = connection.execute(
            """
            SELECT l.message
            FROM digi_flow_event_log l
            JOIN digi_flows f ON f.id = l.flow_id
            WHERE f.target_kind = 'tx_aprsis'
              AND l.frame_uid = ?
              AND l.message LIKE '%| line=%'
            ORDER BY l.id DESC
            LIMIT 1
            """,
            (strict_frame_uid,),
        ).fetchone()
        strict_line = _extract_line_suffix(_row_value(strict_line_row, "message", ""))

    strict_24h_total = int(_row_value(tx_stats_row, "strict_24h", 0) or 0)
    strict_total = int(_row_value(tx_stats_row, "strict_total", 0) or 0)
    strict_tcp = int(_row_value(strict_reasons_row, "blocked_tcp", 0) or 0)
    strict_rfonly = int(_row_value(strict_reasons_row, "blocked_rfonly", 0) or 0)
    strict_malformed = int(_row_value(strict_reasons_row, "malformed_third_party", 0) or 0)
    strict_other = max(0, strict_24h_total - strict_tcp - strict_rfonly - strict_malformed)
    strict_tcp_total = int(_row_value(strict_reasons_total_row, "blocked_tcp_total", 0) or 0)
    strict_rfonly_total = int(_row_value(strict_reasons_total_row, "blocked_rfonly_total", 0) or 0)
    strict_malformed_total = int(_row_value(strict_reasons_total_row, "malformed_third_party_total", 0) or 0)
    strict_other_total = max(0, strict_total - strict_tcp_total - strict_rfonly_total - strict_malformed_total)

    return {
        "tx_total": int(_row_value(tx_stats_row, "tx_total", 0) or 0),
        "tx_1h": int(_row_value(tx_stats_row, "tx_1h", 0) or 0),
        "tx_24h": int(_row_value(tx_stats_row, "tx_24h", 0) or 0),
        "drop_total": int(_row_value(tx_stats_row, "drop_total", 0) or 0),
        "drop_1h": int(_row_value(tx_stats_row, "drop_1h", 0) or 0),
        "drop_24h": int(_row_value(tx_stats_row, "drop_24h", 0) or 0),
        "strict_total": strict_total,
        "strict_1h": int(_row_value(tx_stats_row, "strict_1h", 0) or 0),
        "strict_24h": strict_24h_total,
        "strict_tcp_24h": strict_tcp,
        "strict_rfonly_24h": strict_rfonly,
        "strict_malformed_24h": strict_malformed,
        "strict_other_24h": strict_other,
        "strict_tcp_total": strict_tcp_total,
        "strict_rfonly_total": strict_rfonly_total,
        "strict_malformed_total": strict_malformed_total,
        "strict_other_total": strict_other_total,
        "last_sent_at": str(_row_value(last_tx_row, "created_at", "") or "") or None,
        "last_sent_line": _extract_line_suffix(_row_value(last_tx_row, "message", "")),
        "last_drop_at": str(_row_value(last_drop_row, "created_at", "") or "") or None,
        "last_drop_line": _extract_line_suffix(_row_value(last_drop_row, "message", "")),
        "last_strict_reject_at": str(_row_value(last_strict_row, "created_at", "") or "") or None,
        "last_strict_reject_line": strict_line,
        "last_strict_reject_reason": str(_row_value(last_strict_row, "message", "") or "") or None,
    }


def _backfill_aprsis_minute_stats_from_event_log(connection: Any, *, start_at: str) -> None:
    connection.execute(
        """
        INSERT INTO aprsis_uplink_minute_stats (
            bucket_minute_utc,
            tx_count,
            drop_count,
            strict_count,
            strict_blocked_tcpip_tcpxx_count,
            strict_blocked_nogate_rfonly_count,
            strict_malformed_third_party_count,
            strict_other_count,
            updated_at
        )
        SELECT
            strftime('%Y-%m-%dT%H:%M:00+00:00', l.created_at) AS bucket_minute_utc,
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'tx' THEN 1 ELSE 0 END) AS tx_count,
            SUM(CASE WHEN l.event_type = 'output_action' AND l.decision = 'drop' THEN 1 ELSE 0 END) AS drop_count,
            SUM(CASE WHEN l.event_type = 'strict_filter' AND l.decision = 'rejected' THEN 1 ELSE 0 END) AS strict_count,
            SUM(
                CASE
                    WHEN l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND (UPPER(l.message) LIKE '%TCPIP%' OR UPPER(l.message) LIKE '%TCPXX%')
                    THEN 1
                    ELSE 0
                END
            ) AS strict_blocked_tcpip_tcpxx_count,
            SUM(
                CASE
                    WHEN l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND (UPPER(l.message) LIKE '%NOGATE%' OR UPPER(l.message) LIKE '%RFONLY%')
                    THEN 1
                    ELSE 0
                END
            ) AS strict_blocked_nogate_rfonly_count,
            SUM(
                CASE
                    WHEN l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND UPPER(l.message) LIKE '%MALFORMED OR INVALID%'
                    THEN 1
                    ELSE 0
                END
            ) AS strict_malformed_third_party_count,
            SUM(
                CASE
                    WHEN l.event_type = 'strict_filter'
                     AND l.decision = 'rejected'
                     AND UPPER(l.message) NOT LIKE '%TCPIP%'
                     AND UPPER(l.message) NOT LIKE '%TCPXX%'
                     AND UPPER(l.message) NOT LIKE '%NOGATE%'
                     AND UPPER(l.message) NOT LIKE '%RFONLY%'
                     AND UPPER(l.message) NOT LIKE '%MALFORMED OR INVALID%'
                    THEN 1
                    ELSE 0
                END
            ) AS strict_other_count,
            ?
        FROM digi_flow_event_log l
        JOIN digi_flows f ON f.id = l.flow_id
        WHERE f.target_kind = 'tx_aprsis'
          AND l.created_at >= ?
        GROUP BY bucket_minute_utc
        ON CONFLICT(bucket_minute_utc) DO UPDATE SET
            tx_count = excluded.tx_count,
            drop_count = excluded.drop_count,
            strict_count = excluded.strict_count,
            strict_blocked_tcpip_tcpxx_count = excluded.strict_blocked_tcpip_tcpxx_count,
            strict_blocked_nogate_rfonly_count = excluded.strict_blocked_nogate_rfonly_count,
            strict_malformed_third_party_count = excluded.strict_malformed_third_party_count,
            strict_other_count = excluded.strict_other_count,
            updated_at = excluded.updated_at
        """,
        (utc_now(), start_at),
    )


def record_aprsis_tx_result(
    *,
    sent: bool,
    frame_line: str | None,
    occurred_at: str | None = None,
) -> None:
    timestamp = str(occurred_at or utc_now())
    normalized_line = _normalize_optional_line(frame_line)
    bucket_minute = _minute_bucket_start(timestamp)
    with get_connection() as connection:
        _ensure_aprsis_uplink_stats_row(connection)
        if sent:
            connection.execute(
                """
                UPDATE aprsis_uplink_stats
                SET tx_total = tx_total + 1,
                    last_sent_at = ?,
                    last_sent_line = COALESCE(?, last_sent_line),
                    updated_at = ?
                WHERE id = 1
                """,
                (timestamp, normalized_line, utc_now()),
            )
            _upsert_aprsis_minute_bucket(connection, bucket_minute_utc=bucket_minute, tx_count=1)
        else:
            connection.execute(
                """
                UPDATE aprsis_uplink_stats
                SET drop_total = drop_total + 1,
                    last_drop_at = ?,
                    last_drop_line = COALESCE(?, last_drop_line),
                    updated_at = ?
                WHERE id = 1
                """,
                (timestamp, normalized_line, utc_now()),
            )
            _upsert_aprsis_minute_bucket(connection, bucket_minute_utc=bucket_minute, drop_count=1)
        _prune_aprsis_minute_stats(connection)


def record_aprsis_strict_reject(
    *,
    reason_key: str,
    frame_line: str | None,
    reason_message: str | None,
    occurred_at: str | None = None,
) -> None:
    normalized_reason = str(reason_key or "").strip().lower()
    if normalized_reason not in _APRSIS_STRICT_REASON_KEYS:
        normalized_reason = APRSIS_STRICT_REASON_OTHER
    timestamp = str(occurred_at or utc_now())
    normalized_line = _normalize_optional_line(frame_line)
    normalized_message = str(reason_message or "").strip() or None
    bucket_minute = _minute_bucket_start(timestamp)

    reason_total_column = {
        APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX: "strict_blocked_tcpip_tcpxx_total",
        APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY: "strict_blocked_nogate_rfonly_total",
        APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY: "strict_malformed_third_party_total",
        APRSIS_STRICT_REASON_OTHER: "strict_other_total",
    }[normalized_reason]
    connection_updates = (
        f"strict_total = strict_total + 1, "
        f"{reason_total_column} = {reason_total_column} + 1, "
        "last_strict_reject_at = ?, "
        "last_strict_reject_line = COALESCE(?, last_strict_reject_line), "
        "last_strict_reject_reason = COALESCE(?, last_strict_reject_reason), "
        "updated_at = ?"
    )

    minute_reason_kwargs = {
        "strict_blocked_tcpip_tcpxx_count": 1 if normalized_reason == APRSIS_STRICT_REASON_BLOCKED_TCPIP_TCPXX else 0,
        "strict_blocked_nogate_rfonly_count": 1 if normalized_reason == APRSIS_STRICT_REASON_BLOCKED_NOGATE_RFONLY else 0,
        "strict_malformed_third_party_count": 1 if normalized_reason == APRSIS_STRICT_REASON_MALFORMED_THIRD_PARTY else 0,
        "strict_other_count": 1 if normalized_reason == APRSIS_STRICT_REASON_OTHER else 0,
    }

    with get_connection() as connection:
        _ensure_aprsis_uplink_stats_row(connection)
        connection.execute(
            f"""
            UPDATE aprsis_uplink_stats
            SET {connection_updates}
            WHERE id = 1
            """,
            (timestamp, normalized_line, normalized_message, utc_now()),
        )
        _upsert_aprsis_minute_bucket(
            connection,
            bucket_minute_utc=bucket_minute,
            strict_count=1,
            **minute_reason_kwargs,
        )
        _prune_aprsis_minute_stats(connection)


def get_aprsis_diagnostics() -> dict[str, Any]:
    now_ts = datetime.now(timezone.utc)
    start_1h = (now_ts - timedelta(hours=1)).replace(second=0, microsecond=0).isoformat()
    start_24h = (now_ts - timedelta(hours=24)).replace(second=0, microsecond=0).isoformat()
    start_72h = (now_ts - timedelta(hours=_APRSIS_MINUTE_STATS_RETENTION_HOURS)).replace(second=0, microsecond=0).isoformat()
    runtime = get_aprsis_runtime_status()

    with get_connection() as connection:
        _ensure_aprsis_uplink_stats_row(connection)
        active_flow_row = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM digi_flows
            WHERE enabled = 1
              AND target_kind = 'tx_aprsis'
            """
        ).fetchone()
        active_flows = connection.execute(
            """
            SELECT id, name
            FROM digi_flows
            WHERE enabled = 1
              AND target_kind = 'tx_aprsis'
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        stats_row = connection.execute(
            """
            SELECT *
            FROM aprsis_uplink_stats
            WHERE id = 1
            """
        ).fetchone()

        minute_stats_row = connection.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN tx_count ELSE 0 END), 0) AS tx_1h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN tx_count ELSE 0 END), 0) AS tx_24h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN drop_count ELSE 0 END), 0) AS drop_1h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN drop_count ELSE 0 END), 0) AS drop_24h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_count ELSE 0 END), 0) AS strict_1h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_count ELSE 0 END), 0) AS strict_24h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_blocked_tcpip_tcpxx_count ELSE 0 END), 0) AS strict_tcp_24h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_blocked_nogate_rfonly_count ELSE 0 END), 0) AS strict_rfonly_24h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_malformed_third_party_count ELSE 0 END), 0) AS strict_malformed_24h,
                COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_other_count ELSE 0 END), 0) AS strict_other_24h
            FROM aprsis_uplink_minute_stats
            """
            ,
            (start_1h, start_24h, start_1h, start_24h, start_1h, start_24h, start_24h, start_24h, start_24h, start_24h),
        ).fetchone()

        connect_events_row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN message LIKE 'Connected APRS-IS uplink to %' THEN 1 ELSE 0 END) AS reconnect_total,
                SUM(CASE WHEN message LIKE 'Connected APRS-IS uplink to %' AND created_at >= ? THEN 1 ELSE 0 END) AS reconnect_24h,
                MAX(CASE WHEN message LIKE 'Connected APRS-IS uplink to %' THEN created_at ELSE NULL END) AS last_connect_at
            FROM event_logs
            WHERE category = 'aprsis'
            """,
            (start_24h,),
        ).fetchone()
        warning_events_row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN level = 'WARNING' THEN 1 ELSE 0 END) AS warning_total,
                SUM(CASE WHEN level = 'WARNING' AND created_at >= ? THEN 1 ELSE 0 END) AS warning_24h
            FROM event_logs
            WHERE category = 'aprsis'
            """,
            (start_24h,),
        ).fetchone()
        legacy_metrics: dict[str, Any] | None = None
        minute_window_empty = (
            int(_row_value(minute_stats_row, "tx_1h", 0) or 0) == 0
            and int(_row_value(minute_stats_row, "tx_24h", 0) or 0) == 0
            and int(_row_value(minute_stats_row, "drop_1h", 0) or 0) == 0
            and int(_row_value(minute_stats_row, "drop_24h", 0) or 0) == 0
            and int(_row_value(minute_stats_row, "strict_1h", 0) or 0) == 0
            and int(_row_value(minute_stats_row, "strict_24h", 0) or 0) == 0
        )
        stats_total_empty = (
            int(_row_value(stats_row, "tx_total", 0) or 0) == 0
            and int(_row_value(stats_row, "drop_total", 0) or 0) == 0
            and int(_row_value(stats_row, "strict_total", 0) or 0) == 0
        )
        stats_last_empty = (
            not str(_row_value(stats_row, "last_sent_at", "") or "").strip()
            and not str(_row_value(stats_row, "last_drop_at", "") or "").strip()
            and not str(_row_value(stats_row, "last_strict_reject_at", "") or "").strip()
        )
        if minute_window_empty or (stats_total_empty and stats_last_empty):
            legacy_metrics = _legacy_event_log_metrics(connection, start_1h=start_1h, start_24h=start_24h)

        if legacy_metrics is not None and stats_total_empty and stats_last_empty and (
            int(legacy_metrics.get("tx_total") or 0) > 0
            or int(legacy_metrics.get("drop_total") or 0) > 0
            or int(legacy_metrics.get("strict_total") or 0) > 0
        ):
            connection.execute(
                """
                UPDATE aprsis_uplink_stats
                SET tx_total = ?,
                    drop_total = ?,
                    strict_total = ?,
                    strict_blocked_tcpip_tcpxx_total = ?,
                    strict_blocked_nogate_rfonly_total = ?,
                    strict_malformed_third_party_total = ?,
                    strict_other_total = ?,
                    last_sent_at = ?,
                    last_sent_line = ?,
                    last_drop_at = ?,
                    last_drop_line = ?,
                    last_strict_reject_at = ?,
                    last_strict_reject_line = ?,
                    last_strict_reject_reason = ?,
                    updated_at = ?
                WHERE id = 1
                """,
                (
                    int(legacy_metrics.get("tx_total") or 0),
                    int(legacy_metrics.get("drop_total") or 0),
                    int(legacy_metrics.get("strict_total") or 0),
                    int(legacy_metrics.get("strict_tcp_total") or 0),
                    int(legacy_metrics.get("strict_rfonly_total") or 0),
                    int(legacy_metrics.get("strict_malformed_total") or 0),
                    int(legacy_metrics.get("strict_other_total") or 0),
                    legacy_metrics.get("last_sent_at"),
                    legacy_metrics.get("last_sent_line"),
                    legacy_metrics.get("last_drop_at"),
                    legacy_metrics.get("last_drop_line"),
                    legacy_metrics.get("last_strict_reject_at"),
                    legacy_metrics.get("last_strict_reject_line"),
                    legacy_metrics.get("last_strict_reject_reason"),
                    utc_now(),
                ),
            )
            stats_row = connection.execute(
                """
                SELECT *
                FROM aprsis_uplink_stats
                WHERE id = 1
                """
            ).fetchone()
        if legacy_metrics is not None and minute_window_empty:
            _backfill_aprsis_minute_stats_from_event_log(connection, start_at=start_72h)
            _prune_aprsis_minute_stats(connection)
            minute_stats_row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN tx_count ELSE 0 END), 0) AS tx_1h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN tx_count ELSE 0 END), 0) AS tx_24h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN drop_count ELSE 0 END), 0) AS drop_1h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN drop_count ELSE 0 END), 0) AS drop_24h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_count ELSE 0 END), 0) AS strict_1h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_count ELSE 0 END), 0) AS strict_24h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_blocked_tcpip_tcpxx_count ELSE 0 END), 0) AS strict_tcp_24h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_blocked_nogate_rfonly_count ELSE 0 END), 0) AS strict_rfonly_24h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_malformed_third_party_count ELSE 0 END), 0) AS strict_malformed_24h,
                    COALESCE(SUM(CASE WHEN bucket_minute_utc >= ? THEN strict_other_count ELSE 0 END), 0) AS strict_other_24h
                FROM aprsis_uplink_minute_stats
                """,
                (start_1h, start_24h, start_1h, start_24h, start_1h, start_24h, start_24h, start_24h, start_24h, start_24h),
            ).fetchone()
            minute_window_empty = False

    last_sent_at = str(_row_value(stats_row, "last_sent_at", "") or "") or None
    last_drop_at = str(_row_value(stats_row, "last_drop_at", "") or "") or None
    last_strict_reject_at = str(_row_value(stats_row, "last_strict_reject_at", "") or "") or None
    if legacy_metrics is not None and minute_window_empty:
        tx_1h = int(legacy_metrics.get("tx_1h") or 0)
        tx_24h = int(legacy_metrics.get("tx_24h") or 0)
        drop_1h = int(legacy_metrics.get("drop_1h") or 0)
        drop_24h = int(legacy_metrics.get("drop_24h") or 0)
        strict_1h = int(legacy_metrics.get("strict_1h") or 0)
        strict_24h_total = int(legacy_metrics.get("strict_24h") or 0)
        strict_tcp = int(legacy_metrics.get("strict_tcp_24h") or 0)
        strict_rfonly = int(legacy_metrics.get("strict_rfonly_24h") or 0)
        strict_malformed = int(legacy_metrics.get("strict_malformed_24h") or 0)
        strict_other = int(legacy_metrics.get("strict_other_24h") or 0)
        if not last_sent_at:
            last_sent_at = legacy_metrics.get("last_sent_at")
        if not last_drop_at:
            last_drop_at = legacy_metrics.get("last_drop_at")
        if not last_strict_reject_at:
            last_strict_reject_at = legacy_metrics.get("last_strict_reject_at")
    else:
        tx_1h = int(_row_value(minute_stats_row, "tx_1h", 0) or 0)
        tx_24h = int(_row_value(minute_stats_row, "tx_24h", 0) or 0)
        drop_1h = int(_row_value(minute_stats_row, "drop_1h", 0) or 0)
        drop_24h = int(_row_value(minute_stats_row, "drop_24h", 0) or 0)
        strict_1h = int(_row_value(minute_stats_row, "strict_1h", 0) or 0)
        strict_24h_total = int(_row_value(minute_stats_row, "strict_24h", 0) or 0)
        strict_tcp = int(_row_value(minute_stats_row, "strict_tcp_24h", 0) or 0)
        strict_rfonly = int(_row_value(minute_stats_row, "strict_rfonly_24h", 0) or 0)
        strict_malformed = int(_row_value(minute_stats_row, "strict_malformed_24h", 0) or 0)
        strict_other = int(_row_value(minute_stats_row, "strict_other_24h", 0) or 0)

    return {
        "active_flow_count": int(_row_value(active_flow_row, "total", 0) or 0),
        "active_flow_names": [str(row["name"]) for row in active_flows if row and row["name"]],
        "session_uptime": _format_uptime_label(runtime.get("connected_at")),
        "last_activity_at": _max_timestamp([last_sent_at, last_drop_at, last_strict_reject_at]),
        "tx": {
            "sent_total": int(_row_value(stats_row, "tx_total", 0) or 0),
            "sent_1h": tx_1h,
            "sent_24h": tx_24h,
            "drop_total": int(_row_value(stats_row, "drop_total", 0) or 0),
            "drop_1h": drop_1h,
            "drop_24h": drop_24h,
            "last_sent_at": last_sent_at,
            "last_sent_frame_uid": None,
            "last_sent_frame_line": str(_row_value(stats_row, "last_sent_line", "") or "") or (legacy_metrics or {}).get("last_sent_line"),
            "last_drop_at": last_drop_at,
            "last_drop_frame_uid": None,
            "last_drop_frame_line": str(_row_value(stats_row, "last_drop_line", "") or "") or (legacy_metrics or {}).get("last_drop_line"),
        },
        "strict_rejects": {
            "total": int(_row_value(stats_row, "strict_total", 0) or 0),
            "last_1h": strict_1h,
            "last_24h": strict_24h_total,
            "last_24h_blocked_tcpip_tcpxx": strict_tcp,
            "last_24h_blocked_nogate_rfonly": strict_rfonly,
            "last_24h_malformed_third_party": strict_malformed,
            "last_24h_other": strict_other,
            "last_rejected_at": last_strict_reject_at,
            "last_rejected_frame_uid": None,
            "last_rejected_reason": str(_row_value(stats_row, "last_strict_reject_reason", "") or "") or (legacy_metrics or {}).get("last_strict_reject_reason"),
            "last_rejected_frame_line": str(_row_value(stats_row, "last_strict_reject_line", "") or "") or (legacy_metrics or {}).get("last_strict_reject_line"),
        },
        "reconnects": {
            "total": int(_row_value(connect_events_row, "reconnect_total", 0) or 0),
            "last_24h": int(_row_value(connect_events_row, "reconnect_24h", 0) or 0),
            "last_connected_at": str(_row_value(connect_events_row, "last_connect_at", "") or "") or None,
            "warning_total": int(_row_value(warning_events_row, "warning_total", 0) or 0),
            "warning_24h": int(_row_value(warning_events_row, "warning_24h", 0) or 0),
        },
    }


def aprsis_runtime_badge(status: str) -> str:
    normalized = _normalize_text(status).lower()
    if normalized == APRSIS_STATUS_CONNECTED:
        return "enabled"
    if normalized == APRSIS_STATUS_CONNECTING:
        return "warning"
    if normalized == APRSIS_STATUS_ERROR:
        return "disabled"
    return "disabled"


class AprsisClientService:
    def __init__(
        self,
        *,
        poll_interval: float = 1.0,
        reconnect_delay: float = 5.0,
        rx_processor: Callable[..., bool] | None = None,
    ) -> None:
        self._poll_interval = poll_interval
        self._reconnect_delay = reconnect_delay
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connection_lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected_config: tuple[str, int, str, str] | None = None
        self._connected_rx_signature: tuple[int, str] | None = None
        self._desired_rx_interface: dict[str, Any] | None = None
        self._connected_since: str | None = None
        self._retry_not_before = 0.0
        self._rx_processor = rx_processor

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-aprsis-uplink")

    async def stop(self) -> None:
        self._stop_event.set()
        await self._disconnect(reason="APRS-IS uplink stopped.", status=APRSIS_STATUS_INACTIVE)
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def send_tnc2_line(self, line: str, telemetry: dict[str, Any] | None = None) -> tuple[bool, str]:
        payload_line = str(line or "").rstrip("\r\n")
        if not payload_line:
            return False, "APRS-IS TX skipped: empty packet line."
        wire = payload_line.encode("latin-1", errors="replace") + b"\r\n"
        async with self._connection_lock:
            if self._writer is None:
                return False, "APRS-IS TX skipped: uplink is not connected."
            try:
                self._writer.write(wire)
                await asyncio.wait_for(self._writer.drain(), timeout=APRSIS_TX_DRAIN_TIMEOUT_SECONDS)
            except (OSError, TimeoutError) as exc:
                detail = f"APRS-IS TX failed: {exc}"
                await self._disconnect_locked(reason=detail, status=APRSIS_STATUS_ERROR, error=str(exc))
                self._retry_not_before = time.monotonic() + self._reconnect_delay
                return False, detail
        rx_to_aprsis_write_ms = _monotonic_delta_ms((telemetry or {}).get("rx_received_monotonic"))
        rx_to_igate_enqueue_ms = (telemetry or {}).get("rx_to_igate_enqueue_ms")
        igate_queue_wait_ms = (telemetry or {}).get("igate_queue_wait_ms")
        metrics_parts = [f"line={payload_line[:120]}"]
        frame_uid = str((telemetry or {}).get("frame_uid") or "").strip()
        if frame_uid:
            metrics_parts.append(f"frame_uid={frame_uid}")
        if isinstance(rx_to_igate_enqueue_ms, (int, float)):
            metrics_parts.append(f"rx_to_igate_enqueue_ms={float(rx_to_igate_enqueue_ms):.3f}")
        if isinstance(igate_queue_wait_ms, (int, float)):
            metrics_parts.append(f"igate_queue_wait_ms={float(igate_queue_wait_ms):.3f}")
        if rx_to_aprsis_write_ms is not None:
            metrics_parts.append(f"rx_to_aprsis_write_ms={rx_to_aprsis_write_ms:.3f}")
        log_event("DEBUG", "aprsis_latency", " | ".join(metrics_parts))
        return True, "APRS-IS TX queued."

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            rx_interface = get_enabled_aprsis_interface()
            self._desired_rx_interface = dict(rx_interface) if rx_interface is not None else None
            aprsis_rx_enabled = rx_interface is not None
            aprsis_tx_required = has_enabled_aprsis_target_flow()
            desired_active = aprsis_rx_enabled or aprsis_tx_required
            config = get_aprsis_config()
            config_key = (
                str(config["server"]),
                int(config["port"]),
                str(config["login"]),
                str(config["passcode"]),
            )

            if not desired_active:
                await self._disconnect(
                    reason="APRS-IS inactive because neither RX nor TX requires a connection.",
                    status=APRSIS_STATUS_INACTIVE,
                )
                await self._sleep(self._poll_interval)
                continue

            if not config_key[2]:
                persist_aprsis_runtime_status(
                    status=APRSIS_STATUS_ERROR,
                    status_detail="APRS-IS login is empty. Configure My Station callsign or set APRS-IS login override.",
                    server=config_key[0],
                    port=config_key[1],
                    login=None,
                    connected_at=None,
                    last_error="Missing APRS-IS login.",
                )
                await self._disconnect(reason="APRS-IS login missing.", status=APRSIS_STATUS_ERROR, error="Missing APRS-IS login.")
                await self._sleep(self._poll_interval)
                continue

            should_reconnect = False
            desired_rx_signature = self._rx_signature(rx_interface)
            async with self._connection_lock:
                should_reconnect = self._connection_needs_reconnect(
                    config_key=config_key,
                    desired_rx_signature=desired_rx_signature,
                )
            if should_reconnect:
                await self._disconnect(
                    reason="APRS-IS uplink reconnecting because configuration changed.",
                    status=APRSIS_STATUS_CONNECTING,
                )

            async with self._connection_lock:
                has_connection = self._writer is not None
            if not has_connection:
                now = time.monotonic()
                if now >= self._retry_not_before:
                    await self._connect(config_key, rx_interface=rx_interface)
            await self._sleep(self._poll_interval)

    async def _connect(
        self,
        config_key: tuple[str, int, str, str],
        *,
        rx_interface: dict[str, Any] | None = None,
    ) -> None:
        server, port, login, passcode = config_key
        persist_aprsis_runtime_status(
            status=APRSIS_STATUS_CONNECTING,
            status_detail=f"Connecting to APRS-IS {server}:{port} as {login}.",
            server=server,
            port=port,
            login=login,
            connected_at=None,
            last_error=None,
        )
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(server, port), timeout=8.0)
        except (OSError, TimeoutError) as exc:
            error = str(exc).strip() or exc.__class__.__name__
            persist_aprsis_runtime_status(
                status=APRSIS_STATUS_ERROR,
                status_detail=f"APRS-IS connection failed: {error}",
                server=server,
                port=port,
                login=login,
                connected_at=None,
                last_error=error,
            )
            self._retry_not_before = time.monotonic() + self._reconnect_delay
            log_event("WARNING", "aprsis", f"APRS-IS connect failed for {server}:{port} ({error})")
            return

        server_filter = str((rx_interface or {}).get("filter") or "").strip()
        login_line = build_aprsis_login_line(login=login, passcode=passcode, server_filter=server_filter)
        try:
            writer.write(login_line.encode("ascii", errors="replace") + b"\r\n")
            await writer.drain()
        except OSError as exc:
            error = str(exc).strip() or exc.__class__.__name__
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            persist_aprsis_runtime_status(
                status=APRSIS_STATUS_ERROR,
                status_detail=f"APRS-IS login send failed: {error}",
                server=server,
                port=port,
                login=login,
                connected_at=None,
                last_error=error,
            )
            self._retry_not_before = time.monotonic() + self._reconnect_delay
            log_event("WARNING", "aprsis", f"APRS-IS login line send failed ({error})")
            return

        connected_since = utc_now()
        async with self._connection_lock:
            self._writer = writer
            self._connected_config = config_key
            self._connected_rx_signature = self._rx_signature(rx_interface)
            self._connected_since = connected_since
            self._reader_task = asyncio.create_task(
                self._reader_loop(reader=reader, config_key=config_key),
                name="aprsbox-aprsis-reader",
            )
        persist_aprsis_runtime_status(
            status=APRSIS_STATUS_CONNECTED,
            status_detail=f"Connected to APRS-IS {server}:{port} as {login}.",
            server=server,
            port=port,
            login=login,
            connected_at=connected_since,
            last_error=None,
        )
        self._retry_not_before = 0.0
        log_event("INFO", "aprsis", f"Connected APRS-IS uplink to {server}:{port} as {login}")

    async def _reader_loop(self, *, reader: asyncio.StreamReader, config_key: tuple[str, int, str, str]) -> None:
        reason = ""
        try:
            while not self._stop_event.is_set():
                line = await reader.readline()
                if not line:
                    reason = "APRS-IS server closed the connection."
                    break
                self._process_server_line(line)
        except asyncio.CancelledError:
            return
        except (OSError, ValueError) as exc:
            reason = f"APRS-IS read failed: {exc}"
        if not reason:
            return
        await self._disconnect(reason=reason, status=APRSIS_STATUS_ERROR, error=reason)
        self._retry_not_before = time.monotonic() + self._reconnect_delay

    async def _disconnect(self, *, reason: str, status: str, error: str | None = None) -> None:
        async with self._connection_lock:
            await self._disconnect_locked(reason=reason, status=status, error=error)

    async def _disconnect_locked(self, *, reason: str, status: str, error: str | None = None) -> None:
        reader_task = self._reader_task
        writer = self._writer
        config_key = self._connected_config
        connected_since = self._connected_since
        self._reader_task = None
        self._writer = None
        self._connected_config = None
        self._connected_rx_signature = None
        self._connected_since = None

        if reader_task is not None and not reader_task.done() and reader_task is not asyncio.current_task():
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task

        if writer is not None:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

        if config_key is None:
            if status == APRSIS_STATUS_INACTIVE:
                persist_aprsis_runtime_status(
                    status=APRSIS_STATUS_INACTIVE,
                    status_detail=reason,
                    connected_at=None,
                    last_error=None,
                )
            return

        server, port, login, _passcode = config_key
        persist_aprsis_runtime_status(
            status=status,
            status_detail=reason,
            server=server,
            port=port,
            login=login,
            connected_at=connected_since if status == APRSIS_STATUS_CONNECTED else None,
            last_error=error,
        )

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(delay, 0.05))
        except TimeoutError:
            return

    @staticmethod
    def _rx_signature(rx_interface: dict[str, Any] | None) -> tuple[int, str] | None:
        if rx_interface is None:
            return None
        try:
            interface_id = int(rx_interface["id"])
        except (KeyError, TypeError, ValueError):
            return None
        return interface_id, str(rx_interface.get("filter") or "").strip()

    def _connection_needs_reconnect(
        self,
        *,
        config_key: tuple[str, int, str, str],
        desired_rx_signature: tuple[int, str] | None,
    ) -> bool:
        if self._reader_task is not None and self._reader_task.done():
            return True
        if self._writer is None:
            return False
        if self._connected_config != config_key:
            return True
        # Disabling APRS-IS RX must not tear down a session still needed for
        # TX.  The reader stops dispatching immediately via
        # _desired_rx_interface, while a later reconnect (if needed for any
        # other reason) logs in without the RX filter.
        if desired_rx_signature is None:
            return False
        return self._connected_rx_signature != desired_rx_signature

    def _process_server_line(self, raw_line: bytes | str) -> bool:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("latin-1", errors="replace").rstrip("\r\n")
        else:
            line = str(raw_line or "").rstrip("\r\n")
        normalized_control = line.lstrip()
        if (
            not normalized_control
            or normalized_control.startswith("#")
            or normalized_control.lower().startswith("logresp ")
        ):
            return False

        rx_interface = self._desired_rx_interface
        if rx_interface is None:
            return False
        try:
            interface_id = int(rx_interface["id"])
        except (KeyError, TypeError, ValueError):
            return False
        interface_name = str(rx_interface.get("name") or f"APRSIS #{interface_id}").strip()
        processor = self._rx_processor
        if processor is None:
            from app.services.traffic import process_normalized_tnc2_rx

            processor = process_normalized_tnc2_rx
        try:
            return bool(
                processor(
                    line,
                    source=f"APRS-IS · {interface_name}",
                    source_kind="aprsis",
                    source_interface_id=interface_id,
                    band="",
                    timestamp=utc_now(),
                    rx_received_monotonic=time.monotonic(),
                )
            )
        except Exception as exc:
            log_event("WARNING", "aprsis", f"APRS-IS RX line processing failed: {exc}")
            return False
