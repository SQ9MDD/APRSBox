import contextlib
import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.services import content
from app.services.content import monitoring_public_snapshot, update_station_settings

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        content._STATION_SNAPSHOT_CACHE.clear()
        try:
            init_db()
            yield database_path
        finally:
            content._STATION_SNAPSHOT_CACHE.clear()
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def insert_modem(*, name: str, enabled: int) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, baud_rate, enabled, tx_blocked,
            expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
            notes, created_at, updated_at
        )
        VALUES (?, 'TCP', '2m', ?, NULL, ?, 0, 1, '127.0.0.1', 8010, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, f"127.0.0.1:{9000 + enabled}", enabled),
    )
    result = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert result is not None
    return int(result["id"])


def station_payload(interface_id: int) -> dict[str, str]:
    return {
        "callsign": "SQ9MDD",
        "ssid": "10",
        "beacon_interface_id": str(interface_id),
        "beacon_comment": "Test",
        "beacon_interval_minutes": "30",
        "beacon_path": "WIDE2-1",
        "status_enabled": "1",
        "status_text": "Online",
        "status_interval_minutes": "30",
        "latitude": "52.2297",
        "longitude": "21.0122",
        "symbol_table": "/",
        "symbol_code": ">",
        "default_units": "metric",
        "tx_enabled": "1",
    }


class PublicMonitoringSnapshotTests(unittest.TestCase):
    def test_snapshot_includes_tnc_wx_station_and_hourly_stats(self) -> None:
        with temporary_database():
            primary_modem_id = insert_modem(name="Primary TNC", enabled=1)
            insert_modem(name="Disabled TNC", enabled=0)
            update_station_settings(station_payload(primary_modem_id))

            now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            execute(
                """
                INSERT INTO traffic_runtime_interfaces(
                    modem_id, modem_name, modem_endpoint, band, status, status_detail,
                    expose_port_enabled, expose_bind_address, expose_port, expose_active_clients,
                    last_error, updated_at
                )
                VALUES (?, 'Primary TNC', '127.0.0.1:9001', '2m', 'connected', 'Connected.', 1, '127.0.0.1', 8010, 2, '', ?)
                """,
                (primary_modem_id, now_utc),
            )
            execute(
                """
                INSERT INTO igate_rules(name, is_enabled, direction, policy_text, updated_at)
                VALUES ('iGate RF->IS', 1, 'rf_to_is', 'allow', ?)
                """,
                (now_utc,),
            )
            execute(
                """
                INSERT INTO digi_rules(name, is_enabled, source_match, destination_match, path_rewrite, updated_at)
                VALUES ('DIGI WIDE', 1, '', '', 'WIDE2-1', ?)
                """,
                (now_utc,),
            )
            execute(
                """
                INSERT INTO traffic_frames(source, interface_id, direction, band, format, line, port, command, length, hex, created_at)
                VALUES ('rf', ?, 'RX', '2m', 'TNC2', 'SP8ABC-9>APDW16:!5218.37N\\02104.87E>Test', '', '', 39, '', ?)
                """,
                (primary_modem_id, now_utc),
            )
            execute(
                """
                INSERT INTO band_condition_activity_buckets(
                    bucket_start_utc, band, total_frames, total_unique_stations,
                    mobile_frames, mobile_unique_stations, fixed_frames, fixed_unique_stations, baseline_processed_at
                )
                VALUES (?, '2m', 120, 22, 30, 8, 90, 14, NULL)
                """,
                (now_utc,),
            )
            execute(
                """
                INSERT INTO band_condition_activity_buckets(
                    bucket_start_utc, band, total_frames, total_unique_stations,
                    mobile_frames, mobile_unique_stations, fixed_frames, fixed_unique_stations, baseline_processed_at
                )
                VALUES (?, '70cm', 20, 5, 10, 3, 10, 2, NULL)
                """,
                (now_utc,),
            )

            snapshot = monitoring_public_snapshot()

            self.assertEqual(snapshot["station"]["full_callsign"], "SQ9MDD-10")
            self.assertTrue(snapshot["station"]["tx_enabled"])

            self.assertEqual(snapshot["tnc"]["total"], 2)
            self.assertEqual(snapshot["tnc"]["enabled"], 1)
            self.assertEqual(snapshot["tnc"]["runtime_connected"], 1)
            self.assertEqual(len(snapshot["tnc"]["items"]), 2)

            self.assertEqual(snapshot["services"]["digi"]["enabled_rules"], 1)
            self.assertEqual(snapshot["services"]["igate"]["enabled_rules"], 1)
            self.assertEqual(snapshot["services"]["traffic_monitor"]["status"], "connected")

            self.assertEqual(snapshot["stats"]["frames_last_hour"]["total_frames"], 140)
            self.assertEqual(snapshot["stats"]["frames_last_hour"]["mobile_frames"], 40)
            self.assertEqual(snapshot["stats"]["frames_last_hour"]["fixed_frames"], 100)
            self.assertGreaterEqual(snapshot["stats"]["stations"]["total"], 1)

            self.assertIn("configured", snapshot["wx"])
            self.assertIn("mapping_status", snapshot["wx"])

    def test_public_monitoring_endpoint_does_not_require_session(self) -> None:
        if not FASTAPI_AVAILABLE:
            self.skipTest("fastapi is not installed in this environment")
        with temporary_database():
            from fastapi.testclient import TestClient

            from app.main import app

            client = TestClient(app)
            response = client.get("/api/public/monitoring")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn("generated_at", payload)
            self.assertIn("tnc", payload)


if __name__ == "__main__":
    unittest.main()
