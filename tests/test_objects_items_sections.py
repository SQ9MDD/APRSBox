import contextlib
import os
import re
import tempfile
import unittest
from pathlib import Path

from app.db import fetch_one, init_db
from app.services.content import get_section_row, safe_create_section_row, safe_update_section_row, update_station_settings


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


class ObjectAndItemFormTests(unittest.TestCase):
    def test_object_row_contains_symbol_icon_and_raw_frame_preview(self) -> None:
        with temporary_database():
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "9",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": None,
                }
            )
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "VOICE",
                    "state": "live",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "path": "WIDE2-2",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one("SELECT id FROM aprs_objects WHERE name = ?", ("VOICE",))
            assert row is not None

            decorated = get_section_row("objects", int(row["id"]))
            assert decorated is not None
            self.assertEqual(decorated["symbol_icon"], "icons/verG/81.gif")
            self.assertRegex(
                decorated["raw_frame_preview"],
                r"^SQ9XYZ-9>APRS,WIDE2-2:;VOICE {4}\*[0-9]{6}z5213\.78N/02100\.73ErLocal voice repeater$",
            )

    def test_object_record_accepts_valid_aprs_fields(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "VOICE",
                    "state": "live",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "path": "WIDE2-2",
                    "is_enabled": "1",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)

            row = fetch_one("SELECT name, state, path, is_enabled, comment FROM aprs_objects WHERE name = ?", ("VOICE",))
            assert row is not None
            self.assertEqual(row["state"], "live")
            self.assertEqual(row["path"], "WIDE2-2")
            self.assertEqual(row["is_enabled"], 1)

    def test_object_name_longer_than_nine_characters_is_rejected(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "TOO-LONG-1",
                    "state": "live",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "path": "",
                    "comment": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Object name must be 1-9 printable ASCII characters.")

    def test_item_name_must_be_between_three_and_nine_characters(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "items",
                {
                    "name": "A",
                    "state": "live",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": "A",
                    "path": "",
                    "comment": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Item name must be 3-9 printable ASCII characters.")

    def test_item_name_cannot_contain_kill_or_live_delimiters(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "items",
                {
                    "name": "AID_1",
                    "state": "live",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": "A",
                    "path": "",
                    "comment": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Item name cannot contain ! or _.")

    def test_comment_longer_than_plain_report_capacity_is_rejected(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "items",
                {
                    "name": "AID01",
                    "state": "live",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": "A",
                    "path": "",
                    "comment": "X" * 44,
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Comment must be 43 printable ASCII characters or fewer.")

    def test_update_preserves_valid_item_state_and_path(self) -> None:
        with temporary_database():
            created, error = safe_create_section_row(
                "items",
                {
                    "name": "AID01",
                    "state": "live",
                    "latitude": "52.0",
                    "longitude": "21.0",
                    "symbol_table": "/",
                    "symbol_code": "A",
                    "path": "",
                    "comment": "Aid station",
                },
            )
            self.assertTrue(created)
            self.assertIsNone(error)
            row = fetch_one("SELECT id FROM aprs_items WHERE name = ?", ("AID01",))
            assert row is not None

            success, update_error = safe_update_section_row(
                "items",
                int(row["id"]),
                {
                    "name": "AID01",
                    "state": "killed",
                    "latitude": "52.0",
                    "longitude": "21.0",
                    "symbol_table": "\\",
                    "symbol_code": "A",
                    "path": "WIDE1-1,WIDE2-1",
                    "comment": "Aid station",
                    "is_enabled": "1",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(update_error)

            updated = get_section_row("items", int(row["id"]))
            assert updated is not None
            self.assertEqual(updated["state"], "killed")
            self.assertEqual(updated["path"], "WIDE1-1,WIDE2-1")
            self.assertEqual(updated["symbol_table"], "\\")
            self.assertEqual(updated["is_enabled"], 1)


if __name__ == "__main__":
    unittest.main()
