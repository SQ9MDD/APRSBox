import asyncio
import contextlib
import os
import socket
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.services.content import get_aprs_symbol_icon_path, traffic_snapshot as build_traffic_snapshot
from app.services.outbound import build_tnc2_kiss_frame, claim_next_outbound_job
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
    async def test_traffic_snapshot_marks_local_generated_and_repeated_tx_rows(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD',
                    ssid = '4'
                WHERE id = 1
                """
            )
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD-4>APBOX0:=5218.37N/02104.87E-Test beacon', '0', 'TX', 43, '', '2026-01-01T00:00:02+00:00'),
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD-4>APBOX0::BLN1     :System bulletin', '0', 'TX', 45, '', '2026-01-01T00:00:01+00:00'),
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SP8XYZ-9>APRS,WIDE1-1:>Relayed packet', '0', 'TX', 38, '', '2026-01-01T00:00:00+00:00'),
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SP9AAA-1>APRS:>Remote proxy packet', '0', 'TX-PROXY', 33, '', '2026-01-01T00:00:03+00:00')
                """
            )

            snapshot = build_traffic_snapshot(limit=10)
            row_classes = {frame["line"]: frame["row_class"] for frame in snapshot["frames"]}

            self.assertEqual(row_classes["SQ9MDD-4>APBOX0:=5218.37N/02104.87E-Test beacon"], "traffic-log-row-own-beacon-tx")
            self.assertEqual(row_classes["SQ9MDD-4>APBOX0::BLN1     :System bulletin"], "traffic-log-row-own-message-tx")
            self.assertEqual(row_classes["SP8XYZ-9>APRS,WIDE1-1:>Relayed packet"], "traffic-log-row-repeated-tx")
            self.assertEqual(row_classes["SP9AAA-1>APRS:>Remote proxy packet"], "traffic-log-row-proxy-tx")

    async def test_traffic_snapshot_marks_wx_from_local_callsign_with_other_ssid_as_weather(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD',
                    ssid = '4'
                WHERE id = 1
                """
            )
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD-3>APBOX0,RFONLY:=5215.03N/02055.60E_.../...t...X121', '0', 'TX', 62, '', '2026-01-01T00:00:02+00:00')
                """
            )

            snapshot = build_traffic_snapshot(limit=10)
            row_classes = {frame["line"]: frame["row_class"] for frame in snapshot["frames"]}

            self.assertEqual(
                row_classes["SQ9MDD-3>APBOX0,RFONLY:=5215.03N/02055.60E_.../...t...X121"],
                "traffic-log-row-own-wx-tx",
            )

    async def test_traffic_snapshot_uses_object_name_and_symbol_icon_for_object_frames(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES
                    (
                        'OpenWebRX MQTT',
                        1,
                        'rx',
                        '70cm',
                        'TNC2',
                        'SQ5ABC-9>APBOX0:;X2922759 *111207z5228.37N/02104.87EORS41-SGP P=169.90hPa /A=042219 F=4024 RSM424 FW v20506',
                        '0',
                        'RX',
                        114,
                        '',
                        '2026-01-01T00:00:02+00:00'
                    )
                """
            )

            snapshot = build_traffic_snapshot(limit=10)
            frame = next(item for item in snapshot["frames"] if item["line"].startswith("SQ5ABC-9>APBOX0:;X2922759"))

            self.assertEqual(frame["display_callsign"], "X2922759")
            self.assertEqual(frame["display_packet_group"], "object")
            self.assertEqual(frame["display_icon_path"], get_aprs_symbol_icon_path("/O"))

    async def test_traffic_snapshot_treats_local_ssid_zero_as_base_callsign_for_row_classification(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD',
                    ssid = '0'
                WHERE id = 1
                """
            )
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD>APBOX0:=5218.37N/02104.87E-Test beacon', '0', 'TX', 41, '', '2026-01-01T00:00:02+00:00')
                """
            )

            snapshot = build_traffic_snapshot(limit=10)
            row_classes = {frame["line"]: frame["row_class"] for frame in snapshot["frames"]}
            self.assertEqual(row_classes["SQ9MDD>APBOX0:=5218.37N/02104.87E-Test beacon"], "traffic-log-row-own-beacon-tx")

    async def test_traffic_snapshot_marks_rx_local_rows_and_skipped_tx_rows(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD',
                    ssid = '4'
                WHERE id = 1
                """
            )
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES
                    ('TNC-2m', 1, 'rx', '2m', 'TNC2', 'SQ9MDD-4>APBOX0:=5218.37N/02104.87E-Test beacon', '0', 'RX', 43, '', '2026-01-01T00:00:03+00:00'),
                    ('TNC-2m', 1, 'rx', '2m', 'TNC2', 'SQ9MDD-4>APBOX0::BLN1     :System bulletin', '0', 'RX', 45, '', '2026-01-01T00:00:02+00:00'),
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD-4>APBOX0:=5218.37N/02104.87E-Test beacon', '0', 'TX-SKIP', 43, '', '2026-01-01T00:00:01+00:00')
                """
            )

            snapshot = build_traffic_snapshot(limit=10)
            tx_skip_row = next(frame for frame in snapshot["frames"] if frame["command"] == "TX-SKIP")
            rx_beacon_row = next(
                frame
                for frame in snapshot["frames"]
                if frame["direction"] == "RX" and frame["line"] == "SQ9MDD-4>APBOX0:=5218.37N/02104.87E-Test beacon"
            )
            rx_bulletin_row = next(
                frame
                for frame in snapshot["frames"]
                if frame["direction"] == "RX" and frame["line"] == "SQ9MDD-4>APBOX0::BLN1     :System bulletin"
            )

            self.assertEqual(rx_beacon_row["row_class"], "traffic-log-row-own-beacon-rx")
            self.assertEqual(rx_bulletin_row["row_class"], "traffic-log-row-own-message-rx")
            self.assertIn("traffic-log-row-own-beacon-tx", tx_skip_row["row_class"])
            self.assertIn("traffic-log-row-skipped", tx_skip_row["row_class"])

    async def test_traffic_snapshot_marks_own_query_and_object_rows(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD',
                    ssid = '4'
                WHERE id = 1
                """
            )
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD-4>APRS:?APRSP', '0', 'TX', 18, '', '2026-01-01T00:00:04+00:00'),
                    ('TNC-2m', 1, 'rx', '2m', 'TNC2', 'SQ9MDD-4>APRS:?APRSP', '0', 'RX', 18, '', '2026-01-01T00:00:03+00:00'),
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD-4>APRS:;OBJTEST *010101z5218.37N/02104.87E-Test', '0', 'TX', 58, '', '2026-01-01T00:00:02+00:00'),
                    ('TNC-2m', 1, 'rx', '2m', 'TNC2', 'SQ9MDD-4>APRS:;OBJTEST *010101z5218.37N/02104.87E-Test', '0', 'RX', 58, '', '2026-01-01T00:00:01+00:00')
                """
            )

            snapshot = build_traffic_snapshot(limit=10)
            row_classes = {(frame["direction"], frame["line"]): frame["row_class"] for frame in snapshot["frames"]}

            self.assertEqual(row_classes[("TX", "SQ9MDD-4>APRS:?APRSP")], "traffic-log-row-own-message-tx")
            self.assertEqual(row_classes[("RX", "SQ9MDD-4>APRS:?APRSP")], "traffic-log-row-own-message-rx")
            self.assertEqual(
                row_classes[("TX", "SQ9MDD-4>APRS:;OBJTEST *010101z5218.37N/02104.87E-Test")],
                "traffic-log-row-own-beacon-tx",
            )
            self.assertEqual(
                row_classes[("RX", "SQ9MDD-4>APRS:;OBJTEST *010101z5218.37N/02104.87E-Test")],
                "traffic-log-row-own-beacon-rx",
            )

    async def test_traffic_snapshot_marks_proxy_tx_even_for_own_source(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD',
                    ssid = '4'
                WHERE id = 1
                """
            )
            execute(
                """
                INSERT INTO traffic_frames(
                    source, interface_id, direction, band, format, line, port, command, length, hex, created_at
                )
                VALUES
                    ('TNC-2m', 1, 'tx', '2m', 'TNC2-TX', 'SQ9MDD-4>APRS:>Proxy-originated frame', '0', 'TX-PROXY', 36, '', '2026-01-01T00:00:03+00:00')
                """
            )

            snapshot = build_traffic_snapshot(limit=10)
            row_classes = {frame["line"]: frame["row_class"] for frame in snapshot["frames"]}
            self.assertEqual(row_classes["SQ9MDD-4>APRS:>Proxy-originated frame"], "traffic-log-row-proxy-tx")

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

    async def test_outbound_service_reuses_active_tcp_monitor_connection_for_tx(self) -> None:
        with temporary_database():
            tnc_port = free_tcp_port()
            modem_id = insert_tcp_modem(name="TNC-2m", band="2m", device_path=f"127.0.0.1:{tnc_port}")

            accepted_connections = 0
            tnc_reader_queue: asyncio.Queue[bytes] = asyncio.Queue()

            async def handle_tnc_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                nonlocal accepted_connections
                accepted_connections += 1
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
            traffic_monitor = TrafficMonitorService(reconnect_delay=0.1)
            try:
                await traffic_monitor.start()
                await wait_until(
                    lambda: len(traffic_monitor.snapshot().get("interfaces") or []) == 1
                    and traffic_monitor.snapshot()["interfaces"][0]["status"] == "connected",
                    timeout=4.0,
                )
                self.assertEqual(accepted_connections, 1)

                line = "SQ9MDD-4>APRS:>TCP monitor TX"
                expected_frame = build_tnc2_kiss_frame(line)
                execute(
                    """
                    INSERT INTO outbound_jobs(
                        kind, interface_id, payload_json, status, scheduled_at,
                        locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                    )
                    VALUES (
                        'digi_tx', ?, ?, 'queued', '2026-01-01T00:00:00+00:00',
                        NULL, NULL, NULL, 0, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                    )
                    """,
                    (modem_id, '{"line":"SQ9MDD-4>APRS:>TCP monitor TX"}'),
                )

                job = claim_next_outbound_job()
                assert job is not None
                await OutboundService(traffic_monitor=traffic_monitor)._process_job(job)

                self.assertEqual(await asyncio.wait_for(tnc_reader_queue.get(), timeout=1.0), expected_frame)
                self.assertEqual(accepted_connections, 1)

                row = fetch_one("SELECT status FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
                assert row is not None
                self.assertEqual(row["status"], "sent")
            finally:
                await traffic_monitor.stop()
                tnc_server.close()
                await tnc_server.wait_closed()
