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
    def test_export_contains_config_tables_and_whitelisted_app_settings(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
                VALUES ('TNC-A', 'TCP', '2m', '127.0.0.1:8001', NULL, 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            set_app_setting("app_language", "pl")
            set_app_setting("scheduler.wx.last_refresh_at", "2026-01-01T00:00:00+00:00")

            payload = export_configuration_backup()

            self.assertEqual(CONFIG_BACKUP_FORMAT, payload["format"])
            self.assertEqual(CONFIG_BACKUP_VERSION, payload["backup_version"])
            modem_rows = payload["tables"]["modems"]
            self.assertEqual(1, len(modem_rows))
            self.assertEqual("TNC-A", modem_rows[0]["name"])
            self.assertEqual("pl", payload["app_settings"]["app_language"])
            self.assertNotIn("scheduler.wx.last_refresh_at", payload["app_settings"])

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


if __name__ == "__main__":
    unittest.main()
