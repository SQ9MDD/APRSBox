import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, init_db
from app.services import content
from app.services.content import get_station_detail


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


def insert_tnc2_frame(line: str, *, created_at: str = "2026-01-01T00:00:00+00:00") -> None:
    execute(
        """
        INSERT INTO traffic_frames(source, interface_id, direction, band, format, line, port, command, length, hex, created_at)
        VALUES (?, NULL, 'RX', '2m', 'TNC2', ?, '', '', ?, '', ?)
        """,
        ("rf", line, len(line), created_at),
    )


def sample_identification() -> dict[str, object]:
    return {
        "identifier_kind": "tocall",
        "actual_identifier": "APDW16",
        "matched_pattern": "APDW??",
        "short_name": "DireWolf",
        "identified_as": "DireWolf",
        "vendor": "WB2OSZ",
        "model": "DireWolf",
        "class_label": "Desktop software",
        "class_description": "Desktop software",
        "message_capable": True,
        "features": ["messaging"],
    }


class StationDeviceIdentificationVisibilityTests(unittest.TestCase):
    def test_station_detail_shows_identification_for_station_position_frame(self) -> None:
        with temporary_database(), patch(
            "app.services.content.lookup_aprs_device_identification",
            return_value=sample_identification(),
        ), patch(
            "app.services.content.get_aprs_device_identification_database",
            return_value={},
        ):
            insert_tnc2_frame("SP8ABC-9>APDW16:!5218.37N\\02104.87E>Test")

            detail = get_station_detail("SP8ABC-9")
            assert detail is not None
            self.assertIsNotNone(detail["aprs_device"])
            self.assertEqual((detail["aprs_device"] or {}).get("short_name"), "DireWolf")

    def test_station_detail_does_not_show_identification_for_object_frame(self) -> None:
        with temporary_database(), patch(
            "app.services.content.lookup_aprs_device_identification",
            return_value=sample_identification(),
        ), patch(
            "app.services.content.get_aprs_device_identification_database",
            return_value={},
        ):
            insert_tnc2_frame("SP8ABC-9>APDW16:;OBJTEST  *010203z5228.23N/02101.28E#Object")

            detail = get_station_detail("OBJTEST")
            assert detail is not None
            self.assertEqual(detail["entity_class"], "object")
            self.assertIsNone(detail["aprs_device"])

    def test_station_detail_hides_identification_when_lookup_returns_none(self) -> None:
        with temporary_database(), patch(
            "app.services.content.lookup_aprs_device_identification",
            return_value=None,
        ), patch(
            "app.services.content.get_aprs_device_identification_database",
            return_value={},
        ):
            insert_tnc2_frame("SP8ABC-9>APDW16:!5218.37N\\02104.87E>Test")

            detail = get_station_detail("SP8ABC-9")
            assert detail is not None
            self.assertIsNone(detail["aprs_device"])

    def test_station_detail_exposes_mic_e_details_for_mic_e_frame(self) -> None:
        with temporary_database(), patch(
            "app.services.content.lookup_aprs_device_identification",
            return_value={
                "identifier_kind": "mic-e",
                "actual_identifier": "_0",
                "matched_pattern": "_0",
                "short_name": "FT3D",
                "identified_as": "FT3D",
                "vendor": "Yaesu",
                "model": "FT3D",
                "class_label": "Handheld APRS client",
                "class_description": "Handheld APRS client",
                "message_capable": True,
                "features": ["messaging"],
            },
        ), patch(
            "app.services.content.get_aprs_device_identification_database",
            return_value={},
        ):
            insert_tnc2_frame('SO5AJM-7 > URTW13 , SR5NWR*,WIDE1*,WIDE2*:`14M^\\^]D[/"4N}Witam!')

            detail = get_station_detail("SO5AJM-7")
            assert detail is not None
            self.assertIsNotNone(detail["mic_e"])
            self.assertEqual((detail["mic_e"] or {}).get("destination_raw"), "URTW13")
            self.assertEqual((detail["mic_e"] or {}).get("device_name"), "FT3D")
            fields = detail.get("fields") or []
            self.assertIn({"label": "Packet type", "value": "Mic-E"}, fields)
            self.assertTrue(any(field.get("label") == "Destination" and "Mic-E encoded" in str(field.get("value") or "") for field in fields))


if __name__ == "__main__":
    unittest.main()
