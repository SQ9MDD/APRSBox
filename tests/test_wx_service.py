import contextlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from app.db import fetch_one, get_connection, init_db
from app.services.content import update_station_settings
from app.services.wx_scheduler import WxSchedulerService
from app.services.wx import (
    ensure_wx_defaults,
    refresh_single_wx_mapping,
    safe_save_wx_config,
    safe_save_wx_source,
    save_wx_mappings,
)


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
                    "refresh_interval_s": "300",
                    "allow_cache_fallback": "1",
                    "default_cache_max_age_s": "900",
                }
            )
            self.assertFalse(success)
            self.assertIn("not available", error or "")

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
                    "refresh_interval_s": "300",
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


if __name__ == "__main__":
    unittest.main()
