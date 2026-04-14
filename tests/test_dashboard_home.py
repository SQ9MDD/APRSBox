import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.services.content import dashboard_home_data, update_station_settings


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


def insert_modem(*, name: str, enabled: int = 1, tx_blocked: int = 0) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, baud_rate, enabled, tx_blocked,
            expose_port_enabled, expose_bind_address, expose_port, expose_whitelist, notes, created_at, updated_at
        )
        VALUES (?, 'TCP', '2m', '127.0.0.1:8001', NULL, ?, ?, 0, '0.0.0.0', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, enabled, tx_blocked),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


def insert_digi_flow(
    *,
    name: str,
    source_ref: str,
    target_kind: str,
    target_ref: str,
    enabled: int = 1,
) -> None:
    execute(
        """
        INSERT INTO digi_flows(
            name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
        )
        VALUES (?, '', 'receiver_rf', ?, ?, ?, ?, 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, source_ref, target_kind, target_ref, enabled),
    )


def station_payload(interface_id: int) -> dict[str, str]:
    return {
        "callsign": "SQ9MDD",
        "ssid": "4",
        "beacon_interface_id": str(interface_id),
        "beacon_comment": "Test",
        "beacon_interval_minutes": "30",
        "beacon_path": "WIDE2-1",
        "status_enabled": "1",
        "status_text": "Station online",
        "status_interval_minutes": "30",
        "latitude": "52.2297",
        "longitude": "21.0122",
        "symbol_table": "/",
        "symbol_code": ">",
        "default_units": "metric",
        "tx_enabled": "1",
    }


class DashboardHomeTests(unittest.TestCase):
    def test_dashboard_exposes_compact_station_readiness_lists(self) -> None:
        with temporary_database():
            interface_id = insert_modem(name="Main TNC", enabled=1, tx_blocked=0)
            insert_modem(name="Backup TNC", enabled=0, tx_blocked=0)
            update_station_settings(station_payload(interface_id))

            view = dashboard_home_data()
            checks = {item["label"]: item for item in view["checks"]}

            self.assertEqual(checks["Main callsign"]["value"], "SQ9MDD-4")
            self.assertEqual(checks["WX callsign"]["value"], "SQ9MDD")
            self.assertNotIn("Beacon interface", checks)
            self.assertNotIn("TX Block", checks)
            self.assertNotIn("TX Enabled", checks)
            self.assertNotIn("APRS Status enabled", checks)

            interfaces = {entry["name"]: entry["status"] for entry in checks["Active interfaces"].get("entries") or []}
            self.assertEqual(interfaces["Main TNC"], "Unknown")
            self.assertEqual(interfaces["Backup TNC"], "Disabled")

            services = {entry["name"]: entry["status"] for entry in checks["Enabled services"].get("entries") or []}
            self.assertEqual(services["Beacon enabled"], "Enabled")
            self.assertEqual(services["Status enabled"], "Enabled")
            self.assertEqual(services["WX enabled"], "Disabled")
            self.assertEqual(services["Digi routine"], "Disabled")
            self.assertEqual(services["iGate enabled"], "Disabled")
            service_names = [entry["name"] for entry in checks["Enabled services"].get("entries") or []]
            self.assertLess(service_names.index("Digi routine"), service_names.index("iGate enabled"))

    def test_dashboard_does_not_expose_traffic_monitor_check(self) -> None:
        with temporary_database():
            interface_id = insert_modem(name="Error TNC", enabled=1, tx_blocked=0)
            update_station_settings(station_payload(interface_id))

            view = dashboard_home_data()
            checks = {item["label"]: item for item in view["checks"]}
            self.assertNotIn("Traffic Monitor", checks)

    def test_dashboard_exposes_last_station_tx_time_in_stats(self) -> None:
        with temporary_database():
            interface_id = insert_modem(name="TX TNC", enabled=1, tx_blocked=0)
            update_station_settings(station_payload(interface_id))
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, aprs_message_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES (
                    'beacon',
                    ?,
                    NULL,
                    '{"callsign":"SQ9MDD","ssid":"4","latitude":52.2297,"longitude":21.0122,"symbol_table":"/","symbol_code":">","beacon_comment":"Test","beacon_path":"WIDE2-1","trigger":"manual"}',
                    'sent',
                    '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:01+00:00',
                    '2026-01-01T00:00:01+00:00',
                    '2026-01-01T00:00:02+00:00',
                    1,
                    'TX skipped: TX is blocked on interface TX TNC.',
                    '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:02+00:00'
                )
                """,
                (interface_id,),
            )

            view = dashboard_home_data()
            stats = {item["label"]: item for item in view["stats"]}

            self.assertNotEqual(stats["Last station TX"]["value"], "Never")

    def test_dashboard_digi_routine_ignores_black_hole_and_checks_tnc_to_tnc(self) -> None:
        with temporary_database():
            interface_id = insert_modem(name="Main TNC", enabled=1, tx_blocked=0)
            insert_modem(name="Relay TNC", enabled=1, tx_blocked=0)
            update_station_settings(station_payload(interface_id))

            insert_digi_flow(
                name="Blackhole flow",
                source_ref="Main TNC",
                target_kind="action_log",
                target_ref="log-only",
                enabled=1,
            )
            view_with_blackhole = dashboard_home_data()
            checks_blackhole = {item["label"]: item for item in view_with_blackhole["checks"]}
            services_blackhole = {entry["name"]: entry["status"] for entry in checks_blackhole["Enabled services"].get("entries") or []}
            self.assertEqual(services_blackhole["Digi routine"], "Disabled")

            insert_digi_flow(
                name="RF relay",
                source_ref="Main TNC",
                target_kind="tx_rf",
                target_ref="Relay TNC",
                enabled=1,
            )
            view_with_rf = dashboard_home_data()
            checks_rf = {item["label"]: item for item in view_with_rf["checks"]}
            services_rf = {entry["name"]: entry["status"] for entry in checks_rf["Enabled services"].get("entries") or []}
            self.assertEqual(services_rf["Digi routine"], "Enabled")


if __name__ == "__main__":
    unittest.main()
