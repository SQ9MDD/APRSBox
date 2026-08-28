import asyncio
import contextlib
import os
import pty
import select
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.db import execute, fetch_one, init_db
from app.services.outbound import build_tnc2_kiss_frame
from app.services.content import get_section_row, safe_create_section_row
from app.services.map_service import get_map_station_payload
from app.services.traffic import (
    TrafficMonitorService,
    _TrafficModemRuntime,
    _kiss_tcp_rx_silence_reconnect_seconds,
)


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def pseudo_serial_device() -> tuple[int, str]:
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    try:
        yield master_fd, slave_path
    finally:
        os.close(master_fd)
        os.close(slave_fd)


def read_master_chunk(master_fd: int, *, timeout: float = 1.0) -> bytes:
    readable, _, _ = select.select([master_fd], [], [], timeout)
    if not readable:
        return b""
    return os.read(master_fd, 1024)


def insert_modem(
    *,
    name: str = "Proxy TNC",
    modem_type: str = "TCP",
    device_path: str,
    baud_rate: int | None = None,
    expose_port_enabled: int = 0,
    expose_allow_tx: int = 1,
    expose_bind_address: str = "127.0.0.1",
    expose_port: int = 8002,
    expose_whitelist: str = "",
) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, baud_rate, enabled,
            expose_port_enabled, expose_allow_tx, expose_bind_address, expose_port, expose_whitelist,
            notes, created_at, updated_at
        )
        VALUES (?, ?, '2m', ?, ?, 1, ?, ?, ?, ?, ?, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (
            name,
            modem_type,
            device_path,
            baud_rate,
            expose_port_enabled,
            expose_allow_tx,
            expose_bind_address,
            expose_port,
            expose_whitelist,
        ),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


async def wait_until(predicate, *, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Condition was not met before timeout.")


class NativeTcpRxSilenceTests(unittest.IsolatedAsyncioTestCase):
    def test_timeout_setting_applies_only_to_native_kiss_tcp(self) -> None:
        self.assertEqual(
            _kiss_tcp_rx_silence_reconnect_seconds(
                {"modem_type": "TCP", "serial_rx_silence_reconnect_seconds": 30}
            ),
            30,
        )
        self.assertEqual(
            _kiss_tcp_rx_silence_reconnect_seconds(
                {"modem_type": "TCP", "serial_rx_silence_reconnect_seconds": 0}
            ),
            0,
        )
        self.assertEqual(
            _kiss_tcp_rx_silence_reconnect_seconds(
                {"modem_type": "SERIALL", "serial_rx_silence_reconnect_seconds": 30}
            ),
            0,
        )

    async def test_native_tcp_silence_closes_socket_for_existing_reconnect_loop(self) -> None:
        class SilentReader:
            async def read(self, _max_bytes: int) -> bytes:
                await asyncio.Event().wait()
                return b""

        class RecordingWriter:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

            async def wait_closed(self) -> None:
                return None

        modem = {
            "id": 1,
            "name": "Native TCP",
            "modem_type": "TCP",
            "serial_rx_silence_reconnect_seconds": 30,
        }
        runtime = _TrafficModemRuntime(reconnect_delay=0.1)
        writer = RecordingWriter()
        runtime._load_active_modem = lambda: modem  # type: ignore[method-assign]

        with (
            patch("app.services.traffic.asyncio.open_connection", new=AsyncMock(return_value=(SilentReader(), writer))),
            patch("app.services.traffic._kiss_tcp_rx_silence_reconnect_seconds", return_value=0.05),
            patch.object(runtime, "_sync_proxy_server", new=AsyncMock(return_value=None)),
            patch.object(runtime, "_stop_proxy_server", new=AsyncMock()),
            patch.object(runtime, "_set_state"),
            patch("app.services.traffic.log_event") as log_mock,
        ):
            await asyncio.wait_for(
                runtime._run_kiss_tcp_endpoint(
                    modem=modem,
                    host="127.0.0.1",
                    port=8001,
                    connect_label="native test TNC",
                ),
                timeout=1.0,
            )

        self.assertTrue(writer.closed)
        self.assertTrue(
            any("TCP RX silence timeout" in str(call.args[2]) for call in log_mock.call_args_list)
        )

    async def test_any_received_tcp_bytes_reset_silence_timeout(self) -> None:
        class InvalidBytesReader:
            def __init__(self) -> None:
                self.read_count = 0

            async def read(self, _max_bytes: int) -> bytes:
                self.read_count += 1
                if self.read_count <= 3:
                    await asyncio.sleep(0.03)
                    return b"\x01"
                return b""

        modem = {"id": 1, "name": "Native TCP", "modem_type": "TCP"}
        runtime = _TrafficModemRuntime(reconnect_delay=0.1)
        runtime._load_active_modem = lambda: modem  # type: ignore[method-assign]

        with (
            patch.object(runtime, "_set_state"),
            patch.object(runtime, "_sleep", new=AsyncMock()),
            patch("app.services.traffic.log_event") as log_mock,
        ):
            await runtime._consume_connection(
                InvalidBytesReader(),  # type: ignore[arg-type]
                modem,
                "127.0.0.1",
                8001,
                rx_silence_reconnect_seconds=0.05,
            )

        self.assertFalse(
            any("TCP RX silence timeout" in str(call.args[2]) for call in log_mock.call_args_list)
        )


class TrafficProxyValidationTests(unittest.TestCase):
    def test_modem_form_normalizes_expose_settings(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "LAN Proxy",
                    "band": "2m",
                    "modem_type": "TCP",
                    "device_path": "127.0.0.1:9001",
                    "baud_rate": None,
                    "enabled": "1",
                    "expose_port_enabled": "1",
                    "expose_allow_tx": "1",
                    "expose_bind_address": "0.0.0.0",
                    "expose_port": "8002",
                    "expose_whitelist": "192.168.1.10, 192.168.1.0/24",
                    "notes": "",
                },
            )
            self.assertTrue(success, error)

            row = get_section_row("modems", 1)
            assert row is not None
            self.assertEqual(int(row["expose_port_enabled"]), 1)
            self.assertEqual(int(row["expose_allow_tx"]), 1)
            self.assertEqual(row["expose_bind_address"], "0.0.0.0")
            self.assertEqual(int(row["expose_port"]), 8002)
            self.assertEqual(row["expose_whitelist"], "192.168.1.10\n192.168.1.0/24")

    def test_modem_form_rejects_invalid_expose_settings(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "Invalid LAN Proxy",
                    "band": "2m",
                    "modem_type": "TCP",
                    "device_path": "127.0.0.1:9001",
                    "baud_rate": None,
                    "enabled": "1",
                    "expose_port_enabled": "1",
                    "expose_bind_address": "invalid-host",
                    "expose_port": "8002",
                    "expose_whitelist": "192.168.1.10",
                    "notes": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Bind address must be a valid IPv4 address.")

            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "Invalid Whitelist",
                    "band": "2m",
                    "modem_type": "TCP",
                    "device_path": "127.0.0.1:9001",
                    "baud_rate": None,
                    "enabled": "1",
                    "expose_port_enabled": "1",
                    "expose_bind_address": "127.0.0.1",
                    "expose_port": "8002",
                    "expose_whitelist": "bad-entry",
                    "notes": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Whitelist entries must be valid IPv4 addresses or CIDR ranges.")

            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "Invalid Serial Baud",
                    "band": "2m",
                    "modem_type": "SERIALL",
                    "device_path": "/dev/ttyUSB0",
                    "baud_rate": 12345,
                    "enabled": "1",
                    "expose_port_enabled": "1",
                    "expose_bind_address": "127.0.0.1",
                    "expose_port": "8002",
                    "expose_whitelist": "",
                    "notes": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Baud rate must be one of: 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200.")

            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "Invalid RX Timeout",
                    "band": "2m",
                    "modem_type": "SERIALL",
                    "device_path": "/dev/ttyUSB0",
                    "baud_rate": 9600,
                    "serial_rx_silence_reconnect_seconds": "95",
                    "enabled": "1",
                    "expose_port_enabled": "1",
                    "expose_bind_address": "127.0.0.1",
                    "expose_port": "8002",
                    "expose_whitelist": "",
                    "notes": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "RX silence reconnect timeout must be one of: 0, 30, 60, 90, 120, 150, ..., 600 seconds.")

    def test_modem_form_accepts_tx_min_gap_in_configured_range(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "Gap OK",
                    "band": "2m",
                    "modem_type": "TCP",
                    "device_path": "127.0.0.1:9001",
                    "enabled": "1",
                    "tx_min_gap_seconds": "0.72",
                    "expose_port_enabled": "0",
                    "expose_bind_address": "127.0.0.1",
                    "expose_port": "8002",
                    "expose_whitelist": "",
                },
            )
            self.assertTrue(success, error)
            row = get_section_row("modems", 1)
            assert row is not None
            self.assertAlmostEqual(float(row["tx_min_gap_seconds"]), 0.72, places=2)

    def test_modem_form_rejects_tx_min_gap_out_of_range(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "Gap Too Low",
                    "band": "2m",
                    "modem_type": "TCP",
                    "device_path": "127.0.0.1:9001",
                    "enabled": "1",
                    "tx_min_gap_seconds": "0.19",
                    "expose_port_enabled": "0",
                    "expose_bind_address": "127.0.0.1",
                    "expose_port": "8002",
                    "expose_whitelist": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "TX minimum gap must be between 0.2 and 1.2 seconds.")


class TrafficProxyRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_proxy_relays_tnc_traffic_and_client_writes(self) -> None:
        with temporary_database():
            tnc_port = free_tcp_port()
            expose_port = free_tcp_port()
            insert_modem(
                device_path=f"127.0.0.1:{tnc_port}",
                expose_port_enabled=1,
                expose_bind_address="127.0.0.1",
                expose_port=expose_port,
            )

            tnc_reader_queue: asyncio.Queue[bytes] = asyncio.Queue()
            connection_ready: asyncio.Future[asyncio.StreamWriter] = asyncio.get_running_loop().create_future()

            async def handle_tnc_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                if not connection_ready.done():
                    connection_ready.set_result(writer)
                try:
                    while True:
                        chunk = await reader.read(1024)
                        if not chunk:
                            break
                        await tnc_reader_queue.put(chunk)
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass

            tnc_server = await asyncio.start_server(handle_tnc_client, host="127.0.0.1", port=tnc_port)
            service = TrafficMonitorService(reconnect_delay=0.1)
            client_writer_1: asyncio.StreamWriter | None = None
            client_writer_2: asyncio.StreamWriter | None = None
            tnc_writer: asyncio.StreamWriter | None = None
            try:
                await service.start()
                await wait_until(
                    lambda: service.snapshot()["status"] == "connected" and service.snapshot()["expose"]["enabled"],
                    timeout=3.0,
                )
                tnc_writer = await asyncio.wait_for(connection_ready, timeout=1.0)

                client_reader_1, client_writer_1 = await asyncio.open_connection("127.0.0.1", expose_port)
                client_reader_2, client_writer_2 = await asyncio.open_connection("127.0.0.1", expose_port)
                await wait_until(lambda: service.snapshot()["expose"]["active_clients"] == 2)

                tnc_payload = b"\xC0\x00ABC\xC0"
                tnc_writer.write(tnc_payload)
                await tnc_writer.drain()
                self.assertEqual(await asyncio.wait_for(client_reader_1.readexactly(len(tnc_payload)), timeout=1.0), tnc_payload)
                self.assertEqual(await asyncio.wait_for(client_reader_2.readexactly(len(tnc_payload)), timeout=1.0), tnc_payload)

                client_payload = b"\xC0\x00DEF\xC0"
                client_writer_1.write(client_payload)
                await client_writer_1.drain()
                self.assertEqual(await asyncio.wait_for(tnc_reader_queue.get(), timeout=1.0), client_payload)
            finally:
                if client_writer_1 is not None:
                    client_writer_1.close()
                    try:
                        await client_writer_1.wait_closed()
                    except OSError:
                        pass
                if client_writer_2 is not None:
                    client_writer_2.close()
                    try:
                        await client_writer_2.wait_closed()
                    except OSError:
                        pass
                if tnc_writer is not None:
                    tnc_writer.close()
                    try:
                        await tnc_writer.wait_closed()
                    except OSError:
                        pass
                await service.stop()
                tnc_server.close()
                await tnc_server.wait_closed()

    async def test_proxy_client_tx_is_persisted_for_rf_log_and_map(self) -> None:
        with temporary_database():
            tnc_port = free_tcp_port()
            expose_port = free_tcp_port()
            interface_id = insert_modem(
                device_path=f"127.0.0.1:{tnc_port}",
                expose_port_enabled=1,
                expose_bind_address="127.0.0.1",
                expose_port=expose_port,
            )

            tnc_reader_queue: asyncio.Queue[bytes] = asyncio.Queue()
            connection_ready: asyncio.Future[asyncio.StreamWriter] = asyncio.get_running_loop().create_future()

            async def handle_tnc_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                if not connection_ready.done():
                    connection_ready.set_result(writer)
                try:
                    while True:
                        chunk = await reader.read(1024)
                        if not chunk:
                            break
                        await tnc_reader_queue.put(chunk)
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass

            tnc_server = await asyncio.start_server(handle_tnc_client, host="127.0.0.1", port=tnc_port)
            service = TrafficMonitorService(reconnect_delay=0.1)
            client_writer: asyncio.StreamWriter | None = None
            tnc_writer: asyncio.StreamWriter | None = None
            try:
                await service.start()
                await wait_until(
                    lambda: service.snapshot()["status"] == "connected" and service.snapshot()["expose"]["enabled"],
                    timeout=3.0,
                )
                tnc_writer = await asyncio.wait_for(connection_ready, timeout=1.0)
                _client_reader, client_writer = await asyncio.open_connection("127.0.0.1", expose_port)

                tnc2_line = "SP8XYZ-9>APRS:=5218.37N/02104.87E-Proxy uplink"
                client_payload = build_tnc2_kiss_frame(tnc2_line)
                client_writer.write(client_payload)
                await client_writer.drain()
                self.assertEqual(await asyncio.wait_for(tnc_reader_queue.get(), timeout=1.0), client_payload)

                await wait_until(
                    lambda: fetch_one(
                        """
                        SELECT id
                        FROM traffic_frames
                        WHERE interface_id = ? AND direction = 'tx' AND format = 'TNC2-TX'
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (interface_id,),
                    )
                    is not None,
                    timeout=2.0,
                )

                tx_row = fetch_one(
                    """
                    SELECT interface_id, line, command
                    FROM traffic_frames
                    WHERE interface_id = ? AND direction = 'tx' AND format = 'TNC2-TX'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (interface_id,),
                )
                assert tx_row is not None
                self.assertEqual(int(tx_row["interface_id"]), interface_id)
                self.assertIn("SP8XYZ-9", str(tx_row["line"]))
                self.assertEqual(str(tx_row["command"] or "").upper(), "TX-PROXY")

                stations = get_map_station_payload()["stations"]
                station = next((item for item in stations if item["display_callsign"] == "SP8XYZ-9"), None)
                self.assertIsNotNone(station)
                assert station is not None
                self.assertEqual(station["origin"], "local_tx")
            finally:
                if client_writer is not None:
                    client_writer.close()
                    try:
                        await client_writer.wait_closed()
                    except OSError:
                        pass
                if tnc_writer is not None:
                    tnc_writer.close()
                    try:
                        await tnc_writer.wait_closed()
                    except OSError:
                        pass
                await service.stop()
                tnc_server.close()
                await tnc_server.wait_closed()

    async def test_proxy_rejects_client_tx_when_remote_tx_is_disabled(self) -> None:
        with temporary_database():
            tnc_port = free_tcp_port()
            expose_port = free_tcp_port()
            interface_id = insert_modem(
                device_path=f"127.0.0.1:{tnc_port}",
                expose_port_enabled=1,
                expose_allow_tx=0,
                expose_bind_address="127.0.0.1",
                expose_port=expose_port,
            )

            tnc_reader_queue: asyncio.Queue[bytes] = asyncio.Queue()
            connection_ready: asyncio.Future[asyncio.StreamWriter] = asyncio.get_running_loop().create_future()

            async def handle_tnc_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                if not connection_ready.done():
                    connection_ready.set_result(writer)
                try:
                    while True:
                        chunk = await reader.read(1024)
                        if not chunk:
                            break
                        await tnc_reader_queue.put(chunk)
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass

            tnc_server = await asyncio.start_server(handle_tnc_client, host="127.0.0.1", port=tnc_port)
            service = TrafficMonitorService(reconnect_delay=0.1)
            client_reader: asyncio.StreamReader | None = None
            client_writer: asyncio.StreamWriter | None = None
            tnc_writer: asyncio.StreamWriter | None = None
            try:
                await service.start()
                await wait_until(
                    lambda: service.snapshot()["status"] == "connected" and service.snapshot()["expose"]["enabled"],
                    timeout=3.0,
                )
                tnc_writer = await asyncio.wait_for(connection_ready, timeout=1.0)
                client_reader, client_writer = await asyncio.open_connection("127.0.0.1", expose_port)

                client_payload = build_tnc2_kiss_frame("SP8XYZ-9>APRS:>Should be blocked")
                client_writer.write(client_payload)
                await client_writer.drain()

                with self.assertRaises(TimeoutError):
                    await asyncio.wait_for(tnc_reader_queue.get(), timeout=0.5)

                tx_row = fetch_one(
                    """
                    SELECT id
                    FROM traffic_frames
                    WHERE interface_id = ? AND direction = 'tx' AND command = 'TX-PROXY'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (interface_id,),
                )
                self.assertIsNone(tx_row)

                tnc_payload = b"\xC0\x00ABC\xC0"
                tnc_writer.write(tnc_payload)
                await tnc_writer.drain()
                assert client_reader is not None
                self.assertEqual(await asyncio.wait_for(client_reader.readexactly(len(tnc_payload)), timeout=1.0), tnc_payload)
            finally:
                if client_writer is not None:
                    client_writer.close()
                    try:
                        await client_writer.wait_closed()
                    except OSError:
                        pass
                if tnc_writer is not None:
                    tnc_writer.close()
                    try:
                        await tnc_writer.wait_closed()
                    except OSError:
                        pass
                await service.stop()
                tnc_server.close()
                await tnc_server.wait_closed()

    async def test_proxy_enforces_whitelist_and_connection_limit(self) -> None:
        with temporary_database():
            tnc_port = free_tcp_port()
            expose_port = free_tcp_port()
            insert_modem(
                device_path=f"127.0.0.1:{tnc_port}",
                expose_port_enabled=1,
                expose_bind_address="127.0.0.1",
                expose_port=expose_port,
                expose_whitelist="127.0.0.1/32",
            )

            async def handle_tnc_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await reader.read()
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass

            tnc_server = await asyncio.start_server(handle_tnc_client, host="127.0.0.1", port=tnc_port)
            service = TrafficMonitorService(reconnect_delay=0.1)
            writers: list[asyncio.StreamWriter] = []
            try:
                await service.start()
                await wait_until(
                    lambda: service.snapshot()["status"] == "connected" and service.snapshot()["expose"]["enabled"],
                    timeout=3.0,
                )

                for _ in range(3):
                    _reader, writer = await asyncio.open_connection("127.0.0.1", expose_port)
                    writers.append(writer)

                await wait_until(lambda: service.snapshot()["expose"]["active_clients"] == 3)

                extra_reader, extra_writer = await asyncio.open_connection("127.0.0.1", expose_port)
                try:
                    self.assertEqual(await asyncio.wait_for(extra_reader.read(1), timeout=1.0), b"")
                finally:
                    extra_writer.close()
                    try:
                        await extra_writer.wait_closed()
                    except OSError:
                        pass
            finally:
                for writer in writers:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
                await service.stop()
                tnc_server.close()
                await tnc_server.wait_closed()

    async def test_proxy_accepts_clients_when_backed_by_serial_tnc(self) -> None:
        with temporary_database():
            expose_port = free_tcp_port()
            with pseudo_serial_device() as (master_fd, slave_path):
                insert_modem(
                    modem_type="SERIALL",
                    name="Serial Proxy TNC",
                    device_path=slave_path,
                    baud_rate=9600,
                    expose_port_enabled=1,
                    expose_bind_address="127.0.0.1",
                    expose_port=expose_port,
                )

                service = TrafficMonitorService(reconnect_delay=0.1)
                client_writer: asyncio.StreamWriter | None = None
                try:
                    await service.start()
                    await wait_until(
                        lambda: service.snapshot()["status"] == "connected" and service.snapshot()["expose"]["enabled"],
                        timeout=3.0,
                    )

                    client_reader, client_writer = await asyncio.open_connection("127.0.0.1", expose_port)
                    await wait_until(lambda: service.snapshot()["expose"]["active_clients"] == 1, timeout=2.0)

                    serial_payload = build_tnc2_kiss_frame("SQ9MDD-4>APRS:>Serial proxy test")
                    os.write(master_fd, serial_payload)
                    self.assertEqual(
                        await asyncio.wait_for(client_reader.readexactly(len(serial_payload)), timeout=1.0),
                        serial_payload,
                    )

                    client_payload = b"\xC0\x00SERIAL-UPLINK\xC0"
                    client_writer.write(client_payload)
                    await client_writer.drain()
                    self.assertEqual(await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0), client_payload)
                finally:
                    if client_writer is not None:
                        client_writer.close()
                        try:
                            await client_writer.wait_closed()
                        except OSError:
                            pass
                    await service.stop()

    async def test_proxy_rejects_client_outside_whitelist(self) -> None:
        with temporary_database():
            tnc_port = free_tcp_port()
            expose_port = free_tcp_port()
            insert_modem(
                device_path=f"127.0.0.1:{tnc_port}",
                expose_port_enabled=1,
                expose_bind_address="127.0.0.1",
                expose_port=expose_port,
                expose_whitelist="192.168.50.0/24",
            )

            async def handle_tnc_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await reader.read()
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass

            tnc_server = await asyncio.start_server(handle_tnc_client, host="127.0.0.1", port=tnc_port)
            service = TrafficMonitorService(reconnect_delay=0.1)
            try:
                await service.start()
                await wait_until(
                    lambda: service.snapshot()["status"] == "connected" and service.snapshot()["expose"]["enabled"],
                    timeout=3.0,
                )

                reader, writer = await asyncio.open_connection("127.0.0.1", expose_port)
                try:
                    self.assertEqual(await asyncio.wait_for(reader.read(1), timeout=1.0), b"")
                    await wait_until(lambda: service.snapshot()["expose"]["active_clients"] == 0)
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
            finally:
                await service.stop()
                tnc_server.close()
                await tnc_server.wait_closed()


if __name__ == "__main__":
    unittest.main()
