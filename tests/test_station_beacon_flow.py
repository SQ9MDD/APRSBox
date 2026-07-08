import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_all, fetch_one, get_app_setting, init_db, set_app_setting
from app.services.beacon_scheduler import (
    BeaconSchedulerService,
    LAST_SCHEDULED_BEACON_AT_KEY,
    LAST_SCHEDULED_STATUS_AT_KEY,
)
from app.services.content import get_station_settings, safe_update_station_settings, update_station_settings
from app.services.outbound import build_beacon_tnc2, build_status_tnc2, claim_next_outbound_job, get_outbound_job
from app.services.outbound_runtime import OutboundService
from app.services.tx_scope import ALL_ACTIVE_INTERFACE_OPTION_VALUE, INTERNAL_TX_INTERFACE_OPTION_VALUE, TX_SCOPE_ALL_ACTIVE


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


def station_payload(
    interface_id: int,
    *,
    tx_enabled: str | None,
    beacon_interval_minutes: str = "15",
    beacon_interval_mode: str | None = None,
    symbol_table: str = "/",
    symbol_code: str = ">",
    symbol_overlay: str = "",
) -> dict[str, str]:
    payload = {
        "callsign": "sq9xyz",
        "ssid": "9",
        "beacon_interface_id": str(interface_id),
        "beacon_comment": "Test beacon",
        "beacon_interval_minutes": beacon_interval_minutes,
        "beacon_path": "WIDE2-2",
        "status_text": "Station online",
        "status_interval_minutes": "30",
        "latitude": "52.2297",
        "longitude": "21.0122",
        "symbol_table": symbol_table,
        "symbol_code": symbol_code,
        "symbol_overlay": symbol_overlay,
        "default_units": "metric",
    }
    if beacon_interval_mode is not None:
        payload["beacon_interval_mode"] = beacon_interval_mode
    if tx_enabled is not None:
        payload["tx_enabled"] = tx_enabled
    return payload


