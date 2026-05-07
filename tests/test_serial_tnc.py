import asyncio
import contextlib
import os
import pty
import select
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.db import execute, fetch_one, init_db
from app.services import serial_broker as serial_broker_module
from app.services.content import get_section_row, safe_create_section_row, update_station_settings
from app.services.outbound import build_beacon_tnc2, build_tnc2_kiss_frame, claim_next_outbound_job, get_outbound_job
from app.services.outbound_runtime import OutboundService
from app.services.serial_tnc import write_serial_data as base_write_serial_data
from app.services.traffic import TrafficMonitorService, _TrafficModemRuntime


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


@contextlib.contextmanager
def pseudo_serial_device() -> tuple[int, str]:
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    try:
        yield master_fd, slave_path
    finally:
        os.close(master_fd)
        os.close(slave_fd)


def insert_serial_modem(
    *,
    device_path: str,
    baud_rate: int = 9600,
    enabled: int = 1,
    name: str = "Serial TNC",
    band: str = "2m",
) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, baud_rate, enabled,
            expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
            notes, created_at, updated_at
        )
        VALUES (?, 'SERIALL', ?, ?, ?, ?, 0, '127.0.0.1', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, band, device_path, baud_rate, enabled),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ? ORDER BY id DESC LIMIT 1", (name,))
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


def read_master_chunk(master_fd: int, *, timeout: float = 1.0) -> bytes:
    readable, _, _ = select.select([master_fd], [], [], timeout)
    if not readable:
        return b""
    return os.read(master_fd, 1024)


class SerialTncValidationTests(unittest.TestCase):
    def test_modem_form_accepts_serial_device_and_baud_rate(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "USB TNC",
                    "band": "2m",
                    "modem_type": "SERIALL",
                    "device_path": "/dev/ttyACM0",
                    "baud_rate": "9600",
                    "serial_rx_silence_reconnect_seconds": "0",
                    "enabled": "1",
                    "tx_blocked": "1",
                    "expose_port_enabled": "1",
                    "expose_bind_address": "0.0.0.0",
                    "expose_port": "8002",
                    "expose_whitelist": "",
                    "notes": "",
                },
            )
            self.assertTrue(success, error)
            row = get_section_row("modems", 1)
            assert row is not None
            self.assertEqual(row["device_path"], "/dev/ttyACM0")
            self.assertEqual(int(row["baud_rate"]), 9600)
            self.assertEqual(int(row["serial_rx_silence_reconnect_seconds"]), 0)
            self.assertEqual(int(row["tx_blocked"]), 1)
            self.assertEqual(int(row["expose_port_enabled"]), 1)


