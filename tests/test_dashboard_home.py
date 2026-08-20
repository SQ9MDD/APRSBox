import contextlib
from datetime import datetime, timedelta, timezone
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_one, init_db
from app.services.content import dashboard_home_data, dashboard_traffic_summary, update_station_settings


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


def insert_modem(*, name: str, enabled: int = 1, tx_blocked: int = 0, modem_type: str = "TCP") -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, baud_rate, enabled, tx_blocked,
            expose_port_enabled, expose_bind_address, expose_port, expose_whitelist, notes, created_at, updated_at
        )
        VALUES (?, ?, '2m', '127.0.0.1:8001', NULL, ?, ?, 0, '0.0.0.0', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, modem_type, enabled, tx_blocked),
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
    source_kind: str = "receiver_rf",
) -> None:
    execute(
        """
        INSERT INTO digi_flows(
            name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
        )
        VALUES (?, '', ?, ?, ?, ?, ?, 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name, source_kind, source_ref, target_kind, target_ref, enabled),
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
    def test_dashboard_kpis_use_last_24_hours_only(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(microsecond=0)
            recent_at = (now_utc - timedelta(hours=2)).isoformat()
            old_at = (now_utc - timedelta(hours=25)).isoformat()
            for source_kind, line, created_at in (
                ("rf", "SP5ABC-1>APRS:!5212.00N/02057.00E-Test", recent_at),
                ("rf", "SP5OLD-1>APRS:!5212.00N/02057.00E-Old", old_at),
                ("aprsis", "SP5NET-1>APRS:!5212.00N/02057.00E-Net", recent_at),
            ):
                execute(
                    """
                    INSERT INTO traffic_frames(
                        source, source_kind, interface_id, direction, band, format,
                        line, port, command, length, hex, created_at
                    )
                    VALUES ('test', ?, NULL, 'RX', '2m', 'TNC2', ?, NULL, NULL, ?, NULL, ?)
                    """,
                    (source_kind, line, len(line), created_at),
                )

            traffic = dashboard_traffic_summary(
                heard_snapshots=[
                    {"last_heard_rf_at": recent_at},
                    {"last_heard_rf_at": old_at},
                ]
            )

            self.assertEqual(traffic["window_hours"], 24)
            self.assertEqual(traffic["decoded_aprs"], 1)
            self.assertEqual(traffic["heard_stations"], 1)

    def test_dashboard_exposes_activity_chart_series(self) -> None:
        with temporary_database():
            interface_id = insert_modem(name="Chart TNC", enabled=1, tx_blocked=0)
            update_station_settings(station_payload(interface_id))

            view = dashboard_home_data()
            chart = view.get("activity_chart") or {}
            series = chart.get("series") or {}
            labels = chart.get("labels") or []

            self.assertEqual(chart.get("bucket_minutes"), 5)
            self.assertEqual(chart.get("window_minutes"), 60)
            self.assertEqual(len(labels), 12)
            self.assertEqual(len(series.get("total") or []), len(labels))
            self.assertEqual(len(series.get("rx") or []), len(labels))
            self.assertEqual(len(series.get("tx") or []), len(labels))
            self.assertEqual(sum(series.get("total") or []), int((chart.get("totals") or {}).get("total", 0)))

    def test_dashboard_uses_initial_activity_range_kpis(self) -> None:
        with temporary_database():
            view = dashboard_home_data(
                dashboard_activity={
                    "kpis": {
                        "heard_stations": 17,
                        "aprs_frames": 1234,
                    }
                }
            )
            stats = {item["label"]: item for item in view["stats"]}

            self.assertEqual(stats["Heard stations"]["value"], "17")
            self.assertEqual(stats["APRS frames"]["value"], "1234")

    def test_dashboard_reuses_station_and_activity_projections(self) -> None:
        with temporary_database():
            activity = {
                "range_minutes": 60,
                "output_bucket_minutes": 5,
                "window_start_utc": "2026-01-01T00:00:00+00:00",
                "window_end_utc": "2026-01-01T01:00:00+00:00",
                "labels": ["00:00", "00:05"],
                "series": {
                    "rx_total": [3, 4],
                    "tx_total": [1, 2],
                    "digipeated_total": [0, 1],
                    "mobile_total": [1, 0],
                    "messages_total": [0, 1],
                    "queries_total": [0, 0],
                },
                "kpis": {"heard_stations": 1, "aprs_frames": 7},
            }
            snapshot = {
                "display_callsign": "SP5ABC-1",
                "last_heard_at": "2026-01-01T00:05:00+00:00",
                "last_heard_rf_at": "2026-01-01T00:05:00+00:00",
                "origin": "heard",
                "entity_class": "fixed",
                "frame_type": "P",
                "symbol": "/>",
            }
            with (
                patch("app.services.map_station_state.read_map_station_rf_snapshots", return_value=[snapshot]),
                patch("app.services.content.get_rf_heard_station_snapshots", side_effect=AssertionError("raw rebuild")),
                patch("app.services.content.dashboard_activity_series", side_effect=AssertionError("raw chart")),
            ):
                view = dashboard_home_data(dashboard_activity=activity)

            chart = view["activity_chart"]
            self.assertEqual(chart["series"]["total"], [4, 6])
            self.assertEqual(chart["series"]["repeated_tx"], [0, 1])
            self.assertEqual(chart["totals"]["rx"], 7)
            self.assertEqual(view["last_rf_activity"][0]["value"], "SP5ABC-1")

    def test_dashboard_exposes_compact_station_readiness_lists(self) -> None:
        with temporary_database():
            interface_id = insert_modem(name="Main TNC", enabled=1, tx_blocked=0)
            insert_modem(name="Backup TNC", enabled=0, tx_blocked=0)
            update_station_settings(station_payload(interface_id))

            view = dashboard_home_data()
            checks = {item["label"]: item for item in view["checks"]}

            self.assertIn("Runtime readiness", checks)
            self.assertIn("Configuration checklist", checks)
            self.assertIn("Enabled services", checks)
            self.assertEqual(view.get("interface_summary"), "1 enabled / 1 disabled")

            config_entries = {entry["name"]: entry["status"] for entry in checks["Configuration checklist"].get("entries") or []}
            self.assertEqual(config_entries["Main callsign"], "Configured")
            self.assertEqual(config_entries["WX callsign"], "Configured")
            self.assertEqual(config_entries["Location"], "Configured")

            interfaces = {entry["name"]: entry["status"] for entry in view.get("interface_entries") or []}
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
            runtime_entries = {entry["name"]: entry for entry in checks["Runtime readiness"].get("entries") or []}
            self.assertEqual(runtime_entries["TX queue"]["status_key"], "Idle")
            self.assertEqual(runtime_entries["TX queue"]["status_params"], {})

            readiness_overview = {
                entry["label"]: entry for entry in view["station_readiness"]["overview"]
            }
            self.assertEqual(readiness_overview["Radio interfaces"]["tone"], "partial")

            execute("UPDATE modems SET enabled = 0")
            no_active_overview = {
                entry["label"]: entry for entry in dashboard_home_data()["station_readiness"]["overview"]
            }
            self.assertEqual(no_active_overview["Radio interfaces"]["tone"], "error")

    def test_dashboard_station_readiness_exposes_flow_matrix_per_radio_interface(self) -> None:
        with temporary_database():
            main_id = insert_modem(name="Main TNC")
            insert_modem(name="Backup TNC")
            insert_modem(name="APRS-IS", modem_type="APRSIS")
            update_station_settings(station_payload(main_id))

            insert_digi_flow(
                name="Local TX uplink",
                source_kind="receiver_local_tx",
                source_ref="local_tx",
                target_kind="tx_aprsis",
                target_ref="aprsis",
            )
            insert_digi_flow(name="Main uplink", source_ref="Main TNC", target_kind="tx_aprsis", target_ref="aprsis")
            insert_digi_flow(name="Main repeat", source_ref="Main TNC", target_kind="tx_rf", target_ref="Main TNC")
            insert_digi_flow(name="Main crossband", source_ref="Main TNC", target_kind="tx_rf", target_ref="Backup TNC")
            insert_digi_flow(
                name="APRS-IS to main",
                source_kind="receiver_aprsis",
                source_ref="APRS-IS",
                target_kind="tx_rf",
                target_ref="Main TNC",
            )

            readiness = dashboard_home_data()["station_readiness"]
            overview = {entry["label"]: entry for entry in readiness["overview"]}
            interfaces = {entry["name"]: entry for entry in readiness["interfaces"]}

            self.assertEqual(overview["Local TX → APRS-IS"]["tone"], "ok")
            self.assertEqual(overview["Radio interfaces"]["status_params"], {"active": 2, "total": 2})
            self.assertEqual(overview["Radio interfaces"]["tone"], "ok")
            self.assertEqual(overview["Beacon defined"]["tone"], "ok")
            self.assertTrue(interfaces["Main TNC"]["to_aprsis"])
            self.assertTrue(interfaces["Main TNC"]["from_aprsis"])
            self.assertEqual(interfaces["Main TNC"]["rf_target_count"], 2)
            self.assertEqual(interfaces["Main TNC"]["rf_target_total"], 2)
            self.assertTrue(interfaces["Main TNC"]["rf_ready"])
            self.assertFalse(interfaces["Backup TNC"]["to_aprsis"])
            self.assertFalse(interfaces["Backup TNC"]["from_aprsis"])
            self.assertFalse(interfaces["Backup TNC"]["rf_ready"])

    def test_dashboard_template_uses_visual_first_pack(self) -> None:
        template = Path("app/templates/dashboard.html").read_text(encoding="utf-8")
        stylesheet = Path("app/static/css/style.css").read_text(encoding="utf-8")

        self.assertIn("dashboard-v2-radio-visual", template)
        self.assertIn("dashboard-v2-link-statuses", template)
        self.assertIn("dashboard-v2-kpi-icon", template)
        self.assertIn("dashboard-v2-kpi-meta", template)
        self.assertIn("dashboard-kpi-heard-stations", template)
        self.assertIn("dashboard-kpi-aprs-frames", template)
        self.assertIn("rawPayload?.kpis?.heard_stations", template)
        self.assertIn('`${rangePrefix}: ${rangeLabel}`', template)
        self.assertIn("dashboard-v2-network-grid", template)
        self.assertNotIn('t("Network diagnostics")', template)
        self.assertIn("network_diagnostics.web_ui_url", template)
        self.assertIn("network_diagnostics.ipv6 or", template)
        self.assertIn("{% if dashboard_bands %}", template)
        self.assertIn("dashboard-v2-band-indicators", template)
        self.assertIn("dashboard-v2-band-indicator-{{ item.diagnosis_tone }}", template)
        self.assertIn("{% for level in [5, 4, 3, 2, 1, 0] %}", template)
        self.assertIn('href="{{ request.scope.root_path }}/band-condition"', template)
        self.assertNotIn("dashboard_home.band_updated_at", template)
        self.assertNotIn("Current estimate for", template)
        self.assertNotIn("dashboard-v2-band-meter-current", template)
        self.assertIn("dashboard-v2-readiness-matrix", template)
        self.assertNotIn("dashboard-v2-readiness-score", template)
        self.assertNotIn("station_readiness.ready_count", template)
        self.assertIn('data-help-page="application/dashboard_readiness"', template)
        self.assertIn('class="help-icon-button dashboard-v2-readiness-help-button"', template)
        self.assertNotIn('class="help-icon-button page-help-button"', template)
        self.assertIn('{% include "partials/help_modal.html" %}', template)
        self.assertIn('static/js/help-viewer.js', template)
        self.assertNotIn('dashboard-subtle-link', template)
        self.assertIn('const helpViewerModal = document.getElementById("help-viewer-modal")', template)
        self.assertIn('helpViewerObserver.observe(helpViewerModal', template)
        self.assertIn('window.clearTimeout(dashboardRefreshTimer)', template)
        self.assertNotIn('const dashboardRefreshTimer = window.setInterval', template)
        self.assertNotIn("dashboard-v2-events-panel", template)
        self.assertNotIn("dashboard-v2-summary-panel", template)
        self.assertNotIn("Recent important events", template)
        self.assertIn("height: calc(100dvh - 1.78rem)", stylesheet)
        self.assertIn("Open detailed statistics", template)
        self.assertIn("point: { radius: 0", template)
        self.assertNotIn("dashboard_home.hero.title", template)
        self.assertNotIn('{{ t("Last RF activity") }}: {{ t(station.last_rf) }}', template)
        self.assertNotIn("last_rf=", template)
        self.assertIn(".dashboard-v2-station-panel::before", stylesheet)
        self.assertIn("min-height: 7.6rem", stylesheet)
        self.assertIn(".dashboard-v2-network-grid", stylesheet)
        self.assertIn(".dashboard-v2-top-grid.has-band-indicators", stylesheet)
        self.assertIn(".dashboard-v2-top-grid.has-band-indicators {\n        grid-template-columns: 1fr;", stylesheet)
        self.assertIn(".dashboard-v2-band-step.is-active", stylesheet)
        self.assertIn(".dashboard-v2-event-item:not(:last-child)", stylesheet)

    def test_dashboard_does_not_expose_traffic_monitor_check(self) -> None:
        with temporary_database():
            interface_id = insert_modem(name="Error TNC", enabled=1, tx_blocked=0)
            update_station_settings(station_payload(interface_id))

            view = dashboard_home_data()
            checks = {item["label"]: item for item in view["checks"]}
            self.assertNotIn("Traffic Monitor", checks)

    def test_dashboard_exposes_last_rf_tx_time_in_stats(self) -> None:
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

            self.assertNotEqual(stats["Last RF TX"]["value"], "No RF TX yet")

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