def insert_local_tx_aprsis_flow(*, name: str = "Local TX APRSIS") -> int:
    execute(
        """
        INSERT INTO digi_flows(
            name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
        )
        VALUES (?, '', 'receiver_local_tx', 'local_tx', 'tx_aprsis', 'aprsis', 1, 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (name,),
    )
    row = fetch_one("SELECT id FROM digi_flows WHERE name = ?", (name,))
    assert row is not None
    return int(row["id"])


class StationSettingsAndSchedulerTests(unittest.TestCase):
    def test_saved_and_loaded_station_state_matches_checkbox_flag(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(station_payload(interface_id, tx_enabled="1"))

            station_settings = get_station_settings()
            self.assertEqual(station_settings["tx_enabled"], 1)
            self.assertEqual(station_settings["beacon_interval_mode"], "fixed")
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
            self.assertIn('/station/send-status', template_source)
            self.assertIn("Send status", template_source)
            self.assertIn('name="callsign" value="{{ station.callsign }}" maxlength="6" autocapitalize="characters" spellcheck="false" data-force-uppercase="true"', template_source)
            self.assertIn('name="beacon_path" id="station-beacon-path" value="{{ station.beacon_path }}" autocapitalize="characters" spellcheck="false" data-force-uppercase="true"', template_source)
            self.assertIn('name="latitude" value="{{ station.latitude }}" readonly', template_source)
            self.assertIn('name="longitude" value="{{ station.longitude }}" readonly', template_source)
            self.assertIn('id="station-phg-gain-input"', template_source)
            self.assertIn('id="station-phg-direction-input"', template_source)
            self.assertIn('name="symbol_overlay"', template_source)
            self.assertIn('id="station-symbol-overlay"', template_source)

    def test_station_overlay_is_saved_for_alternate_and_cleared_for_primary(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(
                station_payload(
                    interface_id,
                    tx_enabled="1",
                    symbol_table="\\",
                    symbol_code="A",
                    symbol_overlay="7",
                )
            )
            station_settings = get_station_settings()
            self.assertEqual(station_settings["symbol_table"], "\\")
            self.assertEqual(station_settings["symbol_overlay"], "7")

            update_station_settings(
                station_payload(
                    interface_id,
                    tx_enabled="1",
                    symbol_table="/",
                    symbol_code="A",
                    symbol_overlay="9",
                )
            )
            station_settings = get_station_settings()
            self.assertEqual(station_settings["symbol_table"], "/")
            self.assertIsNone(station_settings["symbol_overlay"])

    def test_beacon_frame_uses_station_overlay_for_alternate_table(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            update_station_settings(
                station_payload(
                    interface_id,
                    tx_enabled="1",
                    symbol_table="\\",
                    symbol_code="A",
                    symbol_overlay="2",
                )
            )
            frame = build_beacon_tnc2(get_station_settings())
            self.assertIn("=5213.78N202100.73EA", frame)

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

    def test_callsign_length_is_enforced(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["callsign"] = "SQ9XYZ7"
            success, error = safe_update_station_settings(payload)
            self.assertFalse(success)
            self.assertEqual(error, "Callsign must be 6 printable ASCII characters or fewer.")

    def test_callsign_ascii_is_enforced(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["callsign"] = "SQ9ŁYZ"
            success, error = safe_update_station_settings(payload)
            self.assertFalse(success)
            self.assertEqual(error, "Callsign may contain only printable ASCII characters.")

    def test_callsign_is_normalized_to_uppercase(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["callsign"] = "sq9xyz"
            update_station_settings(payload)
            station_settings = get_station_settings()
            self.assertEqual(station_settings["callsign"], "SQ9XYZ")

    def test_beacon_path_is_normalized_to_uppercase(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["beacon_path"] = "wide2-2"
            update_station_settings(payload)
            station_settings = get_station_settings()
            self.assertEqual(station_settings["beacon_path"], "WIDE2-2")

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

    def test_all_active_scope_enqueues_jobs_for_each_active_tnc(self) -> None:
        with temporary_database():
            first_interface = insert_modem(name="TNC A", device_path="127.0.0.1:9101")
            second_interface = insert_modem(name="TNC B", device_path="127.0.0.1:9102")
            payload = station_payload(first_interface, tx_enabled="1")
            payload["beacon_interface_id"] = ALL_ACTIVE_INTERFACE_OPTION_VALUE
            payload["status_enabled"] = "1"
            payload["status_interval_minutes"] = "15"
            update_station_settings(payload)

            station_settings = get_station_settings()
            self.assertEqual(station_settings.get("beacon_tx_scope"), TX_SCOPE_ALL_ACTIVE)
            self.assertIsNone(station_settings.get("beacon_interface_id"))

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            beacon_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'beacon'")
            status_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'status'")
            assert beacon_row is not None
            assert status_row is not None
            self.assertEqual(int(beacon_row["total"]), 2)
            self.assertEqual(int(status_row["total"]), 2)

            interfaces = fetch_one(
                """
                SELECT COUNT(DISTINCT interface_id) AS total
                FROM outbound_jobs
                WHERE kind IN ('beacon', 'status')
                """
            )
            assert interfaces is not None
            self.assertEqual(int(interfaces["total"]), 2)
            self.assertEqual({first_interface, second_interface}, {
                int(row["interface_id"])
                for row in fetch_all("SELECT interface_id FROM outbound_jobs WHERE kind IN ('beacon', 'status')")
            })

    def test_internal_tx_without_aprsis_flow_is_allowed(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["beacon_interface_id"] = INTERNAL_TX_INTERFACE_OPTION_VALUE
            success, error = safe_update_station_settings(payload)
            self.assertTrue(success, error)

            station_settings = get_station_settings()
            self.assertTrue(bool(station_settings.get("beacon_internal_tx")))
            self.assertIsNone(station_settings.get("beacon_interface_id"))

    def test_internal_tx_scope_enqueues_station_jobs_without_rf_interface(self) -> None:
        with temporary_database():
            insert_local_tx_aprsis_flow()
            payload = station_payload(insert_modem(), tx_enabled="1")
            payload["beacon_interface_id"] = INTERNAL_TX_INTERFACE_OPTION_VALUE
            payload["status_enabled"] = "1"
            payload["status_interval_minutes"] = "15"
            success, error = safe_update_station_settings(payload)
            self.assertTrue(success, error)

            station_settings = get_station_settings()
            self.assertTrue(bool(station_settings.get("beacon_internal_tx")))
            self.assertIsNone(station_settings.get("beacon_interface_id"))

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            rows = fetch_all(
                """
                SELECT kind, interface_id, payload_json
                FROM outbound_jobs
                WHERE kind IN ('beacon', 'status')
                ORDER BY id ASC
                """
            )
            self.assertEqual(len(rows), 2)
            for row in rows:
                self.assertIsNone(row["interface_id"])
                payload_json = str(row["payload_json"] or "{}")
                payload_data = json.loads(payload_json)
                self.assertTrue(bool(payload_data.get("internal_tx_only")))

    def test_scheduler_uses_proportional_path_for_scheduled_beacons(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(
                interface_id,
                tx_enabled="1",
                beacon_interval_minutes="30",
                beacon_interval_mode="proportional",
            )
            payload["beacon_path"] = "WIDE2-2"
            update_station_settings(payload)

            scheduler = BeaconSchedulerService()
            scheduled_paths: list[str] = []

            for _ in range(7):
                set_app_setting(LAST_SCHEDULED_BEACON_AT_KEY, "2000-01-01T00:00:00+00:00")
                scheduler._tick()
                row = fetch_one(
                    """
                    SELECT payload_json
                    FROM outbound_jobs
                    WHERE kind = 'beacon'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
                assert row is not None
                outbound_payload = json.loads(row["payload_json"])
                scheduled_paths.append(str(outbound_payload.get("beacon_path") or ""))
                execute("UPDATE outbound_jobs SET status = 'sent', updated_at = '2026-01-01T00:00:01+00:00' WHERE kind = 'beacon'")

            self.assertEqual(
                scheduled_paths,
                ["", "", "", "WIDE1-1", "", "", "WIDE2-2"],
            )

    def test_payload_with_proportional_interval_value_is_saved_with_mode(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1")
            payload["beacon_interval_minutes"] = "proportional"
            payload["beacon_interval_minutes_fixed"] = "30"
            success, error = safe_update_station_settings(payload)
            self.assertTrue(success, error)
            station_settings = get_station_settings()
            self.assertEqual(station_settings["beacon_interval_mode"], "proportional")
            self.assertEqual(int(station_settings["beacon_interval_minutes"]), 30)

    def test_numeric_interval_from_form_overrides_stale_proportional_mode(self) -> None:
        with temporary_database():
            interface_id = insert_modem()
            payload = station_payload(interface_id, tx_enabled="1", beacon_interval_minutes="60")
            payload["beacon_interval_mode"] = "proportional"
            payload["beacon_interval_minutes_fixed"] = "30"
            success, error = safe_update_station_settings(payload)
            self.assertTrue(success, error)
            station_settings = get_station_settings()
            self.assertEqual(station_settings["beacon_interval_mode"], "fixed")
            self.assertEqual(int(station_settings["beacon_interval_minutes"]), 60)

    def test_station_template_includes_help_viewer(self) -> None:
        template_source = Path("app/templates/station.html").read_text(encoding="utf-8")
        self.assertIn("static/css/help-viewer.css", template_source)
        self.assertIn('data-help-page="application/station"', template_source)
        self.assertIn('class="help-icon-button page-help-button"', template_source)
        self.assertIn('include "partials/help_modal.html"', template_source)
        self.assertIn("static/js/help-viewer.js", template_source)
        for language in ("pl", "en", "es", "de"):
            self.assertTrue(Path(f"help/application/station.{language}.md").exists())

    def test_station_template_uses_chromeless_outer_panel_without_touching_tx_log(self) -> None:
        template_source = Path("app/templates/station.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn('class="panel{% if can_edit %} station-page-panel{% endif %}"', template_source)
        self.assertIn(".station-page-panel {", stylesheet_source)
        self.assertIn(".station-page-panel {\n    padding: 0;", stylesheet_source)
        self.assertIn("border: 0;", stylesheet_source)
        self.assertIn("background: transparent;", stylesheet_source)
        self.assertIn("box-shadow: none;", stylesheet_source)
        self.assertIn(".station-settings-group {", stylesheet_source)
        self.assertIn(".station-settings-group {\n    padding: var(--space-4);\n    border: 1px solid var(--border);\n    border-radius: var(--radius-md);\n    background: var(--panel);", stylesheet_source)
        self.assertIn("gap: var(--space-4);", stylesheet_source)
        self.assertIn('<section class="panel">\n    <div class="panel-body">\n        <div class="panel-header">\n            <div class="panel-header-copy">\n                <h2>{{ t("Station TX Log") }}</h2>', template_source)


class StationBeaconRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_internal_tx_job_is_marked_sent_without_rf_transport(self) -> None:
        with temporary_database():
            insert_local_tx_aprsis_flow()
            payload = station_payload(insert_modem(device_path="127.0.0.1:9000"), tx_enabled="1")
            payload["beacon_interface_id"] = INTERNAL_TX_INTERFACE_OPTION_VALUE
            update_station_settings(payload)

            scheduler = BeaconSchedulerService()
            scheduler._tick()

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "beacon")
            self.assertIsNone(job.get("interface_id"))

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection") as open_connection_mock:
                await outbound_service._process_job(job)
                open_connection_mock.assert_not_called()

            job_row = fetch_one("SELECT status, last_error FROM outbound_jobs WHERE id = ?", (int(job["id"]),))
            assert job_row is not None
            self.assertEqual(job_row["status"], "sent")
            self.assertIn(job_row["last_error"], (None, ""))

            stored = get_outbound_job(int(job["id"]))
            assert stored is not None
            self.assertTrue(bool(stored["payload"].get("internal_tx_only")))

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

    async def test_outbound_start_recovers_stale_processing_beacon_job_and_logs_not_transmitted(self) -> None:
        with temporary_database():
            interface_id = insert_modem(device_path="127.0.0.1:9010")
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES(
                    'beacon', ?, '{"callsign":"SQ2IBK","ssid":"3","beacon_comment":"test"}',
                    'processing', '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:01+00:00', '2026-01-01T00:00:01+00:00', NULL, 1, NULL,
                    '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:01+00:00'
                )
                """,
                (interface_id,),
            )

            outbound_service = OutboundService(poll_interval=5.0)
            await outbound_service.start()
            await outbound_service.stop()

            recovered = fetch_one(
                """
                SELECT status, last_error
                FROM outbound_jobs
                WHERE kind = 'beacon'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            assert recovered is not None
            self.assertEqual(recovered["status"], "failed")
            self.assertIn("Beacon was not transmitted", str(recovered["last_error"] or ""))

            pending_row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM outbound_jobs
                WHERE kind = 'beacon'
                  AND status IN ('queued', 'processing')
                """
            )
            assert pending_row is not None
            self.assertEqual(int(pending_row["total"]), 0)

            log_row = fetch_one(
                """
                SELECT message
                FROM event_logs
                WHERE category = 'outbound'
                  AND level = 'WARNING'
                  AND message LIKE '%beacon was not transmitted before APRSBox core restart%'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            self.assertIsNotNone(log_row)


if __name__ == "__main__":
    unittest.main()
