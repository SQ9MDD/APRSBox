import asyncio
import contextlib
import os
import pty
import select
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import init_db
from app.services import serial_broker as serial_broker_module
from app.services.serial_broker import RxSilenceReconnectWatchdog, SerialKissTcpBroker


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


class SerialBrokerTests(unittest.IsolatedAsyncioTestCase):
    def test_serial_rx_timestamp_segments_follow_tcp_split_and_merge(self) -> None:
        broker = SerialKissTcpBroker(
            modem_id=99,
            tnc_name="Timestamp test",
            device_path="/dev/null",
            baud_rate=9600,
        )
        with broker._lock:
            broker._serial_rx_segments.extend(
                ([4, 10.0, "first"], [6, 20.0, "second"])
            )

        self.assertEqual(broker.consume_serial_rx_timestamp(2), (10.0, "first"))
        self.assertEqual(broker.consume_serial_rx_timestamp(5), (10.0, "first"))
        self.assertEqual(broker.consume_serial_rx_timestamp(3), (20.0, "second"))
        self.assertIsNone(broker.consume_serial_rx_timestamp(1))

    def test_shared_rx_silence_watchdog_resets_on_any_bytes_and_supports_disabled(self) -> None:
        now = [100.0]
        watchdog = RxSilenceReconnectWatchdog(30, clock=lambda: now[0])

        now[0] = 129.0
        self.assertFalse(watchdog.expired())
        watchdog.record_rx()
        now[0] = 158.0
        self.assertFalse(watchdog.expired())
        now[0] = 159.0
        self.assertTrue(watchdog.expired())

        disabled = RxSilenceReconnectWatchdog(0, clock=lambda: now[0])
        now[0] = 10_000.0
        self.assertFalse(disabled.expired())
        self.assertEqual(disabled.read_timeout(5.0), 5.0)

    async def test_forwards_tcp_to_serial_without_modification(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                broker = SerialKissTcpBroker(
                    modem_id=1,
                    tnc_name="Serial Broker TNC",
                    device_path=slave_path,
                    baud_rate=9600,
                    reconnect_delay=0.1,
                )
                writer: asyncio.StreamWriter | None = None
                try:
                    await broker.start()
                    _reader, writer = await asyncio.open_connection("127.0.0.1", broker.port)
                    payload = bytes([0xC0, 0x00, 0xDB, 0xDD, 0x1C, 0x0D, 0x0A, 0xC0])
                    writer.write(payload)
                    await writer.drain()
                    received = await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0)
                    self.assertEqual(received, payload)
                finally:
                    if writer is not None:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except OSError:
                            pass
                    await broker.stop()

    async def test_forwards_serial_to_tcp_without_modification(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                broker = SerialKissTcpBroker(
                    modem_id=2,
                    tnc_name="Serial Broker TNC RX",
                    device_path=slave_path,
                    baud_rate=9600,
                    reconnect_delay=0.1,
                )
                writer: asyncio.StreamWriter | None = None
                try:
                    await broker.start()
                    reader, writer = await asyncio.open_connection("127.0.0.1", broker.port)
                    payload = bytes([0xC0, 0x00, 0xDB, 0xDC, 0xDB, 0xDD, 0x7F, 0xC0])
                    os.write(master_fd, payload)
                    self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), timeout=1.0), payload)
                finally:
                    if writer is not None:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except OSError:
                            pass
                    await broker.stop()

    async def test_rejects_second_client(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (_master_fd, slave_path):
                broker = SerialKissTcpBroker(
                    modem_id=3,
                    tnc_name="Serial Broker Single Client",
                    device_path=slave_path,
                    baud_rate=9600,
                    reconnect_delay=0.1,
                )
                writer_1: asyncio.StreamWriter | None = None
                writer_2: asyncio.StreamWriter | None = None
                try:
                    await broker.start()
                    _reader_1, writer_1 = await asyncio.open_connection("127.0.0.1", broker.port)
                    await wait_until(lambda: broker._client_writer is not None, timeout=1.0)
                    reader_2, writer_2 = await asyncio.open_connection("127.0.0.1", broker.port)
                    self.assertEqual(await asyncio.wait_for(reader_2.read(1), timeout=1.0), b"")
                finally:
                    if writer_1 is not None:
                        writer_1.close()
                        try:
                            await writer_1.wait_closed()
                        except OSError:
                            pass
                    if writer_2 is not None:
                        writer_2.close()
                        try:
                            await writer_2.wait_closed()
                        except OSError:
                            pass
                    await broker.stop()

    async def test_keeps_serial_open_and_accepts_reconnect_after_client_disconnect(self) -> None:
        with temporary_database():
            with pseudo_serial_device() as (master_fd, slave_path):
                broker = SerialKissTcpBroker(
                    modem_id=4,
                    tnc_name="Serial Broker Reconnect",
                    device_path=slave_path,
                    baud_rate=9600,
                    reconnect_delay=0.1,
                )
                writer_1: asyncio.StreamWriter | None = None
                writer_2: asyncio.StreamWriter | None = None
                try:
                    await broker.start()
                    _reader_1, writer_1 = await asyncio.open_connection("127.0.0.1", broker.port)
                    writer_1.close()
                    await writer_1.wait_closed()
                    writer_1 = None
                    await wait_until(lambda: broker._client_writer is None, timeout=1.5)

                    _reader_2, writer_2 = await asyncio.open_connection("127.0.0.1", broker.port)
                    payload = b"\xC0\x00RECONNECT\xC0"
                    writer_2.write(payload)
                    await writer_2.drain()
                    self.assertEqual(await asyncio.to_thread(read_master_chunk, master_fd, timeout=1.0), payload)
                finally:
                    if writer_1 is not None:
                        writer_1.close()
                        try:
                            await writer_1.wait_closed()
                        except OSError:
                            pass
                    if writer_2 is not None:
                        writer_2.close()
                        try:
                            await writer_2.wait_closed()
                        except OSError:
                            pass
                    await broker.stop()

    async def test_serial_write_calls_are_serialized(self) -> None:
        broker = SerialKissTcpBroker(
            modem_id=5,
            tnc_name="Serial Broker Lock",
            device_path="/dev/ttyUSB-mock",
            baud_rate=9600,
            reconnect_delay=0.1,
        )
        state_lock = threading.Lock()
        in_flight = 0
        max_in_flight = 0

        def slow_write(fd: int, data: bytes, *, timeout: float = 1.0, drain: bool = False) -> None:
            nonlocal in_flight, max_in_flight
            _ = timeout
            _ = drain
            self.assertEqual(fd, 123)
            self.assertTrue(data.startswith(b"\xC0\x00"))
            with state_lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.04)
            with state_lock:
                in_flight -= 1

        with patch.object(serial_broker_module, "write_serial_data", side_effect=slow_write):
            first = asyncio.create_task(broker._write_to_serial(serial_fd=123, chunk=b"\xC0\x00A\xC0"))
            second = asyncio.create_task(broker._write_to_serial(serial_fd=123, chunk=b"\xC0\x00B\xC0"))
            await asyncio.gather(first, second)

        self.assertEqual(max_in_flight, 1)


if __name__ == "__main__":
    unittest.main()
