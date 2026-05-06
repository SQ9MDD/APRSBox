from __future__ import annotations

import asyncio
from threading import Lock

from app.db import log_event
from app.services.serial_tnc import close_serial_device, open_serial_device, read_serial_chunk, write_serial_data

SERIAL_BROKER_HOST = "127.0.0.1"
SERIAL_BROKER_PREVIEW_BYTES = 32


def _chunk_preview(chunk: bytes, *, max_bytes: int = SERIAL_BROKER_PREVIEW_BYTES) -> str:
    if not chunk:
        return "<empty>"
    if len(chunk) <= max_bytes:
        return chunk.hex(" ").upper()
    head_len = max_bytes // 2
    tail_len = max_bytes - head_len
    head = chunk[:head_len].hex(" ").upper()
    tail = chunk[-tail_len:].hex(" ").upper()
    return f"{head} ... {tail}"


class SerialKissTcpBroker:
    def __init__(
        self,
        *,
        modem_id: int,
        tnc_name: str,
        device_path: str,
        baud_rate: int,
        rx_silence_reconnect_seconds: int = 150,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._modem_id = int(modem_id)
        self._tnc_name = str(tnc_name or "").strip() or f"modem-{modem_id}"
        self._device_path = str(device_path or "").strip()
        self._baud_rate = int(baud_rate)
        self._rx_silence_reconnect_seconds = max(0, int(rx_silence_reconnect_seconds))
        self._reconnect_delay = max(0.1, float(reconnect_delay))

        self._lock = Lock()
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._client_ready = asyncio.Event()
        self._serial_write_lock = asyncio.Lock()

        self._listener: asyncio.AbstractServer | None = None
        self._listen_port: int | None = None
        self._client_reader: asyncio.StreamReader | None = None
        self._client_writer: asyncio.StreamWriter | None = None
        self._serial_fd: int | None = None
        self._serial_to_tcp_bytes = 0
        self._tcp_to_serial_bytes = 0

    @property
    def host(self) -> str:
        return SERIAL_BROKER_HOST

    @property
    def port(self) -> int:
        if self._listen_port is None:
            raise RuntimeError("Serial broker is not listening.")
        return self._listen_port

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        await self._start_listener()
        self._task = asyncio.create_task(
            self._run(),
            name=f"aprsbox-serial-broker-{self._modem_id}",
        )
        log_event(
            "INFO",
            "serial_broker",
            (
                f"Broker start for {self._tnc_name} (id={self._modem_id}): "
                f"device={self._device_path} baud={self._baud_rate} "
                f"tcp={SERIAL_BROKER_HOST}:{self.port}"
            ),
        )

    async def stop(self) -> None:
        self._stop_event.set()
        await self._close_listener()
        await self._close_client(log_disconnect=False)
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        await self._close_serial_fd(reason="broker stop")
        log_event(
            "INFO",
            "serial_broker",
            (
                f"Broker stop for {self._tnc_name} (id={self._modem_id}): "
                f"serial->tcp={self._serial_to_tcp_bytes}B tcp->serial={self._tcp_to_serial_bytes}B"
            ),
        )

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            if self._serial_fd is None:
                try:
                    serial_fd = await asyncio.to_thread(open_serial_device, self._device_path, self._baud_rate)
                except (OSError, ValueError) as exc:
                    log_event(
                        "WARNING",
                        "serial_broker",
                        (
                            f"Failed to open serial for {self._tnc_name} (id={self._modem_id}) "
                            f"device={self._device_path} baud={self._baud_rate}: {exc}"
                        ),
                    )
                    await self._sleep(self._reconnect_delay)
                    continue
                self._serial_fd = serial_fd
                log_event(
                    "INFO",
                    "serial_broker",
                    (
                        f"Serial open for {self._tnc_name} (id={self._modem_id}): "
                        f"device={self._device_path} fd={serial_fd}"
                    ),
                )

            if self._client_writer is None or self._client_reader is None:
                await self._wait_for_client()
                continue

            serial_failed = await self._pump_client_session()
            await self._close_client(log_disconnect=True)
            if serial_failed:
                await self._close_serial_fd(reason="serial read/write failure")
                await self._sleep(self._reconnect_delay)

    async def _start_listener(self) -> None:
        self._listener = await asyncio.start_server(self._handle_client, host=SERIAL_BROKER_HOST, port=0)
        sockets = self._listener.sockets or []
        if not sockets:
            raise RuntimeError("Serial broker listener has no active socket.")
        self._listen_port = int(sockets[0].getsockname()[1])

    async def _close_listener(self) -> None:
        listener = self._listener
        self._listener = None
        self._listen_port = None
        if listener is not None:
            listener.close()
            await listener.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        client_host = str(peer[0]) if isinstance(peer, tuple) and peer else "unknown"
        client_port = int(peer[1]) if isinstance(peer, tuple) and len(peer) > 1 else 0
        client_label = f"{client_host}:{client_port}" if client_port > 0 else client_host

        if self._client_writer is not None:
            log_event(
                "WARNING",
                "serial_broker",
                (
                    f"Second client rejected for {self._tnc_name} (id={self._modem_id}) "
                    f"on {SERIAL_BROKER_HOST}:{self.port}: client={client_label}"
                ),
            )
            await self._close_writer(writer)
            return

        self._client_reader = reader
        self._client_writer = writer
        self._client_ready.set()
        log_event(
            "INFO",
            "serial_broker",
            (
                f"Broker client connected for {self._tnc_name} (id={self._modem_id}): "
                f"client={client_label}"
            ),
        )

    async def _wait_for_client(self) -> None:
        self._client_ready.clear()
        try:
            await asyncio.wait_for(self._client_ready.wait(), timeout=1.0)
        except TimeoutError:
            return

    async def _pump_client_session(self) -> bool:
        serial_fd = self._serial_fd
        reader = self._client_reader
        writer = self._client_writer
        if serial_fd is None or reader is None or writer is None:
            return False

        serial_to_tcp = asyncio.create_task(
            self._pump_serial_to_tcp(serial_fd=serial_fd, writer=writer),
            name=f"serial-broker-rx-{self._modem_id}",
        )
        tcp_to_serial = asyncio.create_task(
            self._pump_tcp_to_serial(serial_fd=serial_fd, reader=reader),
            name=f"serial-broker-tx-{self._modem_id}",
        )

        done, pending = await asyncio.wait(
            {serial_to_tcp, tcp_to_serial},
            return_when=asyncio.FIRST_COMPLETED,
        )
        serial_failed = any(bool(task.result()) for task in done if not task.cancelled())
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass
        return serial_failed

    async def _pump_serial_to_tcp(self, *, serial_fd: int, writer: asyncio.StreamWriter) -> bool:
        loop = asyncio.get_running_loop()
        last_rx_at = loop.time()
        while not self._stop_event.is_set():
            try:
                chunk = await asyncio.to_thread(read_serial_chunk, serial_fd, max_bytes=1024, timeout=1.0)
            except OSError as exc:
                log_event(
                    "WARNING",
                    "serial_broker",
                    (
                        f"Serial read failed for {self._tnc_name} (id={self._modem_id}) "
                        f"device={self._device_path}: {exc}"
                    ),
                )
                return True
            if not chunk:
                if self._rx_silence_reconnect_seconds > 0:
                    silence_seconds = loop.time() - last_rx_at
                    if silence_seconds >= self._rx_silence_reconnect_seconds:
                        log_event(
                            "WARNING",
                            "serial_broker",
                            (
                                f"Serial silence timeout for {self._tnc_name} (id={self._modem_id}) "
                                f"device={self._device_path}: no RX for {self._rx_silence_reconnect_seconds}s"
                            ),
                        )
                        return True
                continue
            last_rx_at = loop.time()
            try:
                writer.write(chunk)
                await writer.drain()
            except OSError as exc:
                log_event(
                    "WARNING",
                    "serial_broker",
                    f"Broker TCP write failed for {self._tnc_name} (id={self._modem_id}): {exc}",
                )
                return False
            with self._lock:
                self._serial_to_tcp_bytes += len(chunk)
            self._log_debug_chunk(direction="serial->tcp", chunk=chunk)
        return False

    async def _pump_tcp_to_serial(self, *, serial_fd: int, reader: asyncio.StreamReader) -> bool:
        while not self._stop_event.is_set():
            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            except TimeoutError:
                continue
            except OSError as exc:
                log_event(
                    "WARNING",
                    "serial_broker",
                    f"Broker TCP read failed for {self._tnc_name} (id={self._modem_id}): {exc}",
                )
                return False
            if not chunk:
                return False
            try:
                await self._write_to_serial(serial_fd=serial_fd, chunk=chunk)
            except (OSError, TimeoutError) as exc:
                log_event(
                    "WARNING",
                    "serial_broker",
                    (
                        f"Serial write failed for {self._tnc_name} (id={self._modem_id}) "
                        f"device={self._device_path}: {exc}"
                    ),
                )
                return True
            with self._lock:
                self._tcp_to_serial_bytes += len(chunk)
            self._log_debug_chunk(direction="tcp->serial", chunk=chunk)
        return False

    async def _write_to_serial(self, *, serial_fd: int, chunk: bytes) -> None:
        async with self._serial_write_lock:
            await asyncio.to_thread(write_serial_data, serial_fd, chunk, drain=True)

    async def _close_client(self, *, log_disconnect: bool) -> None:
        writer = self._client_writer
        self._client_reader = None
        self._client_writer = None
        self._client_ready.clear()
        if writer is not None:
            await self._close_writer(writer)
            if log_disconnect:
                log_event(
                    "INFO",
                    "serial_broker",
                    f"Broker client disconnected for {self._tnc_name} (id={self._modem_id})",
                )

    async def _close_serial_fd(self, *, reason: str) -> None:
        serial_fd = self._serial_fd
        self._serial_fd = None
        if serial_fd is None:
            return
        await asyncio.to_thread(close_serial_device, serial_fd)
        log_event(
            "INFO",
            "serial_broker",
            (
                f"Serial close for {self._tnc_name} (id={self._modem_id}): "
                f"device={self._device_path} fd={serial_fd} reason={reason}"
            ),
        )

    async def _sleep(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            pass

    def _log_debug_chunk(self, *, direction: str, chunk: bytes) -> None:
        command_text = "n/a"
        if len(chunk) >= 2 and chunk[0] == 0xC0:
            command_text = f"0x{chunk[1]:02X}"
        log_event(
            "DEBUG",
            "serial_broker",
            (
                f"Broker {direction} for {self._tnc_name} (id={self._modem_id}): "
                f"len={len(chunk)} cmd={command_text} preview={_chunk_preview(chunk)}"
            ),
        )

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