class KISSFrameEncodingTests(unittest.TestCase):
    def test_build_tnc2_kiss_frame_escapes_fend_and_fesc_in_payload(self) -> None:
        with patch("app.services.outbound._parse_tnc2_line", return_value=("SRC", "DST", "", "PAYLOAD")):
            with patch(
                "app.services.outbound._encode_ax25_address",
                side_effect=[
                    bytes([0xC0, 0xDB, 0x20, 0x20, 0x20, 0x20, 0x01]),
                    bytes([0x82, 0xA0, 0xA4, 0xA6, 0x40, 0x40, 0x61]),
                ],
            ):
                frame = build_tnc2_kiss_frame("SRC>DST:PAYLOAD")
        payload = frame[1:-1]
        self.assertEqual(frame[0], 0xC0)
        self.assertEqual(frame[-1], 0xC0)
        self.assertIn(bytes([0xDB, 0xDC]), payload)
        self.assertIn(bytes([0xDB, 0xDD]), payload)
        self.assertNotIn(bytes([0xC0]), payload)

    def test_build_tnc2_kiss_frame_rejects_invalid_ax25_callsign(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid AX.25 callsign"):
            build_tnc2_kiss_frame("SQ9XYZ-9>AP?RS:>Test")

    def test_build_tnc2_kiss_frame_keeps_control_bytes_in_info(self) -> None:
        frame = build_tnc2_kiss_frame("SQ9XYZ-9>APRS:'0SWl \x1c[/>144.800MHz op. Rysiek&")
        self.assertTrue(frame.startswith(bytes([0xC0, 0x00])))
        self.assertEqual(frame[-1], 0xC0)

    def test_build_tnc2_kiss_frame_uses_data_command_and_never_uses_kiss_return(self) -> None:
        frame = build_tnc2_kiss_frame("SQ9MDD-7>APRS,WIDE1-1:>test")
        self.assertEqual(frame[0], 0xC0)
        self.assertEqual(frame[-1], 0xC0)
        self.assertEqual(frame[1], 0x00)
        self.assertNotEqual(frame[1], 0xFF)


class SerialTxLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_serial_runtime_rejects_kiss_return_command_byte(self) -> None:
        class _Writer:
            def __init__(self) -> None:
                self.writes: list[bytes] = []

            def write(self, chunk: bytes) -> None:
                self.writes.append(bytes(chunk))

            async def drain(self) -> None:
                return None

        runtime = _TrafficModemRuntime(modem_id=1)
        with runtime._lock:
            runtime._active_modem = {"id": 1, "name": "Serial TNC"}
        writer = _Writer()
        runtime._tnc_writer = writer

        result = await runtime.send_outbound_frame(interface_id=1, frame=b"\xC0\xFFA\xC0")
        self.assertFalse(result)
        self.assertEqual(writer.writes, [])

    async def test_serial_runtime_serializes_parallel_tx_writes(self) -> None:
        class _SlowWriter:
            def __init__(self) -> None:
                self.writes: list[bytes] = []
                self.in_flight = 0
                self.max_in_flight = 0

            def write(self, chunk: bytes) -> None:
                self.writes.append(bytes(chunk))
                self.in_flight += 1
                self.max_in_flight = max(self.max_in_flight, self.in_flight)

            async def drain(self) -> None:
                await asyncio.sleep(0.03)
                self.in_flight -= 1

        runtime = _TrafficModemRuntime(modem_id=1)
        writer = _SlowWriter()
        with runtime._lock:
            runtime._active_modem = {"id": 1, "name": "Serial TNC"}
        runtime._tnc_writer = writer

        first = asyncio.create_task(runtime.send_outbound_frame(interface_id=1, frame=b"\xC0\x00A\xC0"))
        second = asyncio.create_task(runtime.send_outbound_frame(interface_id=1, frame=b"\xC0\x00B\xC0"))
        results = await asyncio.gather(first, second)

        self.assertEqual(results, [True, True])
        self.assertEqual(len(writer.writes), 2)
        self.assertEqual(writer.max_in_flight, 1)


class SerialTncRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_serial_runtime_routes_through_internal_localhost_broker(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (_master_fd, slave_path):
                interface_id = insert_serial_modem(device_path=slave_path, baud_rate=9600)
                service = TrafficMonitorService(reconnect_delay=0.1)
                try:
                    await service.start()
                    await wait_until(lambda: service.snapshot()["status"] == "connected", timeout=4.0)

                    runtime = service._runtime_for_interface(interface_id)
                    self.assertIsNotNone(runtime)
                    assert runtime is not None
                    self.assertIsNotNone(runtime._serial_broker)
                    self.assertIsNotNone(runtime._tnc_writer)
                    assert runtime._serial_broker is not None
                    assert runtime._tnc_writer is not None
                    peer = runtime._tnc_writer.get_extra_info("peername")
                    self.assertIsInstance(peer, tuple)
                    assert isinstance(peer, tuple)
                    self.assertEqual(str(peer[0]), "127.0.0.1")
                    self.assertEqual(int(peer[1]), runtime._serial_broker.port)
                finally:
                    await service.stop()

    async def test_two_serial_modems_get_distinct_broker_ports(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (_master_a, slave_a):
                with pseudo_serial_device() as (_master_b, slave_b):
                    modem_a = insert_serial_modem(device_path=slave_a, baud_rate=9600, name="Serial TNC A")
                    modem_b = insert_serial_modem(device_path=slave_b, baud_rate=9600, name="Serial TNC B", band="70cm")
                    service = TrafficMonitorService(reconnect_delay=0.1)
                    try:
                        await service.start()
                        await wait_until(
                            lambda: len(service.snapshot().get("interfaces") or []) == 2
                            and all(item["status"] == "connected" for item in service.snapshot()["interfaces"]),
                            timeout=4.0,
                        )
                        runtime_a = service._runtime_for_interface(modem_a)
                        runtime_b = service._runtime_for_interface(modem_b)
                        self.assertIsNotNone(runtime_a)
                        self.assertIsNotNone(runtime_b)
                        assert runtime_a is not None and runtime_b is not None
                        self.assertIsNotNone(runtime_a._serial_broker)
                        self.assertIsNotNone(runtime_b._serial_broker)
                        assert runtime_a._serial_broker is not None
                        assert runtime_b._serial_broker is not None
                        self.assertNotEqual(runtime_a._serial_broker.port, runtime_b._serial_broker.port)
                    finally:
                        await service.stop()

    async def test_service_stop_closes_serial_broker(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (_master_fd, slave_path):
                interface_id = insert_serial_modem(device_path=slave_path, baud_rate=9600)
                service = TrafficMonitorService(reconnect_delay=0.1)
                runtime: _TrafficModemRuntime | None = None
                broker = None
                try:
                    await service.start()
                    await wait_until(lambda: service.snapshot()["status"] == "connected", timeout=4.0)
                    runtime = service._runtime_for_interface(interface_id)
                    self.assertIsNotNone(runtime)
                    assert runtime is not None
                    broker = runtime._serial_broker
                    self.assertIsNotNone(broker)
                    assert broker is not None
                    self.assertIsNotNone(broker._task)
                finally:
                    await service.stop()
                self.assertIsNotNone(runtime)
                assert runtime is not None
                self.assertIsNone(runtime._serial_broker)
                self.assertIsNotNone(broker)
                assert broker is not None
                self.assertIsNone(broker._task)

    async def test_traffic_monitor_reads_kiss_frames_from_serial_tnc(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                insert_serial_modem(device_path=slave_path, baud_rate=9600)
                service = TrafficMonitorService(reconnect_delay=0.1)
                try:
                    await service.start()
                    await wait_until(lambda: service.snapshot()["status"] == "connected", timeout=3.0)

                    os.write(master_fd, build_tnc2_kiss_frame("SQ9MDD-4>APRS:>Serial runtime test"))
                    await wait_until(
                        lambda: (fetch_one("SELECT COUNT(*) AS total FROM traffic_frames WHERE format = 'TNC2'") or {"total": 0})["total"] >= 1,
                        timeout=2.0,
                    )

                    row = fetch_one("SELECT format, line FROM traffic_frames WHERE format = 'TNC2' ORDER BY id DESC LIMIT 1")
                    assert row is not None
                    self.assertEqual(row["format"], "TNC2")
                    self.assertIn("Serial runtime test", row["line"])
                finally:
                    await service.stop()

    async def test_outbound_service_writes_kiss_frames_to_serial_tnc(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                interface_id = insert_serial_modem(device_path=slave_path, baud_rate=9600)
                update_station_settings(
                    {
                        "callsign": "sq9xyz",
                        "ssid": "9",
                        "beacon_interface_id": str(interface_id),
                        "beacon_comment": "Test beacon",
                        "beacon_interval_minutes": "15",
                        "beacon_path": "WIDE2-2",
                        "status_text": "Station online",
                        "status_interval_minutes": "30",
                        "latitude": "52.2297",
                        "longitude": "21.0122",
                        "symbol_table": "/",
                        "symbol_code": ">",
                        "default_units": "metric",
                        "tx_enabled": "1",
                    }
                )
                execute(
                    """
                    INSERT INTO outbound_jobs(
                        kind, interface_id, payload_json, status, scheduled_at,
                        locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                    )
                    VALUES (
                        'beacon', ?, '{"callsign":"SQ9XYZ","ssid":"9","latitude":52.2297,"longitude":21.0122,"symbol_table":"/","symbol_code":">","beacon_comment":"Test beacon","beacon_path":"WIDE2-2","trigger":"manual"}',
                        'queued', '2026-01-01T00:00:00+00:00',
                        NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (interface_id,),
                )

                job = claim_next_outbound_job()
                assert job is not None
                traffic_monitor = TrafficMonitorService(reconnect_delay=0.1)
                try:
                    await traffic_monitor.start()
                    await wait_until(lambda: traffic_monitor.snapshot()["status"] == "connected", timeout=3.0)
                    await OutboundService(traffic_monitor=traffic_monitor)._process_job(job)

                    runtime_job = get_outbound_job(int(job["id"]))
                    assert runtime_job is not None
                    expected_line = build_beacon_tnc2(runtime_job["payload"])
                    expected_frame = build_tnc2_kiss_frame(expected_line)
                    written_frame = await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0)

                    self.assertEqual(written_frame, expected_frame)
                    row = fetch_one("SELECT status FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
                    assert row is not None
                    self.assertEqual(row["status"], "sent")
                finally:
                    await traffic_monitor.stop()

    async def test_outbound_service_reuses_active_serial_monitor_connection(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                interface_id = insert_serial_modem(device_path=slave_path, baud_rate=9600)
                update_station_settings(
                    {
                        "callsign": "sq9xyz",
                        "ssid": "9",
                        "beacon_interface_id": str(interface_id),
                        "beacon_comment": "Test beacon",
                        "beacon_interval_minutes": "15",
                        "beacon_path": "WIDE2-2",
                        "status_text": "Station online",
                        "status_interval_minutes": "30",
                        "latitude": "52.2297",
                        "longitude": "21.0122",
                        "symbol_table": "/",
                        "symbol_code": ">",
                        "default_units": "metric",
                        "tx_enabled": "1",
                    }
                )
                execute(
                    """
                    INSERT INTO outbound_jobs(
                        kind, interface_id, payload_json, status, scheduled_at,
                        locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                    )
                    VALUES (
                        'beacon', ?, '{"callsign":"SQ9XYZ","ssid":"9","latitude":52.2297,"longitude":21.0122,"symbol_table":"/","symbol_code":">","beacon_comment":"Test beacon","beacon_path":"WIDE2-2","trigger":"manual"}',
                        'queued', '2026-01-01T00:00:00+00:00',
                        NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (interface_id,),
                )

                traffic_monitor = TrafficMonitorService(reconnect_delay=0.1)
                try:
                    await traffic_monitor.start()
                    await wait_until(lambda: traffic_monitor.snapshot()["status"] == "connected", timeout=3.0)

                    job = claim_next_outbound_job()
                    assert job is not None
                    await OutboundService(traffic_monitor=traffic_monitor)._process_job(job)

                    runtime_job = get_outbound_job(int(job["id"]))
                    assert runtime_job is not None
                    expected_line = build_beacon_tnc2(runtime_job["payload"])
                    expected_frame = build_tnc2_kiss_frame(expected_line)
                    self.assertEqual(await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0), expected_frame)

                    rx_frame = build_tnc2_kiss_frame("SQ9MDD-4>APRS:>RX after shared serial TX")
                    os.write(master_fd, rx_frame)
                    await wait_until(
                        lambda: (
                            fetch_one(
                                "SELECT COUNT(*) AS total FROM traffic_frames WHERE format = 'TNC2' AND line LIKE ?",
                                ("%RX after shared serial TX%",),
                            )
                            or {"total": 0}
                        )["total"] >= 1,
                        timeout=2.0,
                    )
                finally:
                    await traffic_monitor.stop()

    async def test_outbound_service_uses_shared_serial_runtime_path_when_multiple_interfaces_enabled(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                interface_id = insert_serial_modem(device_path=slave_path, baud_rate=9600)
                execute(
                    """
                    INSERT INTO modems(
                        name, modem_type, band, device_path, enabled,
                        expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
                        notes, created_at, updated_at
                    )
                    VALUES(
                        'Aux TCP TNC', 'TCP', '70cm', '127.0.0.1:65534', 1,
                        0, '127.0.0.1', 8002, '',
                        '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """
                )
                update_station_settings(
                    {
                        "callsign": "sq9xyz",
                        "ssid": "9",
                        "beacon_interface_id": str(interface_id),
                        "beacon_comment": "Test beacon",
                        "beacon_interval_minutes": "15",
                        "beacon_path": "WIDE2-2",
                        "status_text": "Station online",
                        "status_interval_minutes": "30",
                        "latitude": "52.2297",
                        "longitude": "21.0122",
                        "symbol_table": "/",
                        "symbol_code": ">",
                        "default_units": "metric",
                        "tx_enabled": "1",
                    }
                )
                execute(
                    """
                    INSERT INTO outbound_jobs(
                        kind, interface_id, payload_json, status, scheduled_at,
                        locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                    )
                    VALUES (
                        'beacon', ?, '{"callsign":"SQ9XYZ","ssid":"9","latitude":52.2297,"longitude":21.0122,"symbol_table":"/","symbol_code":">","beacon_comment":"Test beacon","beacon_path":"WIDE2-2","trigger":"manual"}',
                        'queued', '2026-01-01T00:00:00+00:00',
                        NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (interface_id,),
                )

                traffic_monitor = TrafficMonitorService(reconnect_delay=0.1)
                try:
                    await traffic_monitor.start()
                    await wait_until(lambda: traffic_monitor.snapshot()["connected_interfaces"] >= 1, timeout=3.0)

                    job = claim_next_outbound_job()
                    assert job is not None
                    with patch.object(
                        traffic_monitor,
                        "send_outbound_frame",
                        wraps=traffic_monitor.send_outbound_frame,
                    ) as send_mock:
                        await OutboundService(traffic_monitor=traffic_monitor)._process_job(job)
                    send_mock.assert_called_once()
                    self.assertEqual(send_mock.call_args.kwargs["interface_id"], interface_id)

                    runtime_job = get_outbound_job(int(job["id"]))
                    assert runtime_job is not None
                    expected_line = build_beacon_tnc2(runtime_job["payload"])
                    expected_frame = build_tnc2_kiss_frame(expected_line)
                    self.assertEqual(await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0), expected_frame)
                finally:
                    await traffic_monitor.stop()

    async def test_outbound_service_does_not_use_direct_serial_fallback_when_shared_runtime_send_fails(self) -> None:
        with temporary_database():
            interface_id = insert_serial_modem(device_path="/dev/ttyUSB-mock-shared-runtime", baud_rate=9600)
            update_station_settings(
                {
                    "callsign": "sq9xyz",
                    "ssid": "9",
                    "beacon_interface_id": str(interface_id),
                    "beacon_comment": "Test beacon",
                    "beacon_interval_minutes": "15",
                    "beacon_path": "WIDE2-2",
                    "status_text": "Station online",
                    "status_interval_minutes": "30",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "1",
                }
            )
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES (
                    'beacon', ?, '{"callsign":"SQ9XYZ","ssid":"9","latitude":52.2297,"longitude":21.0122,"symbol_table":"/","symbol_code":">","beacon_comment":"Test beacon","beacon_path":"WIDE2-2","trigger":"manual"}',
                    'queued', '2026-01-01T00:00:00+00:00',
                    NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                )
                """,
                (interface_id,),
            )

            job = claim_next_outbound_job()
            assert job is not None
            traffic_monitor = TrafficMonitorService(reconnect_delay=0.1)
            send_mock = AsyncMock(return_value=False)
            restart_mock = AsyncMock()
            with patch.object(traffic_monitor, "send_outbound_frame", send_mock):
                with patch.object(traffic_monitor, "restart", restart_mock):
                    await OutboundService(traffic_monitor=traffic_monitor)._process_job(job)

            self.assertEqual(send_mock.await_count, 1)
            self.assertEqual(send_mock.await_args_list[0].kwargs["interface_id"], interface_id)
            restart_mock.assert_not_awaited()
            row = fetch_one("SELECT status, last_error FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
            assert row is not None
            self.assertEqual(str(row["status"]), "failed")
            self.assertIn("Serial TX must use the active shared runtime", str(row["last_error"] or ""))

    async def test_outbound_marks_digi_tx_failed_for_non_printable_aprs_payload(self) -> None:
        with temporary_database():
            interface_id = insert_serial_modem(device_path="/dev/ttyUSB-mock", baud_rate=9600)
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES (
                    'digi_tx', ?, '{"line":"SQ9XYZ-9>AP?RS:>Bad destination"}',
                    'queued', '2026-01-01T00:00:00+00:00',
                    NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                )
                """,
                (interface_id,),
            )

            job = claim_next_outbound_job()
            assert job is not None
            await OutboundService()._process_job(job)

            row = fetch_one("SELECT status, last_error FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
            assert row is not None
            self.assertEqual(str(row["status"]), "failed")
            self.assertIn("Invalid AX.25 callsign", str(row["last_error"] or ""))

    async def test_outbound_serial_tx_requires_active_traffic_monitor_runtime(self) -> None:
        with temporary_database():
            interface_id = insert_serial_modem(device_path="/dev/ttyUSB-mock", baud_rate=9600)
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES (
                    'digi_tx', ?, '{"line":"SQ9XYZ-9>APRS:>Direct serial TX"}',
                    'queued', '2026-01-01T00:00:00+00:00',
                    NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                )
                """,
                (interface_id,),
            )

            job = claim_next_outbound_job()
            assert job is not None
            await OutboundService()._process_job(job)

            row = fetch_one("SELECT status, last_error FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
            assert row is not None
            self.assertEqual(str(row["status"]), "failed")
            self.assertIn("requires an active traffic monitor runtime", str(row["last_error"] or ""))

    async def test_disable_enable_recreates_runtime_and_closes_old_serial_handle(self) -> None:
        with temporary_database():
            interface_id = insert_serial_modem(device_path="/dev/ttyUSB-lifecycle", baud_rate=9600)
            opened_handles = [401, 402]
            closed_handles: list[int] = []

            def fake_open(path: str, baud_rate: int, *, flush_buffers: bool = True) -> int:
                self.assertEqual(path, "/dev/ttyUSB-lifecycle")
                self.assertEqual(baud_rate, 9600)
                self.assertTrue(flush_buffers)
                return opened_handles.pop(0)

            def fake_close(fd: int | None, **_kwargs: object) -> None:
                if fd is not None:
                    closed_handles.append(int(fd))

            def fake_read(_fd: int, *, max_bytes: int = 1024, timeout: float = 1.0) -> bytes:
                _ = max_bytes
                _ = timeout
                return b""

            def fake_write(_fd: int, _data: bytes, *, timeout: float = 1.0, drain: bool = False) -> None:
                _ = timeout
                _ = drain

            service = TrafficMonitorService(reconnect_delay=0.1)
            with patch.object(serial_broker_module, "open_serial_device", side_effect=fake_open):
                with patch.object(serial_broker_module, "close_serial_device", side_effect=fake_close):
                    with patch.object(serial_broker_module, "read_serial_chunk", side_effect=fake_read):
                        with patch.object(serial_broker_module, "write_serial_data", side_effect=fake_write):
                            try:
                                await service.start()
                                await wait_until(
                                    lambda: service.snapshot()["status"] == "connected" and service.snapshot()["modem_count"] == 1,
                                    timeout=3.0,
                                )

                                execute("UPDATE modems SET enabled = 0 WHERE id = ?", (interface_id,))
                                await wait_until(lambda: service.snapshot()["modem_count"] == 0, timeout=4.0)

                                execute("UPDATE modems SET enabled = 1 WHERE id = ?", (interface_id,))
                                await wait_until(
                                    lambda: service.snapshot()["status"] == "connected" and service.snapshot()["modem_count"] == 1,
                                    timeout=4.0,
                                )
                            finally:
                                await service.stop()

            self.assertEqual(opened_handles, [])
            self.assertIn(401, closed_handles)
            self.assertIn(402, closed_handles)

    async def test_tx_failure_triggers_reconnect_and_rx_continues(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                interface_id = insert_serial_modem(device_path=slave_path, baud_rate=9600)
                execute(
                    """
                    INSERT INTO outbound_jobs(
                        kind, interface_id, payload_json, status, scheduled_at,
                        locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                    )
                    VALUES (
                        'digi_tx', ?, '{"line":"SQ9XYZ-9>APRS:>TX fail then recover"}',
                        'queued', '2026-01-01T00:00:00+00:00',
                        NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (interface_id,),
                )

                traffic_monitor = TrafficMonitorService(reconnect_delay=0.1)
                failed_once = False

                def flaky_write_serial_data(fd: int, data: bytes, *, timeout: float = 1.0, drain: bool = False) -> None:
                    nonlocal failed_once
                    if not failed_once:
                        failed_once = True
                        raise OSError("Simulated serial TX failure")
                    base_write_serial_data(fd, data, timeout=timeout, drain=drain)

                try:
                    await traffic_monitor.start()
                    await wait_until(lambda: traffic_monitor.snapshot()["status"] == "connected", timeout=3.0)

                    job = claim_next_outbound_job()
                    assert job is not None
                    with patch.object(serial_broker_module, "write_serial_data", side_effect=flaky_write_serial_data):
                        await OutboundService(traffic_monitor=traffic_monitor)._process_job(job)

                    await wait_until(lambda: traffic_monitor.snapshot()["status"] == "connected", timeout=3.0)

                    os.write(master_fd, build_tnc2_kiss_frame("SQ9MDD-4>APRS:>RX after TX failure"))
                    await wait_until(
                        lambda: (
                            fetch_one(
                                "SELECT COUNT(*) AS total FROM traffic_frames WHERE format = 'TNC2' AND line LIKE ?",
                                ("%RX after TX failure%",),
                            )
                            or {"total": 0}
                        )["total"] >= 1,
                        timeout=2.0,
                    )
                finally:
                    await traffic_monitor.stop()


if __name__ == "__main__":
    unittest.main()
