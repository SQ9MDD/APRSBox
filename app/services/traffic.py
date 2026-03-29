from __future__ import annotations

import asyncio
from collections import deque
from threading import Lock
from typing import Any

from app.db import fetch_one, log_event, utc_now


class TrafficMonitorService:
    def __init__(self, *, reconnect_delay: float = 5.0, max_frames: int = 200) -> None:
        self._reconnect_delay = reconnect_delay
        self._frames: deque[dict[str, str]] = deque(maxlen=max_frames)
        self._lock = Lock()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._status = "idle"
        self._status_detail = "Traffic monitor is starting."
        self._active_modem: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._updated_at = utc_now()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-traffic-monitor")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_modem = dict(self._active_modem) if self._active_modem else None
            frames = [dict(frame) for frame in reversed(self._frames)]
            return {
                "status": self._status,
                "status_detail": self._status_detail,
                "active_modem": active_modem,
                "last_error": self._last_error,
                "updated_at": self._updated_at,
                "frames": frames,
            }

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            modem = self._load_active_tcp_modem()
            if modem is None:
                self._set_state(
                    status="idle",
                    detail="No enabled TCP TNC is configured.",
                    modem=None,
                    error=None,
                )
                await self._sleep(self._reconnect_delay)
                continue

            endpoint = self._parse_endpoint(modem.get("device_path") or "")
            if endpoint is None:
                self._set_state(
                    status="error",
                    detail="Configured TNC address is invalid. Expected format: ip:port.",
                    modem=modem,
                    error="Invalid TCP endpoint in TNC settings.",
                )
                await self._sleep(self._reconnect_delay)
                continue

            host, port = endpoint
            self._set_state(
                status="connecting",
                detail=f"Connecting to {host}:{port}.",
                modem=modem,
                error=None,
            )

            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
            except (OSError, TimeoutError) as exc:
                message = f"TCP connection to {host}:{port} failed: {exc}"
                self._set_state(status="error", detail=message, modem=modem, error=str(exc))
                log_event("WARNING", "traffic", message)
                await self._sleep(self._reconnect_delay)
                continue

            connect_message = f"Connected to TCP TNC {modem['name']} at {host}:{port}"
            self._set_state(
                status="connected",
                detail=connect_message,
                modem=modem,
                error=None,
            )
            log_event("INFO", "traffic", connect_message)

            try:
                await self._consume_connection(reader, modem, host, port)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

    async def _consume_connection(
        self,
        reader: asyncio.StreamReader,
        modem: dict[str, Any],
        host: str,
        port: int,
    ) -> None:
        while not self._stop_event.is_set():
            current_modem = self._load_active_tcp_modem()
            if current_modem != modem:
                self._set_state(
                    status="idle",
                    detail="Active TCP TNC configuration changed. Reconnecting.",
                    modem=current_modem,
                    error=None,
                )
                return

            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            except TimeoutError:
                continue
            except OSError as exc:
                message = f"Read from TCP TNC {host}:{port} failed: {exc}"
                self._set_state(status="error", detail=message, modem=modem, error=str(exc))
                log_event("WARNING", "traffic", message)
                await self._sleep(self._reconnect_delay)
                return

            if not chunk:
                message = f"TCP TNC {host}:{port} closed the connection."
                self._set_state(status="error", detail=message, modem=modem, error="Remote side closed the connection.")
                log_event("WARNING", "traffic", message)
                await self._sleep(self._reconnect_delay)
                return

            self._record_frame(chunk)

    def _record_frame(self, chunk: bytes) -> None:
        text_preview = chunk.decode("utf-8", errors="replace").replace("\r", "\\r").replace("\n", "\\n\n").strip()
        if not text_preview:
            text_preview = "<binary>"
        frame = {
            "timestamp": utc_now(),
            "length": str(len(chunk)),
            "text": text_preview,
            "hex": chunk.hex(" ").upper(),
        }
        with self._lock:
            self._frames.append(frame)
            self._updated_at = frame["timestamp"]

    def _set_state(
        self,
        *,
        status: str,
        detail: str,
        modem: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        with self._lock:
            self._status = status
            self._status_detail = detail
            self._active_modem = dict(modem) if modem else None
            self._last_error = error
            self._updated_at = utc_now()

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    def _load_active_tcp_modem(self) -> dict[str, Any] | None:
        row = fetch_one(
            """
            SELECT id, name, modem_type, device_path, baud_rate, enabled, notes, created_at, updated_at
            FROM modems
            WHERE enabled = 1 AND modem_type = 'TCP'
            ORDER BY id ASC
            LIMIT 1
            """
        )
        return dict(row) if row else None

    def _parse_endpoint(self, value: str) -> tuple[str, int] | None:
        host, separator, port_text = value.strip().rpartition(":")
        if not separator or not host or not port_text:
            return None
        try:
            port = int(port_text)
        except ValueError:
            return None
        if port < 1 or port > 65535:
            return None
        return host.strip(), port
