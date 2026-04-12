import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_one, get_app_setting, init_db, set_app_setting
from app.services.beacon_scheduler import (
    BeaconSchedulerService,
    LAST_SCHEDULED_BEACON_AT_KEY,
    LAST_SCHEDULED_STATUS_AT_KEY,
)
from app.services.content import get_station_settings, safe_update_station_settings, update_station_settings
from app.services.outbound import build_beacon_tnc2, build_status_tnc2, claim_next_outbound_job, get_outbound_job
from app.services.outbound_runtime import OutboundService


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


def insert_modem(*, name: str = "Test TNC", device_path: str = "127.0.0.1:8001") -> int:
    execute(
        """
        INSERT INTO modems(name, modem_type, band, device_path, enabled, notes, created_at, updated_at)
        VALUES (?, 'TCP', '2m', ?, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, device_path),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


def station_payload(interface_id: int, *, tx_enabled: str | None) -> dict[str, str]:
    payload = {
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
    }
    if tx_enabled is not None:
        payload["tx_enabled"] = tx_enabled
    return payload


class StationSettingsAndSchedulerTests(unittest.TestCase):
    def test_saved_and_loaded_station_state_matches_checkbox_flag(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id, tx_enabled="1"))

            station_settings = get_station_settings()
            self.assertEqual(station_settings["tx_enabled"], 1)
            self.assertEqual(station_settings["beacon_interval_minutes"], 15)
            self.assertEqual(station_settings["beacon_interface_id"], interface_id)
            self.assertEqual(station_settings["status_enabled"], 0)
            self.assertEqual(station_settings["status_text"], "Station online")
            self.assertEqual(station_settings["status_interval_minutes"], 30)

            template_source = Path("app/templates/station.html").read_text(encoding="utf-8")
            self.assertIn('name="tx_enabled" value="1" {% if station.tx_enabled %}checked{% endif %}', template_source)
            self.assertIn("Enable automatic beacon transmission every selected interval", template_source)
            self.assertIn('name="status_enabled" value="1" {% if station.status_enabled %}checked{% endif %}', template_source)
            self.assertIn("Status is sent as a separate APRS frame", template_source)
            self.assertIn('id="station-phg-gain-input"', template_source)
            self.assertIn('id="station-phg-direction-input"', template_source)

    def test_status_validation_rejects_enabled_empty_text(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["status_enabled"] = "1"
            payload["status_text"] = "   "
            success, error = safe_update_station_settings(payload)
            self.assertFalse(success)
            self.assertEqual(error, "Status text is required when APRS Status is enabled.")

    def test_beacon_comment_length_is_enforced(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["beacon_comment"] = "A" * 44
            success, error = safe_update_station_settings(payload)
            self.assertFalse(success)
            self.assertEqual(error, "Beacon comment must be 43 printable ASCII characters or fewer.")

    def test_beacon_comment_ascii_is_enforced(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["beacon_comment"] = "Bad ł"
            success, error = safe_update_station_settings(payload)
            self.assertFalse(success)
            self.assertEqual(error, "Beacon comment may contain only printable ASCII characters.")

    def test_status_text_length_is_enforced(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["status_enabled"] = "1"
            payload["status_text"] = "X" * 63
            success, error = safe_update_station_settings(payload)
            self.assertFalse(success)
            self.assertEqual(error, "Status text must be 62 printable ASCII characters or fewer.")

    def test_status_text_ascii_is_enforced(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["status_enabled"] = "1"
            payload["status_text"] = "Ťext"
            success, error = safe_update_station_settings(payload)
            self.assertFalse(success)
            self.assertEqual(error, "Status text may contain only printable ASCII characters.")

    def test_scheduler_state_persists_across_reload_and_restart_boundaries(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id, tx_enabled="1"))

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            job_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'beacon'")
            assert job_row is not None
            self.assertEqual(int(job_row["total"]), 1)
            self.assertIsNotNone(get_app_setting(LAST_SCHEDULED_BEACON_AT_KEY))
            self.assertIsNone(get_app_setting(LAST_SCHEDULED_STATUS_AT_KEY))

            reloaded = get_station_settings()
            self.assertEqual(reloaded["tx_enabled"], 1)
            self.assertEqual(reloaded["beacon_interval_minutes"], 15)

            init_db()
            restarted = BeaconSchedulerService()
            restarted._tick()
            job_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'beacon'")
            assert job_row is not None
            self.assertEqual(int(job_row["total"]), 1)

            execute("UPDATE outbound_jobs SET status = 'sent', updated_at = '2026-01-01T00:00:01+00:00' WHERE kind = 'beacon'")
            set_app_setting(LAST_SCHEDULED_BEACON_AT_KEY, "2000-01-01T00:00:00+00:00")
            restarted._tick()
            job_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'beacon'")
            assert job_row is not None
            self.assertEqual(int(job_row["total"]), 2)

    def test_scheduler_enqueues_status_independently_from_beacon(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["status_enabled"] = "1"
            payload["status_interval_minutes"] = "15"
            update_station_settings(payload)

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            beacon_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'beacon'")
            status_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'status'")
            assert beacon_row is not None
            assert status_row is not None
            self.assertEqual(int(beacon_row["total"]), 1)
            self.assertEqual(int(status_row["total"]), 1)
            self.assertIsNotNone(get_app_setting(LAST_SCHEDULED_BEACON_AT_KEY))
            self.assertIsNotNone(get_app_setting(LAST_SCHEDULED_STATUS_AT_KEY))


class StationBeaconRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_beacon_flows_from_saved_flag_to_runtime_send(self) -> None:
        with temporary_database():
            interface_id = insert_modem(device_path="127.0.0.1:9001")
            update_station_settings(station_payload(interface_id, tx_enabled="1"))

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            job = claim_next_outbound_job()
            assert job is not None

            written_frames: list[bytes] = []

            class FakeWriter:
                def write(self, data: bytes) -> None:
                    written_frames.append(data)

                async def drain(self) -> None:
                    return None

                def close(self) -> None:
                    return None

                async def wait_closed(self) -> None:
                    return None

            async def fake_open_connection(host: str, port: int):
                self.assertEqual(host, "127.0.0.1")
                self.assertEqual(port, 9001)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            job_row = fetch_one(
                "SELECT id, status, payload_json FROM outbound_jobs WHERE kind = 'beacon' ORDER BY id DESC LIMIT 1"
            )
            assert job_row is not None
            self.assertEqual(job_row["status"], "sent")

            payload = json.loads(job_row["payload_json"])
            self.assertEqual(payload["trigger"], "scheduled")

            runtime_job = get_outbound_job(int(job_row["id"]))
            assert runtime_job is not None
            expected_line = build_beacon_tnc2(runtime_job["payload"])
            self.assertTrue(written_frames)
            self.assertGreater(len(written_frames[0]), 0)

            traffic_row = fetch_one("SELECT line FROM traffic_frames ORDER BY id DESC LIMIT 1")
            assert traffic_row is not None
            self.assertEqual(traffic_row["line"], expected_line)

    async def test_scheduled_status_flows_from_saved_flag_to_runtime_send(self) -> None:
        with temporary_database():
            interface_id = insert_modem(device_path="127.0.0.1:9002")
            payload = station_payload(interface_id, tx_enabled="1")
            payload["status_enabled"] = "1"
            payload["status_interval_minutes"] = "15"
            update_station_settings(payload)

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            execute("UPDATE outbound_jobs SET status = 'sent', updated_at = '2026-01-01T00:00:01+00:00' WHERE kind = 'beacon'")
            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "status")

            written_frames: list[bytes] = []

            class FakeWriter:
                def write(self, data: bytes) -> None:
                    written_frames.append(data)

                async def drain(self) -> None:
                    return None

                def close(self) -> None:
                    return None

                async def wait_closed(self) -> None:
                    return None

            async def fake_open_connection(host: str, port: int):
                self.assertEqual(host, "127.0.0.1")
                self.assertEqual(port, 9002)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            job_row = fetch_one(
                "SELECT id, status, payload_json FROM outbound_jobs WHERE kind = 'status' ORDER BY id DESC LIMIT 1"
            )
            assert job_row is not None
            self.assertEqual(job_row["status"], "sent")

            runtime_job = get_outbound_job(int(job_row["id"]))
            assert runtime_job is not None
            expected_line = build_status_tnc2(runtime_job["payload"])
            self.assertTrue(written_frames)
            self.assertGreater(len(written_frames[0]), 0)

            traffic_row = fetch_one("SELECT line FROM traffic_frames ORDER BY id DESC LIMIT 1")
            assert traffic_row is not None
            self.assertEqual(traffic_row["line"], expected_line)

    async def test_tx_blocked_interface_skips_runtime_transmit_and_logs_diagnostic(self) -> None:
        with temporary_database():
            interface_id = insert_modem(device_path="127.0.0.1:9003")
            execute("UPDATE modems SET tx_blocked = 1 WHERE id = ?", (interface_id,))
            update_station_settings(station_payload(interface_id, tx_enabled="1"))

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "beacon")

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection") as open_connection_mock:
                await outbound_service._process_job(job)
                open_connection_mock.assert_not_called()

            job_row = fetch_one("SELECT status FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
            assert job_row is not None
            self.assertEqual(job_row["status"], "sent")

            tx_row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM traffic_frames
                WHERE direction = 'tx'
                  AND command = 'TX-SKIP'
                """
            )
            assert tx_row is not None
            self.assertEqual(int(tx_row["total"]), 1)

            log_row = fetch_one(
                """
                SELECT message
                FROM event_logs
                WHERE category = 'outbound'
                  AND level = 'WARNING'
                  AND message LIKE '%TX is blocked on interface%'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            self.assertIsNotNone(log_row)

    async def test_disabled_interface_skips_runtime_transmit_and_logs_diagnostic(self) -> None:
        with temporary_database():
            interface_id = insert_modem(device_path="127.0.0.1:9004")
            execute("UPDATE modems SET enabled = 0 WHERE id = ?", (interface_id,))
            update_station_settings(station_payload(interface_id, tx_enabled="1"))

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "beacon")

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection") as open_connection_mock:
                await outbound_service._process_job(job)
                open_connection_mock.assert_not_called()

            job_row = fetch_one("SELECT status, last_error FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
            assert job_row is not None
            self.assertEqual(job_row["status"], "sent")
            self.assertIn("TX skipped:", str(job_row["last_error"] or ""))

            tx_row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM traffic_frames
                WHERE direction = 'tx'
                  AND command = 'TX-SKIP'
                """
            )
            assert tx_row is not None
            self.assertEqual(int(tx_row["total"]), 1)

            log_row = fetch_one(
                """
                SELECT message
                FROM event_logs
                WHERE category = 'outbound'
                  AND level = 'WARNING'
                  AND message LIKE '%is disabled%'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            self.assertIsNotNone(log_row)


if __name__ == "__main__":
    unittest.main()
