import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, get_app_setting, init_db, set_app_setting
from app.services.config_backup import (
    CONFIG_BACKUP_FORMAT,
    CONFIG_BACKUP_VERSION,
    build_configuration_backup_filename,
    export_configuration_backup,
    export_configuration_backup_bytes,
    safe_import_configuration_backup,
)


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


class ConfigBackupTests(unittest.TestCase):
    def test_filename_contains_station_callsign_and_ssid(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'sp0abc', ssid = '5', updated_at = '2026-01-01T00:00:00+00:00'
                WHERE id = 1
                """
            )
            filename = build_configuration_backup_filename()
            self.assertIn("SP0ABC-5", filename)
            self.assertTrue(filename.startswith("aprsbox-config-backup-"))
            self.assertTrue(filename.endswith(".json"))

    def test_export_contains_config_tables_and_whitelisted_app_settings(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
                VALUES ('TNC-A', 'TCP', '2m', '127.0.0.1:8001', NULL, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            set_app_setting("app_language", "pl")
            set_app_setting("traffic_retention_minutes", "180")
            set_app_setting("map_coverage_fill_opacity", "5")
            set_app_setting("map_marker_clustering_enabled", "1")
            set_app_setting("aprs.map_alarm_level_threshold", "2")
            set_app_setting("aprs.global_alarm_level_threshold", "3")
            set_app_setting(
                "aprs.alarm_category_thresholds",
                '{"HEAT":{"alerts":2,"map":3}}',
            )
            set_app_setting("scheduler.wx.last_refresh_at", "2026-01-01T00:00:00+00:00")

            payload = export_configuration_backup()

            self.assertEqual(CONFIG_BACKUP_FORMAT, payload["format"])
            self.assertEqual(2, CONFIG_BACKUP_VERSION)
            self.assertEqual(2, payload["backup_version"])
            modem_rows = payload["tables"]["modems"]
            self.assertEqual(1, len(modem_rows))
            self.assertEqual("TNC-A", modem_rows[0]["name"])
            self.assertEqual("pl", payload["app_settings"]["app_language"])
            self.assertEqual("180", payload["app_settings"]["traffic_retention_minutes"])
            self.assertEqual("5", payload["app_settings"]["map_coverage_fill_opacity"])
            self.assertEqual("1", payload["app_settings"]["map_marker_clustering_enabled"])
            self.assertEqual(
                "2",
                payload["app_settings"]["aprs.map_alarm_level_threshold"],
            )
            self.assertEqual(
                "3",
                payload["app_settings"]["aprs.global_alarm_level_threshold"],
            )
            self.assertEqual(
                '{"HEAT":{"alerts":2,"map":3}}',
                payload["app_settings"]["aprs.alarm_category_thresholds"],
            )
            self.assertNotIn("scheduler.wx.last_refresh_at", payload["app_settings"])
            self.assertNotIn("band_condition_reference_stations", payload["tables"])
            self.assertIn("messages.default_path", payload["app_settings"])
            self.assertIsNone(payload["app_settings"]["messages.default_path"])

    def test_import_restores_configuration_without_overwriting_runtime_app_settings(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
                VALUES ('TNC-A', 'TCP', '2m', '127.0.0.1:8001', NULL, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SP0ABC', ssid = '2', updated_at = '2026-01-01T00:00:00+00:00'
                WHERE id = 1
                """
            )
            execute(
                """
                INSERT INTO digi_flows(
                    name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at
                )
                VALUES ('Flow A', 'Test flow', 'receiver_rf', 'TNC-A', 'tx_aprsis', 'aprsis', 1, 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            flow_row = fetch_one("SELECT id FROM digi_flows WHERE name = 'Flow A'")
            assert flow_row is not None
            execute(
                """
                INSERT INTO digi_flow_steps(
                    flow_id, step_order, step_type, title, enabled, config_json, created_at, updated_at
                )
                VALUES (?, 1, 'receiver_rf', 'Receiver', 1, '{}', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                (int(flow_row["id"]),),
            )
            set_app_setting("app_language", "pl")
            set_app_setting("scheduler.wx.last_refresh_at", "runtime-before-export")

            backup_payload = export_configuration_backup_bytes()

            execute("DELETE FROM digi_flow_steps")
            execute("DELETE FROM digi_flows")
            execute("DELETE FROM modems")
            execute("UPDATE station_settings SET callsign = 'CHANGED', ssid = '9', updated_at = '2026-02-01T00:00:00+00:00' WHERE id = 1")
            set_app_setting("app_language", "en")
            set_app_setting("scheduler.wx.last_refresh_at", "runtime-after-export")

            success, error = safe_import_configuration_backup(backup_payload)
            self.assertTrue(success, error)

            restored_modem = fetch_one("SELECT name FROM modems ORDER BY id ASC LIMIT 1")
            assert restored_modem is not None
            self.assertEqual("TNC-A", restored_modem["name"])
            restored_station = fetch_one("SELECT callsign, ssid FROM station_settings WHERE id = 1")
            assert restored_station is not None
            self.assertEqual("SP0ABC", restored_station["callsign"])
            self.assertEqual("2", restored_station["ssid"])
            restored_steps = fetch_one("SELECT COUNT(*) AS total FROM digi_flow_steps")
            assert restored_steps is not None
            self.assertEqual(1, int(restored_steps["total"]))
            self.assertEqual("pl", get_app_setting("app_language"))
            self.assertEqual("runtime-after-export", get_app_setting("scheduler.wx.last_refresh_at"))

    def test_import_rejects_invalid_payload(self) -> None:
        with temporary_database():
            ok, error = safe_import_configuration_backup(b"{")
            self.assertFalse(ok)
            self.assertIn("valid JSON", str(error))

            payload = export_configuration_backup()
            del payload["tables"]["modems"]
            ok, error = safe_import_configuration_backup(json.dumps(payload).encode("utf-8"))
            self.assertFalse(ok)
            self.assertIn("missing table data", str(error))

            payload = export_configuration_backup()
            payload["backup_version"] = 1
            ok, error = safe_import_configuration_backup(json.dumps(payload).encode("utf-8"))
            self.assertFalse(ok)
            self.assertIn("Unsupported backup version", str(error))

            payload = export_configuration_backup()
            del payload["app_settings"]["messages.default_path"]
            ok, error = safe_import_configuration_backup(json.dumps(payload).encode("utf-8"))
            self.assertFalse(ok)
            self.assertIn("missing app settings", str(error))

    def test_import_accepts_older_v2_backup_without_marker_clustering_setting(self) -> None:
        with temporary_database():
            payload = export_configuration_backup()
            del payload["app_settings"]["map_marker_clustering_enabled"]

            ok, error = safe_import_configuration_backup(json.dumps(payload).encode("utf-8"))

            self.assertTrue(ok, error)
            self.assertEqual(get_app_setting("map_marker_clustering_enabled"), "0")

    def test_import_accepts_older_v2_backup_without_marker_spiderfy_settings(self) -> None:
        with temporary_database():
            payload = export_configuration_backup()
            del payload["app_settings"]["map_marker_spiderfy_enabled"]
            del payload["app_settings"]["map_marker_spiderfy_zoom_levels_before_max"]
            del payload["app_settings"]["map_marker_spiderfy_nearby_distance_px"]

            ok, error = safe_import_configuration_backup(json.dumps(payload).encode("utf-8"))

            self.assertTrue(ok, error)
            self.assertEqual(get_app_setting("map_marker_spiderfy_enabled"), "0")
            self.assertEqual(get_app_setting("map_marker_spiderfy_zoom_levels_before_max"), "2")
            self.assertEqual(get_app_setting("map_marker_spiderfy_nearby_distance_px"), "20")

    def test_export_and_import_restores_messages_and_notification_configuration(self) -> None:
        with temporary_database():
            for key, value in (
                ("messages.default_path", "WIDE1-1"),
                ("messages.receive_any_ssid", "1"),
                ("messages.target_groups", "ALL,QST"),
                ("station.tx.internal_mode", "1"),
                ("messages_enabled", "1"),
                ("messages_include_content", "1"),
                ("radar_enabled", "1"),
                ("radar_ignored_patterns", "TEST*,N0CALL"),
            ):
                set_app_setting(key, value)
            execute(
                """
                INSERT INTO notification_transports(
                    name, transport_type, enabled, url, secret_header_name, secret_token,
                    bot_token, chat_id, timeout_s, last_test_status, last_test_error, last_test_at,
                    created_at, updated_at
                )
                VALUES (
                    'Primary webhook', 'webhook', 1, 'https://example.invalid/original', 'Authorization', 'secret',
                    '', '', 7, 'ok', '', '2026-01-01T00:00:00+00:00',
                    '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
                )
                """
            )
            execute(
                """
                INSERT INTO notification_radar_rules(enabled, pattern, distance_m, created_at, updated_at)
                VALUES (1, 'SP0*', 50000, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )

            backup_payload = export_configuration_backup_bytes()
            decoded = json.loads(backup_payload)
            transport_payload = decoded["tables"]["notification_transports"][0]
            self.assertNotIn("last_test_status", transport_payload)
            self.assertNotIn("last_test_error", transport_payload)
            self.assertNotIn("last_test_at", transport_payload)

            set_app_setting("messages.default_path", "")
            set_app_setting("messages_enabled", "0")
            execute(
                """
                UPDATE notification_transports
                SET url = 'https://example.invalid/changed', last_test_status = 'error',
                    last_test_error = 'runtime result', last_test_at = '2026-02-01T00:00:00+00:00'
                """
            )
            execute("UPDATE notification_radar_rules SET pattern = 'CHANGED', distance_m = 1")

            success, error = safe_import_configuration_backup(backup_payload)
            self.assertTrue(success, error)
            self.assertEqual("WIDE1-1", get_app_setting("messages.default_path"))
            self.assertEqual("1", get_app_setting("messages_enabled"))
            transport = fetch_one("SELECT * FROM notification_transports WHERE name = 'Primary webhook'")
            assert transport is not None
            self.assertEqual("https://example.invalid/original", transport["url"])
            self.assertEqual("error", transport["last_test_status"])
            self.assertEqual("runtime result", transport["last_test_error"])
            rule = fetch_one("SELECT pattern, distance_m FROM notification_radar_rules")
            assert rule is not None
            self.assertEqual("SP0*", rule["pattern"])
            self.assertEqual(50000, int(rule["distance_m"]))

    def test_importing_identical_backup_preserves_runtime_references_and_flow_logs(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
                VALUES ('TNC-A', 'TCP', '2m', '127.0.0.1:8001', NULL, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            modem = fetch_one("SELECT id FROM modems WHERE name = 'TNC-A'")
            assert modem is not None
            execute(
                """
                INSERT INTO outbound_jobs(kind, interface_id, payload_json, status, scheduled_at, created_at, updated_at)
                VALUES ('beacon', ?, '{}', 'queued', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                (int(modem["id"]),),
            )
            execute(
                """
                INSERT INTO digi_flows(name, description, source_kind, source_ref, target_kind, target_ref, enabled, sort_order, created_at, updated_at)
                VALUES ('Flow A', '', 'receiver_rf', 'TNC-A', 'action_log', 'log', 1, 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            flow = fetch_one("SELECT id FROM digi_flows WHERE name = 'Flow A'")
            assert flow is not None
            execute(
                """
                INSERT INTO digi_flow_event_log(frame_uid, flow_id, step_id, event_type, decision, message, created_at)
                VALUES ('frame-1', ?, NULL, 'flow', 'accepted', 'runtime log', '2026-01-01T00:00:00+00:00')
                """,
                (int(flow["id"]),),
            )

            backup_payload = export_configuration_backup_bytes()
            success, error = safe_import_configuration_backup(backup_payload)
            self.assertTrue(success, error)

            outbound = fetch_one("SELECT interface_id FROM outbound_jobs")
            assert outbound is not None
            self.assertEqual(int(modem["id"]), int(outbound["interface_id"]))
            flow_log = fetch_one("SELECT flow_id, message FROM digi_flow_event_log WHERE frame_uid = 'frame-1'")
            assert flow_log is not None
            self.assertEqual(int(flow["id"]), int(flow_log["flow_id"]))
            self.assertEqual("runtime log", flow_log["message"])

    def test_import_handles_unique_values_that_were_swapped_between_existing_ids(self) -> None:
        with temporary_database():
            for name, endpoint in (("TNC-A", "127.0.0.1:8001"), ("TNC-B", "127.0.0.1:8002")):
                execute(
                    """
                    INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
                    VALUES (?, 'TCP', '2m', ?, NULL, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                    """,
                    (name, endpoint),
                )
            modem_a = fetch_one("SELECT id FROM modems WHERE name = 'TNC-A'")
            modem_b = fetch_one("SELECT id FROM modems WHERE name = 'TNC-B'")
            assert modem_a is not None and modem_b is not None
            execute(
                """
                INSERT INTO outbound_jobs(kind, interface_id, payload_json, status, scheduled_at, created_at, updated_at)
                VALUES ('beacon', ?, '{}', 'queued', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                (int(modem_a["id"]),),
            )
            backup_payload = export_configuration_backup_bytes()

            execute("UPDATE modems SET name = '__TEMP__' WHERE id = ?", (int(modem_a["id"]),))
            execute("UPDATE modems SET name = 'TNC-A' WHERE id = ?", (int(modem_b["id"]),))
            execute("UPDATE modems SET name = 'TNC-B' WHERE id = ?", (int(modem_a["id"]),))

            success, error = safe_import_configuration_backup(backup_payload)
            self.assertTrue(success, error)
            restored_a = fetch_one("SELECT name FROM modems WHERE id = ?", (int(modem_a["id"]),))
            restored_b = fetch_one("SELECT name FROM modems WHERE id = ?", (int(modem_b["id"]),))
            assert restored_a is not None and restored_b is not None
            self.assertEqual("TNC-A", restored_a["name"])
            self.assertEqual("TNC-B", restored_b["name"])
            outbound = fetch_one("SELECT interface_id FROM outbound_jobs")
            assert outbound is not None
            self.assertEqual(int(modem_a["id"]), int(outbound["interface_id"]))

    def test_import_clears_runtime_foreign_keys_when_backup_has_no_modems(self) -> None:
        with temporary_database():
            backup_payload = export_configuration_backup_bytes()

            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
                VALUES ('RUNTIME-TNC', 'TCP', '2m', '127.0.0.1:8100', NULL, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            modem_row = fetch_one("SELECT id FROM modems WHERE name = 'RUNTIME-TNC'")
            assert modem_row is not None
            modem_id = int(modem_row["id"])
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at, created_at, updated_at
                )
                VALUES ('beacon', ?, '{}', 'queued', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                (modem_id,),
            )

            success, error = safe_import_configuration_backup(backup_payload)
            self.assertTrue(success, error)
            outbound_row = fetch_one("SELECT interface_id FROM outbound_jobs ORDER BY id ASC LIMIT 1")
            assert outbound_row is not None
            self.assertIsNone(outbound_row["interface_id"])


if __name__ == "__main__":
    unittest.main()
