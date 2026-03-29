from __future__ import annotations

import asyncio
from collections import deque
from threading import Lock
from typing import Any

from app.db import fetch_one, log_event, utc_now

KISS_FEND = 0xC0
KISS_FESC = 0xDB
KISS_TFEND = 0xDC
KISS_TFESC = 0xDD
AX25_CONTROL_UI = 0x03
AX25_PID_NO_LAYER3 = 0xF0


class TrafficMonitorService:
    def __init__(self, *, reconnect_delay: float = 5.0, max_frames: int = 400) -> None:
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
        self._kiss_buffer = bytearray()

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
                self._kiss_buffer.clear()
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

            self._kiss_buffer.clear()
            connect_message = f"Connected to TCP TNC {modem['name']} at {host}:{port}"
            self._set_state(status="connected", detail=connect_message, modem=modem, error=None)
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
                self._kiss_buffer.clear()
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
                self._kiss_buffer.clear()
                self._set_state(status="error", detail=message, modem=modem, error="Remote side closed the connection.")
                log_event("WARNING", "traffic", message)
                await self._sleep(self._reconnect_delay)
                return

            self._consume_kiss_chunk(chunk)

    def _consume_kiss_chunk(self, chunk: bytes) -> None:
        self._kiss_buffer.extend(chunk)

        while True:
            try:
                start = self._kiss_buffer.index(KISS_FEND)
            except ValueError:
                if len(self._kiss_buffer) > 8192:
                    self._kiss_buffer.clear()
                return

            if start > 0:
                del self._kiss_buffer[:start]

            if len(self._kiss_buffer) < 2:
                return

            try:
                end = self._kiss_buffer.index(KISS_FEND, 1)
            except ValueError:
                return

            raw_frame = bytes(self._kiss_buffer[1:end])
            del self._kiss_buffer[: end + 1]

            if not raw_frame:
                continue

            self._record_kiss_frame(raw_frame)

    def _record_kiss_frame(self, raw_frame: bytes) -> None:
        command = raw_frame[0]
        port = (command >> 4) & 0x0F
        command_id = command & 0x0F
        payload = self._kiss_unescape(raw_frame[1:])
        timestamp = utc_now()

        entry: dict[str, str] = {
            "timestamp": timestamp,
            "source": self._format_modem_label(),
            "port": str(port),
            "command": f"0x{command_id:X}",
            "length": str(len(payload)),
            "hex": payload.hex(" ").upper(),
            "format": "RAW",
            "line": f"port={port} cmd=0x{command_id:X} len={len(payload)}",
            "text": payload.decode("utf-8", errors="replace").strip() or "<binary>",
        }

        if command_id == 0x00:
            decoded = self._decode_ax25_to_tnc2(payload)
            if decoded is not None:
                entry["format"] = "TNC2"
                entry["line"] = decoded
            else:
                entry["format"] = "KISS"
                entry["line"] = f"port={port} AX.25 frame len={len(payload)}"
        else:
            entry["format"] = "KISS-CMD"
            entry["line"] = f"port={port} KISS command 0x{command_id:X} len={len(payload)}"

        with self._lock:
            self._frames.append(entry)
            self._updated_at = timestamp

    def _kiss_unescape(self, payload: bytes) -> bytes:
        output = bytearray()
        index = 0
        while index < len(payload):
            byte = payload[index]
            if byte == KISS_FESC and index + 1 < len(payload):
                next_byte = payload[index + 1]
                if next_byte == KISS_TFEND:
                    output.append(KISS_FEND)
                    index += 2
                    continue
                if next_byte == KISS_TFESC:
                    output.append(KISS_FESC)
                    index += 2
                    continue
            output.append(byte)
            index += 1
        return bytes(output)

    def _decode_ax25_to_tnc2(self, payload: bytes) -> str | None:
        if len(payload) < 16:
            return None

        addresses: list[tuple[str, bool, bool]] = []
        offset = 0

        while offset + 7 <= len(payload):
            chunk = payload[offset : offset + 7]
            address = self._decode_ax25_address(chunk)
            if address is None:
                return None
            addresses.append(address)
            offset += 7
            if chunk[6] & 0x01:
                break
        else:
            return None

        if len(addresses) < 2 or offset + 2 > len(payload):
            return None

        control = payload[offset]
        pid = payload[offset + 1]
        info = payload[offset + 2 :]

        if control != AX25_CONTROL_UI or pid != AX25_PID_NO_LAYER3:
            return None

        destination = addresses[0][0]
        source = addresses[1][0]
        via = []
        for repeater, has_been_repeated, _reserved in addresses[2:]:
            via.append(f"{repeater}{'*' if has_been_repeated else ''}")

        header = f"{source}>{destination}"
        if via:
            header = f"{header},{','.join(via)}"

        info_text = info.decode("utf-8", errors="replace")
        return f"{header}:{info_text}"

    def _decode_ax25_address(self, chunk: bytes) -> tuple[str, bool, bool] | None:
        if len(chunk) != 7:
            return None

        callsign = "".join(chr(byte >> 1) for byte in chunk[:6]).rstrip()
        if not callsign:
            return None

        ssid_value = (chunk[6] >> 1) & 0x0F
        has_been_repeated = bool(chunk[6] & 0x80)
        last_address = bool(chunk[6] & 0x01)

        if ssid_value:
            callsign = f"{callsign}-{ssid_value}"

        return callsign, has_been_repeated, last_address

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

    def _format_modem_label(self) -> str:
        with self._lock:
            modem = dict(self._active_modem) if self._active_modem else None
        if not modem:
            return "TNC"
        name = str(modem.get("name") or "TNC").strip()
        endpoint = str(modem.get("device_path") or "").strip()
        if endpoint:
            return f"{name} ({endpoint})"
        return name

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
