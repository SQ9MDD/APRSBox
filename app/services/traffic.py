from __future__ import annotations

import asyncio
import ipaddress
import time
from threading import Lock
from typing import Any, Callable

from app.db import fetch_all, fetch_one, get_connection, log_event, traffic_retention_cutoff, utc_now
from app.services.band_condition import process_incoming_frame
from app.services.messages import process_incoming_tnc2_message
from app.services.outbound import persist_outbound_frame
from app.services.radio_activity import record_traffic_device_station_observation
from app.services.serial_broker import SerialKissTcpBroker
from app.services.serial_tnc import normalize_serial_baud_rate, normalize_serial_device_path

KISS_FEND = 0xC0
KISS_FESC = 0xDB
KISS_TFEND = 0xDC
KISS_TFESC = 0xDD
AX25_CONTROL_UI = 0x03
AX25_PID_NO_LAYER3 = 0xF0
EXPOSE_PORT_MAX_CONNECTIONS = 3
SERIAL_RX_SILENCE_RECONNECT_DEFAULT_SECONDS = 150
SERIAL_RX_SILENCE_RECONNECT_ALLOWED_SECONDS = set(range(0, 601, 30))
SUPPORTED_SERIAL_MODEM_TYPES = {"SERIALL", "SERIAL"}
IGNORED_KISS_DEBUG_PREVIEW_BYTES = 24
IGNORED_KISS_DEBUG_INTERVAL_SECONDS = 30.0
SERIAL_TX_DEBUG_PREVIEW_BYTES = 32
KISS_RETURN = 0xFF


def _elapsed_ms_since(start: Any, *, now: float | None = None) -> float | None:
    if not isinstance(start, (int, float)):
        return None
    reference = now if now is not None else time.monotonic()
    delta_ms = (reference - float(start)) * 1000.0
    if delta_ms < 0:
        return 0.0
    return delta_ms


def _kiss_frame_hex_preview(frame: bytes, *, max_bytes: int = SERIAL_TX_DEBUG_PREVIEW_BYTES) -> str:
    if not frame:
        return "<empty>"
    if len(frame) <= max_bytes:
        return frame.hex(" ").upper()
    head_len = max_bytes // 2
    tail_len = max_bytes - head_len
    head = frame[:head_len].hex(" ").upper()
    tail = frame[-tail_len:].hex(" ").upper()
    return f"{head} ... {tail}"


def _normalize_modem_type(value: Any) -> str:
    modem_type = str(value or "").strip().upper()
    if modem_type == "SERIAL":
        return "SERIALL"
    return modem_type


def _normalize_serial_rx_silence_reconnect_seconds(value: Any) -> int:
    raw = str(value if value is not None else SERIAL_RX_SILENCE_RECONNECT_DEFAULT_SECONDS).strip()
    if not raw:
        return SERIAL_RX_SILENCE_RECONNECT_DEFAULT_SECONDS
    try:
        timeout_seconds = int(raw)
    except ValueError:
        return SERIAL_RX_SILENCE_RECONNECT_DEFAULT_SECONDS
    if timeout_seconds not in SERIAL_RX_SILENCE_RECONNECT_ALLOWED_SECONDS:
        return SERIAL_RX_SILENCE_RECONNECT_DEFAULT_SECONDS
    return timeout_seconds


