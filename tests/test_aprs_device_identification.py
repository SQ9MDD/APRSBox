import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.config import settings
from app.db import get_app_setting, init_db, set_app_setting
from app.services import aprs_device_identification as device_id


def sample_database_payload() -> dict[str, object]:
    return {
        "meta": {"generation_time": "2026-04-03T16:21:06Z"},
        "tocalls": {
            "APDW??": {
                "vendor": "WB2OSZ",
                "model": "DireWolf",
                "class": "software",
                "features": ["messaging"],
            }
        },
        "mice": {
            "_0": {
                "vendor": "Yaesu",
                "model": "FT3D",
                "class": "ht",
                "features": ["messaging"],
            }
        },
        "micelegacy": {
            ">=": {
                "vendor": "Kenwood",
                "model": "TH-D72",
                "class": "ht",
                "features": ["messaging"],
            }
        },
        "classes": {
            "software": {"shown": "Desktop software", "description": "Desktop software"},
            "ht": {"shown": "HT", "description": "Hand-held radio"},
        },
    }


class DummyResponse(io.BytesIO):
    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "runtime" / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        device_id._DB_CACHE.clear()
        try:
            init_db()
            yield database_path
        finally:
            device_id._DB_CACHE.clear()
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def write_runtime_cache(payload: dict[str, object]) -> Path:
    cache_path = settings.aprs_device_identification_cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    device_id._DB_CACHE.clear()
    return cache_path


class AprsDeviceIdentificationTests(unittest.TestCase):
    def test_automatic_update_is_due_when_no_success_was_recorded(self) -> None:
        with temporary_database():
            self.assertTrue(
                device_id.is_aprs_device_identification_auto_update_due(
                    now=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
                )
            )

    def test_automatic_update_is_due_after_thirty_days(self) -> None:
        with temporary_database():
            now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
            set_app_setting(device_id.UPDATE_SUCCESS_AT_KEY, (now - timedelta(days=31)).isoformat())
            self.assertTrue(device_id.is_aprs_device_identification_auto_update_due(now=now))

    def test_recent_success_or_failed_attempt_suppresses_automatic_update(self) -> None:
        with temporary_database():
            now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
            set_app_setting(device_id.UPDATE_SUCCESS_AT_KEY, (now - timedelta(days=29)).isoformat())
            self.assertFalse(device_id.is_aprs_device_identification_auto_update_due(now=now))

            set_app_setting(device_id.UPDATE_SUCCESS_AT_KEY, (now - timedelta(days=31)).isoformat())
            set_app_setting(device_id.UPDATE_ATTEMPT_AT_KEY, (now - timedelta(hours=2)).isoformat())
            self.assertFalse(device_id.is_aprs_device_identification_auto_update_due(now=now))

    def test_settings_gui_starts_due_update_silently(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('data-auto-update-due="{{ \'true\' if aprs_device_identification_status.auto_update_due else \'false\' }}"', template_source)
        self.assertIn("runAutomaticDeviceIdentificationUpdate", template_source)
        self.assertIn("window.setTimeout(() => void runAutomaticDeviceIdentificationUpdate(), 750)", template_source)
        self.assertNotIn("automaticDeviceIdentificationUpdateForm.requestSubmit()", template_source)

    def test_lookup_uses_runtime_cache_for_tocall_wildcard(self) -> None:
        with temporary_database():
            write_runtime_cache(sample_database_payload())

            result = device_id.lookup_aprs_device_identification(destination="APDW16", info=">status")

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["actual_identifier"], "APDW16")
            self.assertEqual(result["matched_pattern"], "APDW??")
            self.assertEqual(result["short_name"], "DireWolf")
            self.assertEqual(result["class_label"], "Desktop software")
            self.assertTrue(result["message_capable"])

    def test_lookup_decodes_mic_e_manufacturer_and_version_bytes(self) -> None:
        with temporary_database():
            write_runtime_cache(sample_database_payload())

            result = device_id.lookup_aprs_device_identification(destination="ABCDEF", info="`ABCDEFGHtext_0")

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["identifier_kind"], "mic-e")
            self.assertEqual(result["actual_identifier"], "_0")
            self.assertEqual(result["model"], "FT3D")
            self.assertEqual(result["class_label"], "Handheld APRS client")

    def test_refresh_keeps_existing_cache_when_download_is_invalid(self) -> None:
        with temporary_database():
            cache_path = write_runtime_cache(sample_database_payload())
            original_contents = cache_path.read_text(encoding="utf-8")

            with patch.object(device_id, "urlopen", return_value=DummyResponse(b"{invalid json")):
                result = device_id.refresh_aprs_device_identification_cache()

            self.assertFalse(result["ok"])
            self.assertEqual(cache_path.read_text(encoding="utf-8"), original_contents)
            self.assertEqual(get_app_setting(device_id.UPDATE_GENERATION_TIME_KEY), None)
            self.assertTrue(get_app_setting(device_id.UPDATE_ERROR_KEY))


if __name__ == "__main__":
    unittest.main()
