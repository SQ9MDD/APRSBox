import asyncio
import contextlib
import os
import pty
import select
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_one, init_db
from app.services.content import get_section_row, safe_create_section_row, update_station_settings
from app.services.outbound import build_beacon_tnc2, build_tnc2_kiss_frame, claim_next_outbound_job, get_outbound_job
from app.services.outbound_runtime import OutboundService
from app.services.traffic import TrafficMonitorService


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


def insert_serial_modem(*, device_path: str, baud_rate: int = 9600, enabled: int = 1) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, baud_rate, enabled,
            expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
            notes, created_at, updated_at
        )
        VALUES ('Serial TNC', 'SERIALL', '2m', ?, ?, ?, 0, '127.0.0.1', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (device_path, baud_rate, enabled),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = 'Serial TNC'")
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


class SerialTncRuntimeTests(unittest.IsolatedAsyncioTestCase):
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
                await OutboundService()._process_job(job)

                runtime_job = get_outbound_job(int(job["id"]))
                assert runtime_job is not None
                expected_line = build_beacon_tnc2(runtime_job["payload"])
                expected_frame = build_tnc2_kiss_frame(expected_line)
                written_frame = await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0)

                self.assertEqual(written_frame, expected_frame)
                row = fetch_one("SELECT status FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
                assert row is not None
                self.assertEqual(row["status"], "sent")

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

    async def test_outbound_service_uses_direct_serial_path_when_multiple_interfaces_enabled(self) -> None:
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
                        side_effect=AssertionError("serial TX should bypass monitor path in multi-interface mode"),
                    ):
                        await OutboundService(traffic_monitor=traffic_monitor)._process_job(job)

                    runtime_job = get_outbound_job(int(job["id"]))
                    assert runtime_job is not None
                    expected_line = build_beacon_tnc2(runtime_job["payload"])
                    expected_frame = build_tnc2_kiss_frame(expected_line)
                    self.assertEqual(await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0), expected_frame)
                finally:
                    await traffic_monitor.stop()


if __name__ == "__main__":
    unittest.main()
