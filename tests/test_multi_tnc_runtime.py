import asyncio
import contextlib
import os
import socket
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.services.content import traffic_snapshot as build_traffic_snapshot
from app.services.outbound import build_tnc2_kiss_frame
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


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def insert_tcp_modem(*, name: str, band: str, device_path: str) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, baud_rate, enabled,
            expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
            notes, created_at, updated_at
        )
        VALUES (?, 'TCP', ?, ?, NULL, 1, 0, '127.0.0.1', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, band, device_path),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


async def wait_until(predicate, *, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Condition was not met before timeout.")


class MultiTncRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_monitor_tracks_multiple_enabled_tncs_and_persists_shared_traffic_log(self) -> None:
        with temporary_database():
            port_2m = free_tcp_port()
            port_70cm = free_tcp_port()
            modem_2m_id = insert_tcp_modem(name="TNC-2m", band="2m", device_path=f"127.0.0.1:{port_2m}")
            modem_70cm_id = insert_tcp_modem(name="TNC-70cm", band="70cm", device_path=f"127.0.0.1:{port_70cm}")

            ready_2m: asyncio.Future[asyncio.StreamWriter] = asyncio.get_running_loop().create_future()
            ready_70cm: asyncio.Future[asyncio.StreamWriter] = asyncio.get_running_loop().create_future()

            async def handle_2m(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                if not ready_2m.done():
                    ready_2m.set_result(writer)
                await writer.wait_closed()

            async def handle_70cm(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                if not ready_70cm.done():
                    ready_70cm.set_result(writer)
                await writer.wait_closed()

            server_2m = await asyncio.start_server(handle_2m, host="127.0.0.1", port=port_2m)
            server_70cm = await asyncio.start_server(handle_70cm, host="127.0.0.1", port=port_70cm)
            service = TrafficMonitorService(reconnect_delay=0.1)
            writer_2m: asyncio.StreamWriter | None = None
            writer_70cm: asyncio.StreamWriter | None = None
            try:
                await service.start()
                await wait_until(
                    lambda: len(service.snapshot().get("interfaces") or []) == 2
                    and all(item["status"] == "connected" for item in service.snapshot()["interfaces"]),
                    timeout=4.0,
                )

                writer_2m = await asyncio.wait_for(ready_2m, timeout=1.0)
                writer_70cm = await asyncio.wait_for(ready_70cm, timeout=1.0)

                payload_2m = build_tnc2_kiss_frame("SQ9MDD-4>APRS:>RX on 2m")
                payload_70cm = build_tnc2_kiss_frame("SQ9MDD-4>APRS:>RX on 70cm")
                writer_2m.write(payload_2m)
                writer_70cm.write(payload_70cm)
                await writer_2m.drain()
                await writer_70cm.drain()

                await wait_until(
                    lambda: (
                        fetch_one(
                            """
                            SELECT COUNT(*) AS total
                            FROM traffic_frames
                            WHERE direction = 'rx'
                              AND interface_id IN (?, ?)
                            """,
                            (modem_2m_id, modem_70cm_id),
                        )
                        or {"total": 0}
                    )["total"] >= 2,
                    timeout=3.0,
                )

                snapshot = service.snapshot()
                self.assertEqual(snapshot["status"], "connected")
                self.assertEqual(snapshot["connected_interfaces"], 2)
                self.assertEqual({item["name"] for item in snapshot["interfaces"]}, {"TNC-2m", "TNC-70cm"})
                self.assertTrue(any(frame["source"] == "TNC-2m" and frame["direction"] == "RX" for frame in snapshot["frames"]))
                self.assertTrue(any(frame["source"] == "TNC-70cm" and frame["direction"] == "RX" for frame in snapshot["frames"]))

                db_snapshot = build_traffic_snapshot(limit=20)
                self.assertEqual(len(db_snapshot["interfaces"]), 2)
                self.assertTrue(any(frame["interface_id"] == modem_2m_id and frame["band"] == "2m" for frame in db_snapshot["frames"]))
                self.assertTrue(any(frame["interface_id"] == modem_70cm_id and frame["band"] == "70cm" for frame in db_snapshot["frames"]))
            finally:
                if writer_2m is not None:
                    writer_2m.close()
                    try:
                        await writer_2m.wait_closed()
                    except OSError:
                        pass
                if writer_70cm is not None:
                    writer_70cm.close()
                    try:
                        await writer_70cm.wait_closed()
                    except OSError:
                        pass
                await service.stop()
                server_2m.close()
                server_70cm.close()
                await server_2m.wait_closed()
                await server_70cm.wait_closed()
