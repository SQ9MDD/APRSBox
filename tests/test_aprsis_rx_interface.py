import asyncio
import contextlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.db import execute, fetch_one, init_db, set_app_setting, utc_now
from app.services import content
from app.services.aprsis import (
    AprsisClientService,
    aprsis_connection_required,
    build_aprsis_login_line,
    get_aprsis_config,
    get_enabled_aprsis_interface,
)
from app.services.content import (
    dashboard_activity_series,
    dashboard_traffic_summary,
    get_visible_station_snapshots,
    monitoring_public_snapshot,
    safe_create_section_row,
)
from app.services.map_service import get_map_station_markers_payload
from app.services.radio_activity import run_radio_activity_aggregation
from app.services.traffic import process_normalized_tnc2_rx


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            content._TRAFFIC_SNAPSHOT_CACHE.clear()
            content._STATION_SNAPSHOT_CACHE.clear()
            content._VISIBLE_STATION_SNAPSHOT_TTL_CACHE.clear()
            yield database_path
        finally:
            content._TRAFFIC_SNAPSHOT_CACHE.clear()
            content._STATION_SNAPSHOT_CACHE.clear()
            content._VISIBLE_STATION_SNAPSHOT_TTL_CACHE.clear()
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def create_aprsis_interface(*, name: str = "Internet RX", server_filter: str = "", enabled: bool = True) -> int:
    success, error = safe_create_section_row(
        "modems",
        {
            "name": name,
            "band": "",
            "modem_type": "APRSIS",
            "device_path": server_filter,
            "enabled": "1" if enabled else None,
        },
    )
    if not success:
        raise AssertionError(error)
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


def enable_aprsis_tx_flow() -> None:
    timestamp = utc_now()
    execute(
        """
        INSERT INTO digi_flows(
            name, description, source_kind, source_ref, target_kind, target_ref,
            enabled, created_at, updated_at
        )
        VALUES ('RF to IS', '', 'receiver_rf', 'RF', 'tx_aprsis', 'aprsis', 1, ?, ?)
        """,
        (timestamp, timestamp),
    )


POSITION_LINE = "SP5ABC-9>APRS,TCPIP*:!5223.45N/02101.23E>APRS-IS test"


class AprsisInterfaceConfigurationTests(unittest.TestCase):
    def test_new_aprsis_interface_uses_default_filter_and_existing_igate_settings(self) -> None:
        with temporary_database():
            set_app_setting("aprsis_server", "example.aprs2.net")
            set_app_setting("aprsis_port", "10152")
            set_app_setting("aprsis_login", "SQ9XYZ-10")
            set_app_setting("aprsis_passcode", "12345")

            interface_id = create_aprsis_interface()
            row = fetch_one("SELECT modem_type, device_path FROM modems WHERE id = ?", (interface_id,))
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["modem_type"], "APRSIS")
            self.assertEqual(row["device_path"], "m/20")

            interface = get_enabled_aprsis_interface()
            config = get_aprsis_config()
            self.assertEqual((interface or {}).get("filter"), "m/20")
            self.assertEqual(config["server"], "example.aprs2.net")
            self.assertEqual(config["port"], 10152)
            self.assertEqual(config["login"], "SQ9XYZ-10")
            self.assertEqual(config["passcode"], "12345")

    def test_second_aprsis_interface_is_rejected_with_edit_guidance(self) -> None:
        with temporary_database():
            create_aprsis_interface(name="First")
            success, error = safe_create_section_row(
                "modems",
                {
                    "name": "Second",
                    "modem_type": "APRSIS",
                    "device_path": "r/52.23/21.01/50",
                    "enabled": "1",
                },
            )
            self.assertFalse(success)
            self.assertIn("Edit the existing interface", str(error))
            count = fetch_one("SELECT COUNT(*) AS total FROM modems WHERE modem_type = 'APRSIS'")
            self.assertEqual(int((count or {"total": -1})["total"]), 1)

    def test_login_line_contains_interface_filter_without_changing_auth_config(self) -> None:
        line = build_aprsis_login_line(
            login="SQ9XYZ-10",
            passcode="12345",
            server_filter="r/52.23/21.01/50",
        )
        self.assertIn("user SQ9XYZ-10 pass 12345", line)
        self.assertTrue(line.endswith("filter r/52.23/21.01/50"))