class _TrafficModemRuntime:
    def __init__(
        self,
        *,
        modem_id: int | None = None,
        reconnect_delay: float = 5.0,
        max_frames: int = 400,
        frame_consumer: Callable[[str], None] | Callable[..., None] | None = None,
    ) -> None:
        self._modem_id = modem_id
        self._reconnect_delay = reconnect_delay
        self._max_frames = max_frames
        self._frame_consumer = frame_consumer
        self._lock = Lock()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._status = "idle"
        self._status_detail = "Traffic monitor is starting."
        self._active_modem: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._updated_at = utc_now()
        self._kiss_buffer = bytearray()
        self._proxy_uplink_buffer = bytearray()
        self._tnc_writer: asyncio.StreamWriter | None = None
        self._serial_broker: SerialKissTcpBroker | None = None
        self._tnc_write_lock = asyncio.Lock()
        self._proxy_server: asyncio.AbstractServer | None = None
        self._proxy_server_key: tuple[str, int, str] | None = None
        self._proxy_clients: set[asyncio.StreamWriter] = set()
        self._proxy_whitelist: tuple[ipaddress.IPv4Network, ...] = ()
        self._proxy_bind_address: str | None = None
        self._proxy_port: int | None = None
        self._proxy_enabled = False
        self._proxy_active_clients = 0
        self._ignored_kiss_non_data = 0
        self._ignored_kiss_garbage = 0
        self._ignored_kiss_debug_next_log_at = 0.0
        self._ignored_kiss_debug_suppressed = 0

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-traffic-monitor")

    async def stop(self) -> None:
        self._stop_event.set()
        await self._stop_proxy_server()
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log_event(
                    "WARNING",
                    "traffic",
                    (
                        f"Traffic runtime stop observed task failure on "
                        f"{self._runtime_label()}: {exc}"
                    ),
                )
        self._task = None
        await self._stop_serial_broker()

    async def send_outbound_frame(self, *, interface_id: int | None, frame: bytes) -> bool:
        with self._lock:
            modem = dict(self._active_modem) if self._active_modem else None
        if modem is None:
            return False
        if interface_id is None:
            return False
        try:
            active_interface_id = int(modem.get("id"))
        except (TypeError, ValueError):
            return False
        if active_interface_id != interface_id:
            return False
        try:
            command = self._validate_outbound_kiss_frame(frame)
        except ValueError as exc:
            log_event(
                "WARNING",
                "traffic",
                (
                    f"Rejected outbound TX frame on {self._runtime_label(modem=modem)}: {exc}. "
                    f"frame={_kiss_frame_hex_preview(frame)}"
                ),
            )
            return False
        log_event(
            "DEBUG",
            "traffic",
            (
                f"Outbound TX frame accepted on {self._runtime_label(modem=modem)}: "
                f"len={len(frame)} cmd=0x{command:02X} frame={_kiss_frame_hex_preview(frame)}"
            ),
        )
        try:
            await self._forward_client_chunk_to_tnc(frame)
        except OSError as exc:
            await self._recover_from_tx_error(modem=modem, exc=exc)
            return False
        except RuntimeError:
            return False
        return True

    async def _stop_serial_broker(self) -> None:
        broker = self._serial_broker
        self._serial_broker = None
        if broker is None:
            return
        await broker.stop()

    def is_running(self) -> bool:
        task = self._task
        return task is not None and not task.done()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_modem = dict(self._active_modem) if self._active_modem else None
            status = self._status
            status_detail = self._status_detail
            last_error = self._last_error
            updated_at = self._updated_at
            expose = {
                "enabled": self._proxy_enabled,
                "bind_address": self._proxy_bind_address,
                "port": self._proxy_port,
                "active_clients": self._proxy_active_clients,
            }
            kiss_stats = {
                "ignored_kiss_non_data": self._ignored_kiss_non_data,
                "ignored_kiss_garbage": self._ignored_kiss_garbage,
            }
        expose["listen_endpoint"] = (
            f"{expose['bind_address']}:{expose['port']}"
            if expose["enabled"] and expose["bind_address"] and expose["port"] is not None
            else None
        )
        rows = fetch_all(
            """
            SELECT source, format, line, port, command, length, hex, created_at
            FROM traffic_frames
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (self._max_frames,),
        )
        frames = [
            {
                "timestamp": row["created_at"],
                "source": row["source"],
                "format": row["format"],
                "line": row["line"],
                "port": row["port"] or "",
                "command": row["command"] or "",
                "length": str(row["length"]),
                "hex": row["hex"] or "",
            }
            for row in rows
        ]
        return {
            "status": status,
            "status_detail": status_detail,
            "active_modem": active_modem,
            "expose": expose,
            "last_error": last_error,
            "updated_at": updated_at,
            "kiss_stats": kiss_stats,
            "frames": frames,
        }

    def runtime_snapshot(self) -> dict[str, Any]:
        with self._lock:
            active_modem = dict(self._active_modem) if self._active_modem else None
            expose = {
                "enabled": self._proxy_enabled,
                "bind_address": self._proxy_bind_address,
                "port": self._proxy_port,
                "active_clients": self._proxy_active_clients,
            }
            kiss_stats = {
                "ignored_kiss_non_data": self._ignored_kiss_non_data,
                "ignored_kiss_garbage": self._ignored_kiss_garbage,
            }
            status = self._status
            status_detail = self._status_detail
            last_error = self._last_error
            updated_at = self._updated_at
        expose["listen_endpoint"] = (
            f"{expose['bind_address']}:{expose['port']}"
            if expose["enabled"] and expose["bind_address"] and expose["port"] is not None
            else None
        )
        return {
            "status": status,
            "status_detail": status_detail,
            "active_modem": active_modem,
            "expose": expose,
            "last_error": last_error,
            "updated_at": updated_at,
            "kiss_stats": kiss_stats,
        }

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                modem = self._load_active_modem()
                if modem is None:
                    self._clear_kiss_buffers()
                    await self._stop_proxy_server()
                    self._set_state(
                        status="idle",
                        detail="No enabled TNC is configured.",
                        modem=None,
                        error=None,
                    )
                    await self._sleep(self._reconnect_delay)
                    continue

                modem_type = _normalize_modem_type(modem.get("modem_type"))
                if modem_type == "TCP":
                    await self._run_tcp_modem(modem)
                    continue
                if modem_type in SUPPORTED_SERIAL_MODEM_TYPES:
                    await self._run_serial_modem(modem)
                    continue

                message = f"TNC {modem.get('name') or modem.get('id') or 'unknown'} uses unsupported modem type {modem_type or '-'}."
                self._set_state(status="error", detail=message, modem=modem, error=message)
                log_event("WARNING", "traffic", message)
                log_event("WARNING", "system", message)
                await self._sleep(self._reconnect_delay)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                try:
                    current_modem = self._load_active_modem()
                except Exception:
                    current_modem = None
                message = (
                    f"Traffic runtime loop crashed on {self._runtime_label(modem=current_modem)}: {exc}. "
                    "Retrying."
                )
                self._set_state(
                    status="error",
                    detail=message,
                    modem=current_modem,
                    error=str(exc),
                )
                log_event("WARNING", "traffic", message)
                log_event("WARNING", "system", message)
                await self._sleep(self._reconnect_delay)

    async def _run_tcp_modem(self, modem: dict[str, Any]) -> None:
        endpoint = self._parse_endpoint(modem.get("device_path") or "")
        if endpoint is None:
            await self._stop_proxy_server()
            self._set_state(
                status="error",
                detail="Configured TNC address is invalid. Expected format: ip:port.",
                modem=modem,
                error="Invalid TCP endpoint in TNC settings.",
            )
            await self._sleep(self._reconnect_delay)
            return

        host, port = endpoint
        await self._run_kiss_tcp_endpoint(
            modem=modem,
            host=host,
            port=port,
            connect_label=f"TCP TNC {modem['name']} at {host}:{port}",
        )

    async def _run_serial_modem(self, modem: dict[str, Any]) -> None:
        try:
            device_path = normalize_serial_device_path(modem.get("device_path"))
            baud_rate = normalize_serial_baud_rate(modem.get("baud_rate"))
        except ValueError as exc:
            await self._stop_proxy_server()
            self._set_state(
                status="error",
                detail=str(exc),
                modem=modem,
                error=str(exc),
            )
            await self._sleep(self._reconnect_delay)
            return

        silence_reconnect_timeout_seconds = _normalize_serial_rx_silence_reconnect_seconds(
            modem.get("serial_rx_silence_reconnect_seconds")
        )
        broker = SerialKissTcpBroker(
            modem_id=int(modem["id"]),
            tnc_name=str(modem.get("name") or ""),
            device_path=device_path,
            baud_rate=baud_rate,
            rx_silence_reconnect_seconds=silence_reconnect_timeout_seconds,
            reconnect_delay=self._reconnect_delay,
        )
        self._serial_broker = broker

        try:
            await broker.start()
        except (OSError, ValueError, RuntimeError) as exc:
            self._serial_broker = None
            message = f"Serial broker start failed for {device_path} at {baud_rate} baud: {exc}"
            self._set_state(status="error", detail=message, modem=modem, error=str(exc))
            log_event("WARNING", "traffic", message)
            log_event("WARNING", "system", message)
            await self._sleep(self._reconnect_delay)
            return

        try:
            while not self._stop_event.is_set():
                current_modem = self._load_active_modem()
                if current_modem != modem:
                    self._clear_kiss_buffers()
                    self._set_state(
                        status="idle",
                        detail="Active TNC configuration changed. Reconnecting.",
                        modem=current_modem,
                        error=None,
                    )
                    return
                await self._run_kiss_tcp_endpoint(
                    modem=modem,
                    host=broker.host,
                    port=broker.port,
                    connect_label=(
                        f"serial broker for {modem['name']} "
                        f"({device_path} -> {broker.host}:{broker.port})"
                    ),
                )
        finally:
            await self._stop_serial_broker()

    async def _run_kiss_tcp_endpoint(
        self,
        *,
        modem: dict[str, Any],
        host: str,
        port: int,
        connect_label: str,
    ) -> None:
        self._set_state(
            status="connecting",
            detail=f"Connecting to {host}:{port}.",
            modem=modem,
            error=None,
        )

        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
        except (OSError, TimeoutError) as exc:
            message = f"Connection to {connect_label} failed: {exc}"
            self._set_state(status="error", detail=message, modem=modem, error=str(exc))
            log_event("WARNING", "traffic", message)
            await self._sleep(self._reconnect_delay)
            return

        self._clear_kiss_buffers()
        connect_message = f"Connected to {connect_label}"
        self._tnc_writer = writer
        proxy_error = await self._sync_proxy_server(modem)
        self._set_state(status="connected", detail=connect_message, modem=modem, error=proxy_error)
        log_event("INFO", "traffic", connect_message)

        try:
            await self._consume_connection(reader, modem, host, port)
        finally:
            if self._tnc_writer is writer:
                self._tnc_writer = None
            await self._stop_proxy_server()
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
            current_modem = self._load_active_modem()
            if current_modem != modem:
                self._clear_kiss_buffers()
                self._set_state(
                    status="idle",
                    detail="Active TNC configuration changed. Reconnecting.",
                    modem=current_modem,
                    error=None,
                )
                return

            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=5.0)
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
                self._clear_kiss_buffers()
                self._set_state(status="error", detail=message, modem=modem, error="Remote side closed the connection.")
                log_event("WARNING", "traffic", message)
                await self._sleep(self._reconnect_delay)
                return

            await self._broadcast_proxy_chunk(chunk)
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
                if len(self._kiss_buffer) > 8192:
                    self._kiss_buffer.clear()
                return

            raw_frame = bytes(self._kiss_buffer[1:end])
            del self._kiss_buffer[:end]

            if not raw_frame:
                continue

            self._record_kiss_frame(raw_frame)

    def _consume_proxy_uplink_chunk(self, chunk: bytes) -> None:
        self._proxy_uplink_buffer.extend(chunk)

        while True:
            try:
                start = self._proxy_uplink_buffer.index(KISS_FEND)
            except ValueError:
                if len(self._proxy_uplink_buffer) > 8192:
                    self._proxy_uplink_buffer.clear()
                return

            if start > 0:
                del self._proxy_uplink_buffer[:start]

            if len(self._proxy_uplink_buffer) < 2:
                return

            try:
                end = self._proxy_uplink_buffer.index(KISS_FEND, 1)
            except ValueError:
                if len(self._proxy_uplink_buffer) > 8192:
                    self._proxy_uplink_buffer.clear()
                return

            raw_frame = bytes(self._proxy_uplink_buffer[1:end])
            del self._proxy_uplink_buffer[:end]

            if not raw_frame:
                continue

            self._record_proxy_uplink_frame(raw_frame)

    def _record_proxy_uplink_frame(self, raw_frame: bytes) -> None:
        command = raw_frame[0]
        command_id = command & 0x0F
        if command_id != 0x00:
            return

        port = (command >> 4) & 0x0F
        payload = self._kiss_unescape(raw_frame[1:])
        decoded = self._decode_ax25_to_tnc2(payload)
        if decoded is None:
            return

        interface_id: int | None = None
        band = ""
        with self._lock:
            if self._active_modem:
                try:
                    interface_id = int(self._active_modem["id"])
                except (TypeError, ValueError, KeyError):
                    interface_id = None
                band = str(self._active_modem.get("band") or "").strip()
            self._updated_at = utc_now()

        kiss_frame = bytes([KISS_FEND]) + raw_frame + bytes([KISS_FEND])
        persist_outbound_frame(
            source=self._format_modem_label(),
            interface_id=interface_id,
            band=band,
            line=decoded,
            port=str(port),
            command="TX-PROXY",
            payload_hex=kiss_frame.hex(" ").upper(),
        )

    def _record_kiss_frame(self, raw_frame: bytes) -> None:
        rx_monotonic = time.monotonic()
        command = raw_frame[0]
        port = (command >> 4) & 0x0F
        command_id = command & 0x0F
        payload = self._kiss_unescape(raw_frame[1:])
        if command_id != 0x00:
            reason = "garbage" if self._looks_like_kiss_garbage(raw_frame) else "non-data"
            self._register_ignored_kiss_frame(
                reason=reason,
                port=port,
                command_id=command_id,
                payload=payload,
                raw_frame=raw_frame,
            )
            return
        timestamp = utc_now()

        entry: dict[str, Any] = {
            "timestamp": timestamp,
            "source": self._format_modem_label(),
            "port": str(port),
            "command": f"0x{command_id:X}",
            "length": str(len(payload)),
            "hex": payload.hex(" ").upper(),
            "format": "RAW",
            "line": f"port={port} cmd=0x{command_id:X} len={len(payload)}",
            "text": payload.decode("utf-8", errors="replace").strip() or "<binary>",
            "_rx_monotonic": rx_monotonic,
        }

        decoded = self._decode_ax25_to_tnc2(payload)
        if decoded is not None:
            entry["format"] = "TNC2"
            entry["line"] = decoded
        else:
            entry["format"] = "KISS"
            entry["line"] = f"port={port} AX.25 frame len={len(payload)}"

        self._persist_frame(entry, timestamp)
        with self._lock:
            self._updated_at = timestamp

    def _register_ignored_kiss_frame(
        self,
        *,
        reason: str,
        port: int,
        command_id: int,
        payload: bytes,
        raw_frame: bytes,
    ) -> None:
        with self._lock:
            if reason == "garbage":
                self._ignored_kiss_garbage += 1
            else:
                self._ignored_kiss_non_data += 1
            self._updated_at = utc_now()
        self._log_ignored_kiss_frame(
            reason=reason,
            port=port,
            command_id=command_id,
            payload=payload,
            raw_frame=raw_frame,
        )

    def _looks_like_kiss_garbage(self, raw_frame: bytes) -> bool:
        for byte in raw_frame:
            if byte in {9, 10, 13}:
                continue
            if 32 <= byte <= 126:
                continue
            return False
        return True

    def _log_ignored_kiss_frame(
        self,
        *,
        reason: str,
        port: int,
        command_id: int,
        payload: bytes,
        raw_frame: bytes,
    ) -> None:
        now = time.monotonic()
        suppressed = 0
        with self._lock:
            if now < self._ignored_kiss_debug_next_log_at:
                self._ignored_kiss_debug_suppressed += 1
                return
            suppressed = self._ignored_kiss_debug_suppressed
            self._ignored_kiss_debug_suppressed = 0
            self._ignored_kiss_debug_next_log_at = now + IGNORED_KISS_DEBUG_INTERVAL_SECONDS

        preview = raw_frame[:IGNORED_KISS_DEBUG_PREVIEW_BYTES].hex(" ").upper()
        if len(raw_frame) > IGNORED_KISS_DEBUG_PREVIEW_BYTES:
            preview = f"{preview} ..."
        if not preview:
            preview = "<empty>"
        suppressed_suffix = f"; suppressed={suppressed}" if suppressed > 0 else ""
        log_event(
            "DEBUG",
            "traffic",
            (
                f"Ignored KISS {reason} frame on {self._runtime_label()}: "
                f"port={port} command=0x{command_id:X} len={len(payload)} "
                f"raw={preview}{suppressed_suffix}"
            ),
        )

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

        header = f"{source} > {destination}"
        if via:
            header = f"{header} , {','.join(via)}"

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

    def _validate_outbound_kiss_frame(self, frame: bytes) -> int:
        if len(frame) < 3:
            raise ValueError("KISS frame is too short.")
        if frame[0] != KISS_FEND or frame[-1] != KISS_FEND:
            raise ValueError("KISS frame must start and end with FEND 0xC0.")
        command = frame[1]
        if command == KISS_RETURN:
            raise ValueError("KISS RETURN command 0xFF is not allowed on TX.")
        if command != 0x00:
            raise ValueError(f"KISS command byte must be 0x00 for data frames on port 0, got 0x{command:02X}.")
        return command

    async def _sync_proxy_server(self, modem: dict[str, Any]) -> str | None:
        try:
            config = self._proxy_config_from_modem(modem)
        except ValueError as exc:
            self._update_proxy_state(enabled=False, bind_address=None, port=None, active_clients=0)
            message = f"Expose port configuration for TNC {modem['name']} is invalid: {exc}"
            log_event("WARNING", "traffic", message)
            return message
        if config is None:
            await self._stop_proxy_server()
            return None

        server_key = (config["bind_address"], config["port"], config["whitelist"])
        if self._proxy_server is not None and self._proxy_server_key == server_key:
            return None

        await self._stop_proxy_server()
        try:
            self._proxy_server = await asyncio.start_server(
                self._handle_proxy_client,
                host=config["bind_address"],
                port=config["port"],
            )
        except OSError as exc:
            self._proxy_server = None
            self._proxy_server_key = None
            self._proxy_whitelist = ()
            self._update_proxy_state(enabled=False, bind_address=None, port=None, active_clients=0)
            message = (
                f"Expose port bind failed for TNC {modem['name']} "
                f"on {config['bind_address']}:{config['port']}: {exc}"
            )
            log_event("WARNING", "traffic", message)
            return message

        self._proxy_server_key = server_key
        self._proxy_whitelist = self._parse_whitelist(config["whitelist"])
        self._update_proxy_state(
            enabled=True,
            bind_address=config["bind_address"],
            port=config["port"],
            active_clients=0,
        )
        log_event(
            "INFO",
            "traffic",
            f"Expose port server for TNC {modem['name']} is listening on {config['bind_address']}:{config['port']}",
        )
        return None

    async def _stop_proxy_server(self) -> None:
        clients = list(self._proxy_clients)
        self._proxy_clients.clear()
        for writer in clients:
            writer.close()
        for writer in clients:
            try:
                await writer.wait_closed()
            except OSError:
                pass
        if self._proxy_server is not None:
            self._proxy_server.close()
            await self._proxy_server.wait_closed()
        self._proxy_server = None
        self._proxy_server_key = None
        self._proxy_whitelist = ()
        self._update_proxy_state(enabled=False, bind_address=None, port=None, active_clients=0)

    async def _handle_proxy_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        client_host = str(peer[0]) if isinstance(peer, tuple) and peer else "unknown"

        if self._proxy_server is None or self._tnc_writer is None:
            await self._close_proxy_client(writer)
            return

        if not self._is_proxy_client_allowed(client_host):
            log_event("INFO", "traffic", f"Expose port client {client_host} rejected by whitelist")
            await self._close_proxy_client(writer)
            return

        if len(self._proxy_clients) >= EXPOSE_PORT_MAX_CONNECTIONS:
            log_event("INFO", "traffic", f"Expose port client {client_host} rejected because the client limit was reached")
            await self._close_proxy_client(writer)
            return

        self._proxy_clients.add(writer)
        self._update_proxy_state(active_clients=len(self._proxy_clients))
        log_event("INFO", "traffic", f"Expose port client {client_host} connected")

        try:
            while not self._stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=1.0)
                except TimeoutError:
                    continue
                except OSError as exc:
                    log_event("WARNING", "traffic", f"Read from expose port client {client_host} failed: {exc}")
                    break

                if not chunk:
                    break

                try:
                    await self._forward_client_chunk_to_tnc(chunk, record_proxy_tx=True)
                except OSError as exc:
                    log_event("WARNING", "traffic", f"Forward from expose port client {client_host} failed: {exc}")
                    break
                except RuntimeError as exc:
                    log_event("WARNING", "traffic", f"Expose port client {client_host} dropped: {exc}")
                    break
        finally:
            if writer in self._proxy_clients:
                self._proxy_clients.remove(writer)
            self._update_proxy_state(active_clients=len(self._proxy_clients))
            log_event("INFO", "traffic", f"Expose port client {client_host} disconnected")
            await self._close_proxy_client(writer)

    async def _broadcast_proxy_chunk(self, chunk: bytes) -> None:
        if not self._proxy_clients:
            return
        failed_clients: list[asyncio.StreamWriter] = []
        for writer in list(self._proxy_clients):
            try:
                writer.write(chunk)
                await writer.drain()
            except OSError:
                failed_clients.append(writer)
        if failed_clients:
            for writer in failed_clients:
                if writer in self._proxy_clients:
                    self._proxy_clients.remove(writer)
                await self._close_proxy_client(writer)
            self._update_proxy_state(active_clients=len(self._proxy_clients))

    async def _forward_client_chunk_to_tnc(self, chunk: bytes, *, record_proxy_tx: bool = False) -> None:
        async with self._tnc_write_lock:
            payload_length = len(chunk)
            command = chunk[1] if payload_length >= 2 and chunk[0] == KISS_FEND else None
            command_text = f"0x{command:02X}" if command is not None else "n/a"
            preview = _kiss_frame_hex_preview(chunk)
            if self._tnc_writer is not None:
                log_event(
                    "DEBUG",
                    "traffic",
                    (
                        f"TX start on {self._runtime_label()} via TCP: "
                        f"len={payload_length} cmd={command_text} frame={preview}"
                    ),
                )
                self._tnc_writer.write(chunk)
                await self._tnc_writer.drain()
                if record_proxy_tx:
                    self._consume_proxy_uplink_chunk(chunk)
                log_event(
                    "DEBUG",
                    "traffic",
                    (
                        f"TX end on {self._runtime_label()} via TCP: "
                        f"len={payload_length} cmd={command_text}"
                    ),
                )
                return
            raise RuntimeError("TNC connection is not available.")

    async def _recover_from_tx_error(self, *, modem: dict[str, Any] | None, exc: OSError) -> None:
        async with self._tnc_write_lock:
            writer = self._tnc_writer
            self._tnc_writer = None
        message = (
            f"Transmit to {self._runtime_label(modem=modem)} failed: {exc}. "
            "Closing current link and reconnecting."
        )

        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

        self._clear_kiss_buffers()
        self._set_state(
            status="error",
            detail=message,
            modem=modem,
            error=str(exc),
        )
        log_event("WARNING", "traffic", message)
        log_event("WARNING", "system", message)

    async def _close_proxy_client(self, writer: asyncio.StreamWriter) -> None:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    def _proxy_config_from_modem(self, modem: dict[str, Any]) -> dict[str, Any] | None:
        if not modem.get("expose_port_enabled"):
            return None
        bind_address = str(modem.get("expose_bind_address") or "").strip()
        try:
            parsed_bind = ipaddress.ip_address(bind_address)
        except ValueError as exc:
            raise ValueError("Bind address must be a valid IPv4 address.") from exc
        if parsed_bind.version != 4:
            raise ValueError("Bind address must be a valid IPv4 address.")
        try:
            port = int(modem.get("expose_port"))
        except (TypeError, ValueError):
            raise ValueError("Expose port must be between 1 and 65535.") from None
        if port < 1 or port > 65535:
            raise ValueError("Expose port must be between 1 and 65535.")
        whitelist = str(modem.get("expose_whitelist") or "").strip()
        self._parse_whitelist(whitelist)
        return {
            "bind_address": str(parsed_bind),
            "port": port,
            "whitelist": whitelist,
        }

    def _parse_whitelist(self, whitelist: str) -> tuple[ipaddress.IPv4Network, ...]:
        networks: list[ipaddress.IPv4Network] = []
        for raw_entry in whitelist.splitlines():
            entry = raw_entry.strip()
            if not entry:
                continue
            networks.append(ipaddress.ip_network(entry, strict=False))
        return tuple(networks)

    def _is_proxy_client_allowed(self, client_host: str) -> bool:
        if not self._proxy_whitelist:
            return True
        try:
            address = ipaddress.ip_address(client_host)
        except ValueError:
            return False
        if address.version != 4:
            return False
        return any(address in network for network in self._proxy_whitelist)

    def _update_proxy_state(
        self,
        *,
        enabled: bool | None = None,
        bind_address: str | None = None,
        port: int | None = None,
        active_clients: int | None = None,
    ) -> None:
        with self._lock:
            if enabled is not None:
                self._proxy_enabled = enabled
                self._proxy_bind_address = bind_address
                self._proxy_port = port
            if active_clients is not None:
                self._proxy_active_clients = active_clients
            self._updated_at = utc_now()
        self._persist_runtime_state()

    def _set_state(
        self,
        *,
        status: str,
        detail: str,
        modem: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        timestamp = utc_now()
        with self._lock:
            self._status = status
            self._status_detail = detail
            self._active_modem = dict(modem) if modem else None
            self._last_error = error
            self._updated_at = timestamp
        self._persist_runtime_state()

    def _persist_runtime_state(self) -> None:
        payload = self._runtime_state_payload()
        modem_id = payload.get("modem_id")
        if modem_id in {None, ""}:
            return
        if fetch_one("SELECT id FROM modems WHERE id = ?", (modem_id,)) is None:
            return
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO traffic_runtime_interfaces(
                    modem_id, modem_name, modem_endpoint, band,
                    status, status_detail,
                    expose_port_enabled, expose_bind_address, expose_port, expose_active_clients,
                    last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(modem_id) DO UPDATE SET
                    modem_name = excluded.modem_name,
                    modem_endpoint = excluded.modem_endpoint,
                    band = excluded.band,
                    status = excluded.status,
                    status_detail = excluded.status_detail,
                    expose_port_enabled = excluded.expose_port_enabled,
                    expose_bind_address = excluded.expose_bind_address,
                    expose_port = excluded.expose_port,
                    expose_active_clients = excluded.expose_active_clients,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    modem_id,
                    payload["modem_name"],
                    payload["modem_endpoint"],
                    payload["band"],
                    payload["status"],
                    payload["detail"],
                    payload["proxy_enabled"],
                    payload["proxy_bind_address"],
                    payload["proxy_port"],
                    payload["proxy_active_clients"],
                    payload["error"],
                    payload["updated_at"],
                ),
            )

    def _runtime_state_payload(self) -> dict[str, Any]:
        with self._lock:
            modem = dict(self._active_modem) if self._active_modem else None
            return {
                "modem_id": int(modem["id"]) if modem and modem.get("id") is not None else self._modem_id,
                "status": self._status,
                "detail": self._status_detail,
                "modem_name": str(modem.get("name") or "").strip() if modem else "",
                "modem_endpoint": str(modem.get("device_path") or "").strip() if modem else "",
                "band": str(modem.get("band") or "").strip() if modem else "",
                "proxy_enabled": int(self._proxy_enabled),
                "proxy_bind_address": self._proxy_bind_address,
                "proxy_port": self._proxy_port,
                "proxy_active_clients": self._proxy_active_clients,
                "error": self._last_error,
                "updated_at": self._updated_at,
            }

    def _format_modem_label(self) -> str:
        with self._lock:
            modem = dict(self._active_modem) if self._active_modem else None
        if not modem:
            return "TNC"
        return str(modem.get("name") or "TNC").strip()

    def _runtime_label(self, *, modem: dict[str, Any] | None = None) -> str:
        target = modem
        if target is None:
            with self._lock:
                target = dict(self._active_modem) if self._active_modem else None
        if target:
            name = str(target.get("name") or "").strip()
            modem_id = target.get("id")
            if name and modem_id not in {None, ""}:
                return f"{name} (id={modem_id})"
            if name:
                return name
            if modem_id not in {None, ""}:
                return f"id={modem_id}"
        if self._modem_id is not None:
            return f"id={self._modem_id}"
        return "unknown modem"

    def _persist_frame(self, entry: dict[str, Any], timestamp: str) -> None:
        cutoff = traffic_retention_cutoff()
        active_band = ""
        interface_id: int | None = None
        rx_monotonic = entry.get("_rx_monotonic")
        rx_to_igate_enqueue_ms: float | None = None
        with self._lock:
            if self._active_modem:
                active_band = str(self._active_modem.get("band") or "").strip()
                try:
                    interface_id = int(self._active_modem["id"])
                except (TypeError, ValueError, KeyError):
                    interface_id = None
        if entry["format"] == "TNC2" and self._frame_consumer is not None:
            enqueue_started_at = time.monotonic()
            rx_to_igate_enqueue_ms = _elapsed_ms_since(rx_monotonic, now=enqueue_started_at)
            try:
                self._frame_consumer(
                    str(entry["line"]),
                    source_ref=self._format_modem_label(),
                    rx_received_at=timestamp,
                    rx_received_monotonic=rx_monotonic,
                )
            except TypeError:
                self._frame_consumer(str(entry["line"]), source_ref=self._format_modem_label())
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES (?, ?, 'rx', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["source"],
                    interface_id,
                    active_band,
                    entry["format"],
                    entry["line"],
                    entry["port"],
                    entry["command"],
                    int(entry["length"]),
                    entry["hex"],
                    timestamp,
                ),
            )
            connection.execute("DELETE FROM traffic_frames WHERE created_at < ?", (cutoff,))
        rx_to_db_commit_ms = _elapsed_ms_since(rx_monotonic)
        if entry["format"] == "TNC2":
            details = [
                f"source={entry['source']}",
                f"line={str(entry['line'])[:120]}",
            ]
            if rx_to_igate_enqueue_ms is not None:
                details.append(f"rx_to_igate_enqueue_ms={rx_to_igate_enqueue_ms:.3f}")
            if rx_to_db_commit_ms is not None:
                details.append(f"rx_to_db_commit_ms={rx_to_db_commit_ms:.3f}")
            log_event("DEBUG", "traffic_latency", " | ".join(details))
        try:
            record_traffic_device_station_observation(
                frame_format=entry["format"],
                line=entry["line"],
                timestamp=timestamp,
            )
        except Exception as exc:
            log_event("WARNING", "statistics", f"Failed to update devices statistics buffer: {exc}")
        if entry["format"] == "TNC2":
            process_incoming_frame(entry["line"], band=active_band, timestamp=timestamp)
            process_incoming_tnc2_message(entry["line"], timestamp=timestamp)

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    def _load_active_modem(self) -> dict[str, Any] | None:
        params: tuple[Any, ...] = ()
        if self._modem_id is None:
            query = """
                SELECT
                    id,
                    name,
                    band,
                    modem_type,
                    device_path,
                    baud_rate,
                    serial_rx_silence_reconnect_seconds,
                    enabled,
                    expose_port_enabled,
                    expose_bind_address,
                    expose_port,
                    expose_whitelist,
                    notes,
                    created_at,
                    updated_at
                FROM modems
                WHERE enabled = 1 AND modem_type IN ('TCP', 'SERIALL', 'SERIAL')
                ORDER BY id ASC
                LIMIT 1
            """
        else:
            query = """
                SELECT
                    id,
                    name,
                    band,
                    modem_type,
                    device_path,
                    baud_rate,
                    serial_rx_silence_reconnect_seconds,
                    enabled,
                    expose_port_enabled,
                    expose_bind_address,
                    expose_port,
                    expose_whitelist,
                    notes,
                    created_at,
                    updated_at
                FROM modems
                WHERE id = ? AND enabled = 1 AND modem_type IN ('TCP', 'SERIALL', 'SERIAL')
                LIMIT 1
            """
            params = (self._modem_id,)
        row = fetch_one(query, params)
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

    def _clear_kiss_buffers(self) -> None:
        self._kiss_buffer.clear()
        self._proxy_uplink_buffer.clear()


class TrafficMonitorService:
    def __init__(
        self,
        *,
        reconnect_delay: float = 5.0,
        max_frames: int = 400,
        frame_consumer: Callable[[str], None] | Callable[..., None] | None = None,
    ) -> None:
        self._reconnect_delay = reconnect_delay
        self._max_frames = max_frames
        self._frame_consumer = frame_consumer
        self._lock = Lock()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._runtimes: dict[int, _TrafficModemRuntime] = {}
        self._runtime_signatures: dict[int, tuple[Any, ...]] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="aprsbox-traffic-monitor-manager")

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log_event("WARNING", "traffic", f"Traffic monitor manager stop observed task failure: {exc}")
            self._task = None
        runtimes = self._runtime_instances()
        for runtime in runtimes:
            await runtime.stop()
        with self._lock:
            self._runtimes.clear()
            self._runtime_signatures.clear()
        with get_connection() as connection:
            connection.execute("DELETE FROM traffic_runtime_interfaces")
        self._persist_summary_state()

    async def send_outbound_frame(self, *, interface_id: int | None, frame: bytes) -> bool:
        if interface_id is None:
            return False
        runtime = self._runtime_for_interface(interface_id)
        if runtime is None:
            return False
        return await runtime.send_outbound_frame(interface_id=interface_id, frame=frame)

    def snapshot(self) -> dict[str, Any]:
        interfaces = self._runtime_snapshots()
        summary = self._aggregate_runtime_snapshot(interfaces)
        rows = fetch_all(
            """
            SELECT source, interface_id, direction, band, format, line, port, command, length, hex, created_at
            FROM traffic_frames
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (self._max_frames,),
        )
        summary["interfaces"] = interfaces
        summary["frames"] = [
            {
                "timestamp": row["created_at"],
                "source": row["source"],
                "interface_id": int(row["interface_id"]) if row["interface_id"] is not None else None,
                "direction": str(row["direction"] or "").upper() or ("TX" if str(row["format"] or "").endswith("-TX") else "RX"),
                "band": str(row["band"] or "").strip(),
                "format": row["format"],
                "line": row["line"],
                "port": row["port"] or "",
                "command": row["command"] or "",
                "length": str(row["length"]),
                "hex": row["hex"] or "",
            }
            for row in rows
        ]
        return summary

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await self._sync_runtimes()
                    self._persist_summary_state()
                    await self._sleep(1.0)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_event("WARNING", "traffic", f"Traffic monitor manager loop failed: {exc}. Retrying.")
                    await self._sleep(self._reconnect_delay)
        finally:
            self._persist_summary_state()

    async def _sync_runtimes(self) -> None:
        enabled_modems = self._load_enabled_modems()
        desired_by_id = {int(modem["id"]): modem for modem in enabled_modems}
        existing_ids = set(self._runtime_signatures)
        desired_ids = set(desired_by_id)

        for modem_id in sorted(existing_ids - desired_ids):
            runtime = self._pop_runtime(modem_id)
            if runtime is not None:
                await runtime.stop()
            self._delete_runtime_state(modem_id)

        for modem in enabled_modems:
            modem_id = int(modem["id"])
            signature = self._runtime_signature(modem)
            current_signature = self._runtime_signatures.get(modem_id)
            current_runtime = self._runtime_for_interface(modem_id)
            if current_signature == signature and current_runtime is not None:
                if current_runtime.is_running():
                    continue
                log_event(
                    "WARNING",
                    "traffic",
                    (
                        f"Traffic runtime for modem {modem.get('name') or modem_id} stopped unexpectedly. "
                        "Recreating runtime."
                    ),
                )
            runtime = self._pop_runtime(modem_id)
            if runtime is not None:
                await runtime.stop()
            runtime = _TrafficModemRuntime(
                modem_id=modem_id,
                reconnect_delay=self._reconnect_delay,
                max_frames=self._max_frames,
                frame_consumer=self._frame_consumer,
            )
            with self._lock:
                self._runtimes[modem_id] = runtime
                self._runtime_signatures[modem_id] = signature
            await runtime.start()

    def _load_enabled_modems(self) -> list[dict[str, Any]]:
        rows = fetch_all(
            """
            SELECT
                id,
                name,
                band,
                modem_type,
                device_path,
                baud_rate,
                serial_rx_silence_reconnect_seconds,
                enabled,
                expose_port_enabled,
                expose_bind_address,
                expose_port,
                expose_whitelist,
                notes,
                created_at,
                updated_at
            FROM modems
            WHERE enabled = 1 AND modem_type IN ('TCP', 'SERIALL', 'SERIAL')
            ORDER BY id ASC
            """
        )
        return [dict(row) for row in rows]

    def _runtime_signature(self, modem: dict[str, Any]) -> tuple[Any, ...]:
        return (
            int(modem["id"]),
            str(modem.get("name") or "").strip(),
            str(modem.get("band") or "").strip(),
            _normalize_modem_type(modem.get("modem_type")),
            str(modem.get("device_path") or "").strip(),
            modem.get("baud_rate"),
            modem.get("serial_rx_silence_reconnect_seconds"),
            int(bool(modem.get("expose_port_enabled"))),
            str(modem.get("expose_bind_address") or "").strip(),
            int(modem.get("expose_port") or 0),
            str(modem.get("expose_whitelist") or "").strip(),
        )

    def _runtime_instances(self) -> list[_TrafficModemRuntime]:
        with self._lock:
            return list(self._runtimes.values())

    def _runtime_for_interface(self, modem_id: int) -> _TrafficModemRuntime | None:
        with self._lock:
            return self._runtimes.get(modem_id)

    def _pop_runtime(self, modem_id: int) -> _TrafficModemRuntime | None:
        with self._lock:
            self._runtime_signatures.pop(modem_id, None)
            return self._runtimes.pop(modem_id, None)

    def _runtime_snapshots(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for runtime in self._runtime_instances():
            snapshot = runtime.runtime_snapshot()
            modem = snapshot.get("active_modem") or {}
            expose = dict(snapshot.get("expose") or {})
            kiss_stats = dict(snapshot.get("kiss_stats") or {})
            expose["listen_endpoint"] = (
                f"{expose.get('bind_address')}:{expose.get('port')}"
                if expose.get("enabled") and expose.get("bind_address") and expose.get("port") is not None
                else None
            )
            snapshots.append(
                {
                    "modem_id": int(modem["id"]) if modem.get("id") is not None else None,
                    "name": str(modem.get("name") or "").strip(),
                    "device_path": str(modem.get("device_path") or "").strip(),
                    "band": str(modem.get("band") or "").strip(),
                    "status": snapshot.get("status") or "idle",
                    "status_detail": snapshot.get("status_detail") or "",
                    "last_error": snapshot.get("last_error"),
                    "updated_at": snapshot.get("updated_at"),
                    "ignored_kiss_non_data": int(kiss_stats.get("ignored_kiss_non_data") or 0),
                    "ignored_kiss_garbage": int(kiss_stats.get("ignored_kiss_garbage") or 0),
                    "expose": expose,
                }
            )
        snapshots.sort(key=lambda item: ((item.get("modem_id") is None), item.get("modem_id") or 0, item.get("name") or ""))
        return snapshots

    def _aggregate_runtime_snapshot(self, interfaces: list[dict[str, Any]]) -> dict[str, Any]:
        if not interfaces:
            return {
                "status": "idle",
                "status_detail": "No enabled TNC is configured.",
                "active_modem": None,
                "expose": {
                    "enabled": False,
                    "bind_address": None,
                    "port": None,
                    "active_clients": 0,
                    "listen_endpoint": None,
                },
                "last_error": None,
                "updated_at": None,
                "connected_interfaces": 0,
                "modem_count": 0,
            }

        if len(interfaces) == 1:
            interface = interfaces[0]
            active_modem = None
            if interface["name"] or interface["device_path"]:
                active_modem = {
                    "id": interface["modem_id"],
                    "name": interface["name"],
                    "device_path": interface["device_path"],
                    "band": interface["band"],
                }
            return {
                "status": interface["status"],
                "status_detail": interface["status_detail"],
                "active_modem": active_modem,
                "expose": dict(interface["expose"]),
                "last_error": interface["last_error"],
                "updated_at": interface["updated_at"],
                "connected_interfaces": 1 if interface["status"] == "connected" else 0,
                "modem_count": 1,
            }

        connected = [item for item in interfaces if item["status"] == "connected"]
        connecting = [item for item in interfaces if item["status"] == "connecting"]
        errored = [item for item in interfaces if item.get("last_error")]
        preferred = connected[0] if connected else interfaces[0]
        if connected:
            status = "connected"
            detail = f"{len(connected)}/{len(interfaces)} TNC interfaces connected."
        elif connecting:
            status = "connecting"
            detail = f"Connecting {len(connecting)} TNC interface(s)."
        elif errored:
            status = "error"
            detail = str(errored[0].get("last_error") or preferred["status_detail"] or "TNC interfaces failed.")
        else:
            status = preferred["status"]
            detail = preferred["status_detail"]
        active_modem = None
        if preferred["name"] or preferred["device_path"]:
            active_modem = {
                "id": preferred["modem_id"],
                "name": preferred["name"],
                "device_path": preferred["device_path"],
                "band": preferred["band"],
            }
        total_clients = sum(int((item.get("expose") or {}).get("active_clients") or 0) for item in interfaces)
        updated_at = max((str(item.get("updated_at") or "") for item in interfaces), default="") or None
        return {
            "status": status,
            "status_detail": detail,
            "active_modem": active_modem,
            "expose": {
                "enabled": any(bool((item.get("expose") or {}).get("enabled")) for item in interfaces),
                "bind_address": None,
                "port": None,
                "active_clients": total_clients,
                "listen_endpoint": None,
            },
            "last_error": str(errored[0].get("last_error")) if errored else None,
            "updated_at": updated_at,
            "connected_interfaces": len(connected),
            "modem_count": len(interfaces),
        }

    def _persist_summary_state(self) -> None:
        interfaces = self._runtime_snapshots()
        summary = self._aggregate_runtime_snapshot(interfaces)
        active_modem = dict(summary.get("active_modem") or {})
        expose = dict(summary.get("expose") or {})
        updated_at = str(summary.get("updated_at") or utc_now())
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO traffic_runtime_state (
                    id, status, status_detail, active_modem_name, active_modem_endpoint,
                    expose_port_enabled, expose_bind_address, expose_port, expose_active_clients,
                    last_error, updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    status_detail = excluded.status_detail,
                    active_modem_name = excluded.active_modem_name,
                    active_modem_endpoint = excluded.active_modem_endpoint,
                    expose_port_enabled = excluded.expose_port_enabled,
                    expose_bind_address = excluded.expose_bind_address,
                    expose_port = excluded.expose_port,
                    expose_active_clients = excluded.expose_active_clients,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    summary["status"],
                    summary["status_detail"],
                    active_modem.get("name"),
                    active_modem.get("device_path"),
                    int(bool(expose.get("enabled"))),
                    expose.get("bind_address"),
                    expose.get("port"),
                    int(expose.get("active_clients") or 0),
                    summary.get("last_error"),
                    updated_at,
                ),
            )

    def _delete_runtime_state(self, modem_id: int) -> None:
        with get_connection() as connection:
            connection.execute("DELETE FROM traffic_runtime_interfaces WHERE modem_id = ?", (modem_id,))

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    def _kiss_unescape(self, payload: bytes) -> bytes:
        return _TrafficModemRuntime._kiss_unescape(self, payload)

    def _decode_ax25_address(self, chunk: bytes) -> tuple[str, bool, bool] | None:
        return _TrafficModemRuntime._decode_ax25_address(self, chunk)

    def _decode_ax25_to_tnc2(self, payload: bytes) -> str | None:
        return _TrafficModemRuntime._decode_ax25_to_tnc2(self, payload)
