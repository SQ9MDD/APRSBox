from __future__ import annotations

import asyncio
import contextlib
import re
import time
from typing import Any

from app import get_version
from app.db import fetch_one, get_app_setting, get_connection, log_event, set_app_setting, utc_now

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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


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
    def __init__(self, *, poll_interval: float = 1.0, reconnect_delay: float = 5.0) -> None:
        self._poll_interval = poll_interval
        self._reconnect_delay = reconnect_delay
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connection_lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected_config: tuple[str, int, str, str] | None = None
        self._connected_since: str | None = None
        self._retry_not_before = 0.0

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

    async def send_tnc2_line(self, line: str) -> tuple[bool, str]:
        payload_line = str(line or "").rstrip("\r\n")
        if not payload_line:
            return False, "APRS-IS TX skipped: empty packet line."
        wire = payload_line.encode("latin-1", errors="replace") + b"\r\n"
        async with self._connection_lock:
            if self._writer is None:
                return False, "APRS-IS TX skipped: uplink is not connected."
            try:
                self._writer.write(wire)
                await self._writer.drain()
            except OSError as exc:
                detail = f"APRS-IS TX failed: {exc}"
                await self._disconnect_locked(reason=detail, status=APRSIS_STATUS_ERROR, error=str(exc))
                self._retry_not_before = time.monotonic() + self._reconnect_delay
                return False, detail
        return True, "APRS-IS TX queued."

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            desired_active = has_enabled_aprsis_target_flow()
            config = get_aprsis_config()
            config_key = (
                str(config["server"]),
                int(config["port"]),
                str(config["login"]),
                str(config["passcode"]),
            )

            if not desired_active:
                await self._disconnect(
                    reason="APRS-IS uplink inactive because no enabled Packet Routing flow targets APRS-IS.",
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
            async with self._connection_lock:
                if self._reader_task is not None and self._reader_task.done():
                    should_reconnect = True
                if self._writer is not None and self._connected_config != config_key:
                    should_reconnect = True
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
                    await self._connect(config_key)
            await self._sleep(self._poll_interval)

    async def _connect(self, config_key: tuple[str, int, str, str]) -> None:
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

        login_line = f"user {login} pass {passcode or '-1'} vers APRSBox {get_version()}"
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
        except asyncio.CancelledError:
            return
        except OSError as exc:
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