class AprsisReceivePipelineTests(unittest.TestCase):
    def _service(self, interface_id: int) -> AprsisClientService:
        service = AprsisClientService()
        service._desired_rx_interface = {
            "id": interface_id,
            "name": "Internet RX",
            "filter": "m/20",
        }
        return service

    def test_tnc2_line_reaches_standard_parser_history_station_and_map(self) -> None:
        with temporary_database():
            interface_id = create_aprsis_interface()
            service = self._service(interface_id)

            self.assertTrue(service._process_server_line(POSITION_LINE + "\r\n"))
            history = fetch_one(
                """
                SELECT source, source_kind, interface_id, direction, format, line
                FROM traffic_frames
                ORDER BY id DESC LIMIT 1
                """
            )
            self.assertIsNotNone(history)
            assert history is not None
            self.assertEqual(history["source_kind"], "aprsis")
            self.assertEqual(int(history["interface_id"]), interface_id)
            self.assertEqual(history["direction"].lower(), "rx")
            self.assertEqual(history["format"], "TNC2")
            self.assertIn("APRS-IS", history["source"])

            stations = get_visible_station_snapshots()
            station = next(item for item in stations if item["display_callsign"] == "SP5ABC-9")
            self.assertEqual(station["source_kind"], "aprsis")
            self.assertIsNone(station["last_heard_rf_at"])
            self.assertIsNotNone(station["last_seen_aprsis_at"])
            self.assertTrue(station["latitude"])
            self.assertTrue(station["longitude"])

            marker_payload = get_map_station_markers_payload()
            marker = next(item for item in marker_payload["stations"] if item["display_callsign"] == "SP5ABC-9")
            self.assertEqual(marker["source_kind"], "aprsis")
            self.assertFalse(marker["is_rf"])

    def test_comments_logresp_empty_and_malformed_lines_are_not_history(self) -> None:
        with temporary_database():
            interface_id = create_aprsis_interface()
            service = self._service(interface_id)

            self.assertFalse(service._process_server_line("# aprsc 2.1.10\r\n"))
            self.assertFalse(service._process_server_line("# logresp SQ9XYZ-10 verified, server TEST\r\n"))
            self.assertFalse(service._process_server_line("logresp SQ9XYZ-10 verified, server TEST\r\n"))
            self.assertFalse(service._process_server_line("\r\n"))
            self.assertFalse(service._process_server_line("not-a-tnc2-line\r\n"))
            row = fetch_one("SELECT COUNT(*) AS total FROM traffic_frames")
            self.assertEqual(int((row or {"total": -1})["total"]), 0)

    def test_aprsis_frame_is_excluded_from_every_statistics_input_and_public_telemetry(self) -> None:
        with temporary_database():
            interface_id = create_aprsis_interface()
            service = self._service(interface_id)
            self.assertTrue(service._process_server_line(POSITION_LINE))

            self.assertEqual(dashboard_traffic_summary()["decoded_aprs"], 0)
            self.assertEqual(dashboard_activity_series()["totals"]["rx"], 0)
            for table_name in (
                "traffic_device_station_device_hourly",
                "band_condition_audibility_buckets",
                "band_condition_activity_station_buckets",
                "band_condition_activity_buckets",
            ):
                row = fetch_one(f"SELECT COUNT(*) AS total FROM {table_name}")
                self.assertEqual(int((row or {"total": -1})["total"]), 0, table_name)

            run_radio_activity_aggregation(now_utc=datetime.now(timezone.utc) + timedelta(minutes=10), safety_delay_seconds=0)
            radio_rows = fetch_one("SELECT COUNT(*) AS total FROM radio_activity_5m")
            self.assertEqual(int((radio_rows or {"total": -1})["total"]), 0)

            content._TRAFFIC_SNAPSHOT_CACHE.clear()
            public_snapshot = monitoring_public_snapshot()
            self.assertEqual(public_snapshot["stats"]["frames_last_hour"]["raw_frames"], 0)
            self.assertEqual(public_snapshot["stats"]["stations"]["total"], 0)

    def test_rf_frame_still_updates_statistics_and_preserves_rf_heard_when_aprsis_is_newer(self) -> None:
        with temporary_database():
            rf_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).replace(microsecond=0).isoformat()
            self.assertTrue(
                process_normalized_tnc2_rx(
                    POSITION_LINE.replace("APRS-IS test", "RF test"),
                    source="Main RF",
                    source_kind="rf",
                    source_interface_id=7,
                    band="2m",
                    timestamp=rf_time,
                )
            )
            interface_id = create_aprsis_interface()
            self.assertTrue(self._service(interface_id)._process_server_line(POSITION_LINE))

            self.assertEqual(dashboard_traffic_summary()["decoded_aprs"], 1)
            device_rows = fetch_one("SELECT COUNT(*) AS total FROM traffic_device_station_device_hourly")
            band_rows = fetch_one("SELECT COUNT(*) AS total FROM band_condition_activity_buckets")
            self.assertGreater(int((device_rows or {"total": 0})["total"]), 0)
            self.assertGreater(int((band_rows or {"total": 0})["total"]), 0)

            run_radio_activity_aggregation(
                now_utc=datetime.now(timezone.utc) + timedelta(minutes=10),
                safety_delay_seconds=0,
            )
            radio_rx = fetch_one("SELECT COALESCE(SUM(rx_total), 0) AS total FROM radio_activity_5m")
            self.assertEqual(int((radio_rx or {"total": 0})["total"]), 1)

            station = next(item for item in get_visible_station_snapshots() if item["display_callsign"] == "SP5ABC-9")
            self.assertEqual(station["source_kind"], "aprsis")
            self.assertIsNotNone(station["last_heard_rf_at"])
            self.assertIsNotNone(station["last_seen_aprsis_at"])
            self.assertTrue(station["statistics_eligible"])


class AprsisSharedConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_rx_and_tx_share_one_tcp_writer_and_login_filter(self) -> None:
        class BlockingReader:
            def __init__(self) -> None:
                self.waiter = asyncio.Event()

            async def readline(self) -> bytes:
                await self.waiter.wait()
                return b""

        class RecordingWriter:
            def __init__(self) -> None:
                self.writes: list[bytes] = []
                self.closed = False

            def write(self, data: bytes) -> None:
                self.writes.append(data)

            async def drain(self) -> None:
                return None

            def close(self) -> None:
                self.closed = True

            async def wait_closed(self) -> None:
                return None

        with temporary_database():
            interface_id = create_aprsis_interface(server_filter="m/20")
            received: list[str] = []

            def rx_processor(line: str, **_context: object) -> bool:
                received.append(line)
                return True

            service = AprsisClientService(rx_processor=rx_processor)
            rx_interface = {"id": interface_id, "name": "Internet RX", "filter": "m/20"}
            service._desired_rx_interface = dict(rx_interface)
            reader = BlockingReader()
            writer = RecordingWriter()
            with patch("app.services.aprsis.asyncio.open_connection", new=AsyncMock(return_value=(reader, writer))) as opener:
                await service._connect(
                    ("example.aprs2.net", 14580, "SQ9XYZ-10", "12345"),
                    rx_interface=rx_interface,
                )

            self.assertEqual(opener.await_count, 1)
            self.assertIs(service._writer, writer)
            self.assertIn(b" filter m/20\r\n", writer.writes[0])
            self.assertTrue(service._process_server_line(POSITION_LINE))
            sent, _detail = await service.send_tnc2_line("SQ9XYZ-10>APRS:>TX test")
            self.assertTrue(sent)
            self.assertEqual(received, [POSITION_LINE])
            self.assertEqual(len(writer.writes), 2)
            await service._disconnect(reason="test complete", status="inactive")

    async def test_disabling_rx_keeps_connection_when_tx_flow_still_requires_it(self) -> None:
        class ExistingWriter:
            pass

        with temporary_database():
            interface_id = create_aprsis_interface()
            enable_aprsis_tx_flow()
            service = AprsisClientService()
            config_key = ("example.aprs2.net", 14580, "SQ9XYZ-10", "12345")
            service._writer = ExistingWriter()  # type: ignore[assignment]
            service._connected_config = config_key
            service._connected_rx_signature = (interface_id, "m/20")

            self.assertTrue(
                service._connection_needs_reconnect(
                    config_key=config_key,
                    desired_rx_signature=(interface_id, "r/52.23/21.01/50"),
                )
            )

            execute("UPDATE modems SET enabled = 0 WHERE id = ?", (interface_id,))
            self.assertTrue(aprsis_connection_required())
            self.assertFalse(
                service._connection_needs_reconnect(
                    config_key=config_key,
                    desired_rx_signature=None,
                )
            )


if __name__ == "__main__":
    unittest.main()
