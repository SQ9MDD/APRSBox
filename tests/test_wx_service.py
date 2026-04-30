import contextlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from app.db import execute, fetch_all, fetch_one, get_app_setting, get_connection, init_db, set_app_setting
from app.services.content import update_station_settings
from app.services.outbound import build_wx_tnc2, claim_next_outbound_job, get_outbound_job
from app.services.outbound_runtime import OutboundService
from app.services.wx_scheduler import WxSchedulerService
from app.services.wx import (
    WX_REFRESH_LAST_AT_KEY,
    ensure_wx_defaults,
    refresh_single_wx_mapping,
    safe_enqueue_wx_outbound,
    safe_save_wx_config,
    safe_save_wx_source,
    save_wx_mappings,
    test_wx_source_connection,
)
from app.services.tx_scope import ALL_ACTIVE_INTERFACE_OPTION_VALUE, TX_SCOPE_ALL_ACTIVE


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            ensure_wx_defaults()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def insert_modem(*, name: str = "WX TNC", device_path: str = "127.0.0.1:8001") -> int:
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


class WxServiceTests(unittest.TestCase):
    def test_init_db_creates_wx_tables(self) -> None:
        with temporary_database() as database_path:
            raw = sqlite3.connect(database_path)
            raw.row_factory = sqlite3.Row
            try:
                table_names = {
                    row["name"]
                    for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
                self.assertIn("wx_config", table_names)
                self.assertIn("wx_sources", table_names)
                self.assertIn("wx_mappings", table_names)
                self.assertIn("wx_runtime_cache", table_names)
            finally:
                raw.close()

    def test_wx_config_rejects_ssid_used_by_my_settings(self) -> None:
        with temporary_database():
            modem_id = insert_modem()
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success, error = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "4",
                    "beacon_interface_id": str(modem_id),
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "300",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertFalse(success)
            self.assertIn("not available", error or "")

    def test_wx_config_accepts_interface_path_and_coordinates(self) -> None:
        with temporary_database():
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            modem_id = insert_modem()
            success, error = safe_save_wx_config(
                {
                    "enabled": "",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "900",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success, error)
            row = fetch_one("SELECT beacon_interface_id, path, latitude, longitude FROM wx_config WHERE id = 1")
            assert row is not None
            self.assertEqual(int(row["beacon_interface_id"]), modem_id)
            self.assertEqual(row["path"], "WIDE2-2")
            self.assertEqual(row["latitude"], "52.2297")
            self.assertEqual(row["longitude"], "21.0122")

    def test_wx_all_active_scope_queues_jobs_for_each_active_tnc(self) -> None:
        with temporary_database():
            first_modem = insert_modem(name="WX A", device_path="127.0.0.1:8101")
            second_modem = insert_modem(name="WX B", device_path="127.0.0.1:8102")
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success, error = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": ALL_ACTIVE_INTERFACE_OPTION_VALUE,
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "900",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success, error)
            row = fetch_one("SELECT beacon_interface_id, beacon_tx_scope FROM wx_config WHERE id = 1")
            assert row is not None
            self.assertIsNone(row["beacon_interface_id"])
            self.assertEqual(row["beacon_tx_scope"], TX_SCOPE_ALL_ACTIVE)

            queued, message = safe_enqueue_wx_outbound(trigger="manual")
            self.assertTrue(queued, message)

            count_row = fetch_one("SELECT COUNT(*) AS total FROM outbound_jobs WHERE kind = 'wx'")
            assert count_row is not None
            self.assertEqual(int(count_row["total"]), 2)
            interface_rows = fetch_all("SELECT DISTINCT interface_id FROM outbound_jobs WHERE kind = 'wx'")
            self.assertEqual({first_modem, second_modem}, {int(item["interface_id"]) for item in interface_rows})

    def test_wx_config_interval_allows_5m_for_empty_or_rfonly_path(self) -> None:
        with temporary_database():
            modem_id = insert_modem()
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success_empty_path, error_empty_path = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "300",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success_empty_path, error_empty_path)

            success_rfonly_path, error_rfonly_path = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "rfonly",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "600",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success_rfonly_path, error_rfonly_path)

    def test_wx_config_interval_restricts_routed_paths_and_accepts_39m(self) -> None:
        with temporary_database():
            modem_id = insert_modem()
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success_invalid, error_invalid = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "600",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertFalse(success_invalid)
            self.assertIn("must be one of", str(error_invalid or ""))

            success_valid, error_valid = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "2340",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success_valid, error_valid)

    def test_wx_config_can_enable_without_required_mappings(self) -> None:
        with temporary_database():
            modem_id = insert_modem()
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success, error = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "900",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success, error)

    def test_domoticz_connection_test_uses_devices_endpoint_without_auth(self) -> None:
        with temporary_database():
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Domoticz",
                    "source_type": "domoticz",
                    "base_url": "http://domoticz.local:8080",
                    "auth_type": "none",
                    "token": "",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None

            def domoticz_devices_response(request, timeout=0, context=None):  # type: ignore[no-untyped-def]
                self.assertIn("/json.htm", request.full_url)
                self.assertIn("type=devices", request.full_url)
                return FakeResponse({"status": "OK", "result": []})

            with patch("app.services.wx_sources.urlopen", side_effect=domoticz_devices_response):
                result = test_wx_source_connection(source_id)

            self.assertTrue(result.get("ok"))
            source_row = fetch_one("SELECT last_test_status, last_test_error FROM wx_sources WHERE id = ?", (source_id,))
            assert source_row is not None
            self.assertEqual(source_row["last_test_status"], "ok")
            self.assertEqual(source_row["last_test_error"], "")

    def test_domoticz_connection_accepts_base_url_with_json_htm(self) -> None:
        with temporary_database():
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Domoticz",
                    "source_type": "domoticz",
                    "base_url": "http://domoticz.local:8080/json.htm",
                    "auth_type": "none",
                    "token": "",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None

            def domoticz_json_htm_response(request, timeout=0, context=None):  # type: ignore[no-untyped-def]
                self.assertIn("/json.htm?", request.full_url)
                self.assertNotIn("/json.htm/json.htm", request.full_url)
                return FakeResponse({"status": "OK", "result": []})

            with patch("app.services.wx_sources.urlopen", side_effect=domoticz_json_htm_response):
                result = test_wx_source_connection(source_id)

            self.assertTrue(result.get("ok"))

    def test_wx_refresh_updates_live_cache_and_uses_cached_fallback(self) -> None:
        with temporary_database():
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Home Assistant",
                    "source_type": "home_assistant",
                    "base_url": "http://ha.local:8123",
                    "auth_type": "bearer",
                    "token": "test-token",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None
            save_wx_mappings(
                {
                    "temperature_f": {
                        "source_id": str(source_id),
                        "identifier": "sensor.outdoor_temperature",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "",
                        "cache_max_age_s": "600",
                    }
                }
            )

            def live_temperature_response(request, timeout=0, context=None):  # type: ignore[no-untyped-def]
                self.assertIn("/api/states/sensor.outdoor_temperature", request.full_url)
                return FakeResponse(
                    {
                        "entity_id": "sensor.outdoor_temperature",
                        "state": "20",
                        "last_changed": "2026-04-05T10:00:00+00:00",
                        "last_updated": "2026-04-05T10:00:00+00:00",
                        "attributes": {
                            "unit_of_measurement": "C",
                            "friendly_name": "Outdoor temperature",
                        },
                    }
                )

            with patch("app.services.wx_sources.urlopen", side_effect=live_temperature_response):
                refresh_single_wx_mapping("temperature_f")

            row = fetch_one(
                "SELECT status, normalized_value, normalized_unit, value_origin FROM wx_runtime_cache WHERE parameter_name = ?",
                ("temperature_f",),
            )
            assert row is not None
            self.assertEqual(row["status"], "LIVE")
            self.assertEqual(row["normalized_value"], "68")
            self.assertEqual(row["normalized_unit"], "F")
            self.assertEqual(row["value_origin"], "live")

            with patch("app.services.wx_sources.urlopen", side_effect=URLError("down")):
                refresh_single_wx_mapping("temperature_f")

            cached_row = fetch_one(
                "SELECT status, normalized_value, normalized_unit, value_origin, last_error FROM wx_runtime_cache WHERE parameter_name = ?",
                ("temperature_f",),
            )
            assert cached_row is not None
            self.assertEqual(cached_row["status"], "CACHED")
            self.assertEqual(cached_row["normalized_value"], "68")
            self.assertEqual(cached_row["normalized_unit"], "F")
            self.assertEqual(cached_row["value_origin"], "cache")
            self.assertIn("Network error", str(cached_row["last_error"] or ""))

    def test_wx_refresh_reads_domoticz_device_value(self) -> None:
        with temporary_database():
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Domoticz",
                    "source_type": "domoticz",
                    "base_url": "http://domoticz.local:8080",
                    "auth_type": "none",
                    "token": "",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None
            save_wx_mappings(
                {
                    "temperature_f": {
                        "source_id": str(source_id),
                        "identifier": "123",
                        "selector_kind": "field",
                        "selector_name": "Temp",
                        "unit_override": "",
                        "cache_max_age_s": "600",
                    }
                }
            )

            def domoticz_temperature_response(request, timeout=0, context=None):  # type: ignore[no-untyped-def]
                self.assertIn("type=devices", request.full_url)
                self.assertIn("rid=123", request.full_url)
                return FakeResponse(
                    {
                        "status": "OK",
                        "result": [
                            {
                                "idx": "123",
                                "Name": "Outdoor",
                                "Temp": "20.0",
                                "TempUnit": "C",
                                "LastUpdate": "2026-04-23 18:00:00",
                                "Type": "Temp",
                                "SubType": "Temperature",
                            }
                        ],
                    }
                )

            with patch("app.services.wx_sources.urlopen", side_effect=domoticz_temperature_response):
                refresh_single_wx_mapping("temperature_f")

            row = fetch_one(
                "SELECT status, normalized_value, normalized_unit, value_origin FROM wx_runtime_cache WHERE parameter_name = ?",
                ("temperature_f",),
            )
            assert row is not None
            self.assertEqual(row["status"], "LIVE")
            self.assertEqual(row["normalized_value"], "68")
            self.assertEqual(row["normalized_unit"], "F")
            self.assertEqual(row["value_origin"], "live")

    def test_wx_refresh_marks_stale_when_cache_is_too_old(self) -> None:
        with temporary_database():
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Home Assistant",
                    "source_type": "home_assistant",
                    "base_url": "http://ha.local:8123",
                    "auth_type": "bearer",
                    "token": "test-token",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None
            save_wx_mappings(
                {
                    "temperature_f": {
                        "source_id": str(source_id),
                        "identifier": "sensor.outdoor_temperature",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "",
                        "cache_max_age_s": "60",
                    }
                }
            )
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO wx_runtime_cache(
                        parameter_name, source_id, identifier, raw_value, raw_unit,
                        normalized_value, normalized_unit, value_origin, status,
                        last_success_at, last_attempt_at, last_error, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "temperature_f",
                        source_id,
                        "sensor.outdoor_temperature",
                        "20",
                        "C",
                        "68",
                        "F",
                        "live",
                        "LIVE",
                        "2020-04-05T09:00:00+00:00",
                        "2020-04-05T09:00:00+00:00",
                        "",
                        "2020-04-05T09:00:00+00:00",
                    ),
                )
            with patch("app.services.wx_sources.urlopen", side_effect=URLError("down")):
                refresh_single_wx_mapping("temperature_f")
            row = fetch_one(
                "SELECT status, value_origin, normalized_value FROM wx_runtime_cache WHERE parameter_name = ?",
                ("temperature_f",),
            )
            assert row is not None
            self.assertEqual(row["status"], "STALE")
            self.assertEqual(row["value_origin"], "cache")
            self.assertEqual(row["normalized_value"], "68")

    def test_wx_scheduler_tick_refreshes_cache_when_due(self) -> None:
        with temporary_database():
            modem_id = insert_modem()
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Home Assistant",
                    "source_type": "home_assistant",
                    "base_url": "http://ha.local:8123",
                    "auth_type": "bearer",
                    "token": "test-token",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None
            save_wx_mappings(
                {
                    "wind_direction_deg": {
                        "source_id": str(source_id),
                        "identifier": "sensor.wind_direction",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "deg",
                        "cache_max_age_s": "600",
                    },
                    "wind_speed_mph": {
                        "source_id": str(source_id),
                        "identifier": "sensor.wind_speed",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "mph",
                        "cache_max_age_s": "600",
                    },
                    "temperature_f": {
                        "source_id": str(source_id),
                        "identifier": "sensor.temperature",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "F",
                        "cache_max_age_s": "600",
                    },
                }
            )
            success, error = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "900",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success, error)

            def scheduler_response(request, timeout=0, context=None):  # type: ignore[no-untyped-def]
                if request.full_url.endswith("/api/states/sensor.wind_direction"):
                    return FakeResponse({"entity_id": "sensor.wind_direction", "state": "270", "attributes": {"unit_of_measurement": "deg"}})
                if request.full_url.endswith("/api/states/sensor.wind_speed"):
                    return FakeResponse({"entity_id": "sensor.wind_speed", "state": "12", "attributes": {"unit_of_measurement": "mph"}})
                if request.full_url.endswith("/api/states/sensor.temperature"):
                    return FakeResponse({"entity_id": "sensor.temperature", "state": "68", "attributes": {"unit_of_measurement": "F"}})
                raise AssertionError(request.full_url)

            scheduler = WxSchedulerService()
            with patch("app.services.wx_sources.urlopen", side_effect=scheduler_response):
                scheduler._tick()

            row = fetch_one(
                "SELECT status, normalized_value, value_origin FROM wx_runtime_cache WHERE parameter_name = ?",
                ("temperature_f",),
            )
            assert row is not None
            self.assertEqual(row["status"], "LIVE")
            self.assertEqual(row["normalized_value"], "68")
            self.assertEqual(row["value_origin"], "live")
            job_row = fetch_one("SELECT kind, status FROM outbound_jobs ORDER BY id DESC LIMIT 1")
            assert job_row is not None
            self.assertEqual(job_row["kind"], "wx")
            self.assertEqual(job_row["status"], "queued")
            self.assertIsNotNone(get_app_setting("scheduler.wx.last_enqueued_at"))

    def test_wx_scheduler_logs_pending_job_details_when_enqueue_is_blocked(self) -> None:
        with temporary_database():
            modem_id = insert_modem()
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success, error = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "900",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success, error)
            set_app_setting(WX_REFRESH_LAST_AT_KEY, "2026-04-30T08:35:00+00:00")
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES(
                    'wx', ?, '{"trigger":"scheduled"}',
                    'processing', '2026-04-30T08:33:00+00:00',
                    '2026-04-30T08:33:01+00:00', '2026-04-30T08:33:01+00:00', NULL, 1, NULL,
                    '2026-04-30T08:33:00+00:00', '2026-04-30T08:33:01+00:00'
                )
                """,
                (modem_id,),
            )

            scheduler = WxSchedulerService()
            scheduler._tick()

            log_row = fetch_one(
                """
                SELECT message
                FROM event_logs
                WHERE category = 'wx'
                  AND level = 'INFO'
                  AND message LIKE '%WX scheduler skipped enqueue because WX job #%'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            assert log_row is not None
            message = str(log_row["message"] or "")
            self.assertIn("status=processing", message)
            self.assertIn("started_at=2026-04-30T08:33:01+00:00", message)


class WxOutboundRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_wx_runtime_uses_placeholders_for_missing_required_fields(self) -> None:
        with temporary_database():
            modem_id = insert_modem(device_path="127.0.0.1:9010")
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Home Assistant",
                    "source_type": "home_assistant",
                    "base_url": "http://ha.local:8123",
                    "auth_type": "bearer",
                    "token": "test-token",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None
            save_wx_mappings(
                {
                    "temperature_f": {
                        "source_id": str(source_id),
                        "identifier": "sensor.temperature",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "F",
                        "cache_max_age_s": "600",
                    }
                }
            )
            success, error = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "900",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success, error)

            def temperature_only_response(request, timeout=0, context=None):  # type: ignore[no-untyped-def]
                if request.full_url.endswith("/api/states/sensor.temperature"):
                    return FakeResponse({"entity_id": "sensor.temperature", "state": "68", "attributes": {"unit_of_measurement": "F"}})
                raise AssertionError(request.full_url)

            scheduler = WxSchedulerService()
            with patch("app.services.wx_sources.urlopen", side_effect=temperature_only_response):
                scheduler._tick()

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "wx")

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
                self.assertEqual(port, 9010)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            runtime_job = get_outbound_job(int(job["id"]))
            assert runtime_job is not None
            expected_line = build_wx_tnc2(runtime_job["payload"])
            self.assertEqual(expected_line, "SQ9XYZ-13>APBOX0,WIDE2-2:=5213.78N/02100.73E_.../...t068")
            self.assertTrue(written_frames)

    async def test_scheduled_wx_flows_from_scheduler_to_runtime_send(self) -> None:
        with temporary_database():
            modem_id = insert_modem(device_path="127.0.0.1:9011")
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "status_enabled": "",
                    "status_text": "",
                    "status_interval_minutes": "30",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": "",
                }
            )
            success, error, source_id = safe_save_wx_source(
                {
                    "name": "Home Assistant",
                    "source_type": "home_assistant",
                    "base_url": "http://ha.local:8123",
                    "auth_type": "bearer",
                    "token": "test-token",
                    "username": "",
                    "password": "",
                    "timeout_s": "5",
                    "verify_tls": "",
                    "enabled": "1",
                }
            )
            self.assertTrue(success, error)
            assert source_id is not None
            save_wx_mappings(
                {
                    "wind_direction_deg": {
                        "source_id": str(source_id),
                        "identifier": "sensor.wind_direction",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "deg",
                        "cache_max_age_s": "600",
                    },
                    "wind_speed_mph": {
                        "source_id": str(source_id),
                        "identifier": "sensor.wind_speed",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "mph",
                        "cache_max_age_s": "600",
                    },
                    "temperature_f": {
                        "source_id": str(source_id),
                        "identifier": "sensor.temperature",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "F",
                        "cache_max_age_s": "600",
                    },
                    "humidity_pct": {
                        "source_id": str(source_id),
                        "identifier": "sensor.humidity",
                        "selector_kind": "state",
                        "selector_name": "",
                        "unit_override": "%",
                        "cache_max_age_s": "600",
                    },
                }
            )
            success, error = safe_save_wx_config(
                {
                    "enabled": "1",
                    "ssid": "13",
                    "beacon_interface_id": str(modem_id),
                    "path": "WIDE2-2",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "refresh_interval_s": "900",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertTrue(success, error)

            def scheduler_response(request, timeout=0, context=None):  # type: ignore[no-untyped-def]
                if request.full_url.endswith("/api/states/sensor.wind_direction"):
                    return FakeResponse({"entity_id": "sensor.wind_direction", "state": "270", "attributes": {"unit_of_measurement": "deg"}})
                if request.full_url.endswith("/api/states/sensor.wind_speed"):
                    return FakeResponse({"entity_id": "sensor.wind_speed", "state": "12", "attributes": {"unit_of_measurement": "mph"}})
                if request.full_url.endswith("/api/states/sensor.temperature"):
                    return FakeResponse({"entity_id": "sensor.temperature", "state": "68", "attributes": {"unit_of_measurement": "F"}})
                if request.full_url.endswith("/api/states/sensor.humidity"):
                    return FakeResponse({"entity_id": "sensor.humidity", "state": "45", "attributes": {"unit_of_measurement": "%"}})
                raise AssertionError(request.full_url)

            scheduler = WxSchedulerService()
            with patch("app.services.wx_sources.urlopen", side_effect=scheduler_response):
                scheduler._tick()

            job = claim_next_outbound_job()
            assert job is not None
            self.assertEqual(job["kind"], "wx")

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
                self.assertEqual(port, 9011)
                return object(), FakeWriter()

            outbound_service = OutboundService()
            with patch("app.services.outbound_runtime.asyncio.open_connection", side_effect=fake_open_connection):
                await outbound_service._process_job(job)

            job_row = fetch_one("SELECT id, status, payload_json FROM outbound_jobs WHERE kind = 'wx' ORDER BY id DESC LIMIT 1")
            assert job_row is not None
            self.assertEqual(job_row["status"], "sent")

            runtime_job = get_outbound_job(int(job_row["id"]))
            assert runtime_job is not None
            expected_line = build_wx_tnc2(runtime_job["payload"])
            self.assertEqual(expected_line, "SQ9XYZ-13>APBOX0,WIDE2-2:=5213.78N/02100.73E_270/012t068h45")
            self.assertTrue(written_frames)
            traffic_row = fetch_one("SELECT line FROM traffic_frames ORDER BY id DESC LIMIT 1")
            assert traffic_row is not None
            self.assertEqual(traffic_row["line"], expected_line)

    async def test_outbound_start_recovers_stale_processing_wx_job_and_logs_not_transmitted(self) -> None:
        with temporary_database():
            interface_id = insert_modem(device_path="127.0.0.1:9012")
            execute(
                """
                INSERT INTO outbound_jobs(
                    kind, interface_id, payload_json, status, scheduled_at,
                    locked_at, started_at, sent_at, attempt_count, last_error, created_at, updated_at
                )
                VALUES(
                    'wx', ?, '{"callsign":"SQ9MDD","ssid":"3"}',
                    'processing', '2026-04-30T08:33:00+00:00',
                    '2026-04-30T08:33:01+00:00', '2026-04-30T08:33:01+00:00', NULL, 1, NULL,
                    '2026-04-30T08:33:00+00:00', '2026-04-30T08:33:01+00:00'
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
                WHERE kind = 'wx'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            assert recovered is not None
            self.assertEqual(recovered["status"], "failed")
            self.assertIn("WX frame was not transmitted", str(recovered["last_error"] or ""))

            pending_row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM outbound_jobs
                WHERE kind = 'wx'
                  AND status IN ('queued', 'processing')
                """
            )
            assert pending_row is not None
            self.assertEqual(int(pending_row["total"]), 0)

            wx_log = fetch_one(
                """
                SELECT message
                FROM event_logs
                WHERE category = 'wx'
                  AND level = 'WARNING'
                  AND message LIKE '%WX frame was not transmitted before APRSBox core restart%'
                ORDER BY id DESC
                LIMIT 1
                """
            )
            self.assertIsNotNone(wx_log)


if __name__ == "__main__":
    unittest.main()
