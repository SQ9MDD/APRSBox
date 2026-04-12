import contextlib
import os
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
                    "lifetime": "temporary",
                    "state": "live",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "interval_minutes": "30",
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
                r"^SQ9XYZ-9>APBOX0,WIDE2-2:;VOICE {4}\*[0-9]{6}z5213\.78N/02100\.73ErLocal voice repeater$",
            )

    def test_object_record_accepts_valid_aprs_fields(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "VOICE",
                    "lifetime": "temporary",
                    "state": "live",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "interval_minutes": "45",
                    "path": "WIDE2-2",
                    "is_enabled": "1",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)

            row = fetch_one("SELECT name, lifetime, state, interval_minutes, path, is_enabled, comment FROM aprs_objects WHERE name = ?", ("VOICE",))
            assert row is not None
            self.assertEqual(row["lifetime"], "temporary")
            self.assertEqual(row["state"], "live")
            self.assertEqual(row["interval_minutes"], 45)
            self.assertEqual(row["path"], "WIDE2-2")
            self.assertEqual(row["is_enabled"], 1)

    def test_object_name_longer_than_nine_characters_is_rejected(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "TOO-LONG-1",
                    "lifetime": "temporary",
                    "state": "live",
                    "latitude": "",
                    "longitude": "",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "interval_minutes": "30",
                    "path": "",
                    "comment": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Object name must be 1-9 printable ASCII characters.")

    def test_object_comment_is_required(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "VOICE",
                    "lifetime": "temporary",
                    "state": "live",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "interval_minutes": "30",
                    "path": "",
                    "comment": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Object comment is required.")

    def test_objects_template_includes_comment_counter_and_ascii_validation_message(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn('id="objects-comment-text"', template_source)
        self.assertIn('id="objects-comment-count"', template_source)
        self.assertIn('id="objects-comment-error"', template_source)
        self.assertIn("National characters are blocked.", template_source)
        self.assertIn(
            "Required. Use up to 43 printable ASCII characters if you want a plain object report without extra data extensions.",
            template_source,
        )

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
                    "interval_minutes": "30",
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
                    "interval_minutes": "30",
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
                    "interval_minutes": "30",
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
                    "interval_minutes": "45",
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
                    "interval_minutes": "45",
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
            self.assertEqual(updated["interval_minutes"], 45)
            self.assertEqual(updated["path"], "WIDE1-1,WIDE2-1")
            self.assertEqual(updated["symbol_table"], "\\")
            self.assertEqual(updated["is_enabled"], 1)

    def test_invalid_interval_is_rejected(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "VOICE",
                    "lifetime": "temporary",
                    "state": "live",
                    "latitude": "52.2297",
                    "longitude": "21.0122",
                    "symbol_table": "/",
                    "symbol_code": "r",
                    "interval_minutes": "7",
                    "path": "",
                    "comment": "",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Send interval must be one of: 5, 10, 15, 30, 45, 60 minutes.")

    def test_permanent_object_uses_fixed_111111z_timestamp_in_preview(self) -> None:
        with temporary_database():
            update_station_settings(
                {
                    "callsign": "SQ9MDD",
                    "ssid": "4",
                    "beacon_interface_id": "",
                    "beacon_comment": "",
                    "beacon_interval_minutes": "30",
                    "beacon_path": "",
                    "latitude": "52.2501",
                    "longitude": "20.9268",
                    "symbol_table": "/",
                    "symbol_code": ">",
                    "default_units": "metric",
                    "tx_enabled": None,
                }
            )
            success, error = safe_create_section_row(
                "objects",
                {
                    "name": "T2WARSPL",
                    "lifetime": "permanent",
                    "state": "live",
                    "latitude": "52.2501",
                    "longitude": "20.9268",
                    "symbol_table": "/",
                    "symbol_code": "I",
                    "interval_minutes": "30",
                    "path": "",
                    "comment": "http://hamspirit.pl:14501 Server T2",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one("SELECT id FROM aprs_objects WHERE name = ?", ("T2WARSPL",))
            assert row is not None
            decorated = get_section_row("objects", int(row["id"]))
            assert decorated is not None
            self.assertRegex(
                decorated["raw_frame_preview"],
                r"^SQ9MDD-4>APBOX0:;T2WARSPL \*111111z5215\.01N/02055\.61EIhttp://hamspirit\.pl:14501 Server T2$",
            )


class BulletinAndMessageFormTests(unittest.TestCase):
    def test_announcement_row_contains_target_and_raw_frame_preview(self) -> None:
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
                "bulletins",
                {
                    "message_kind": "announcement",
                    "bulletin_code": "A",
                    "group_name": "",
                    "interval_minutes": "15",
                    "path": "WIDE2-1",
                    "is_enabled": "1",
                    "message_text": "Net starts at 19:30 UTC",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)

            row = fetch_one("SELECT id FROM bulletins ORDER BY id DESC LIMIT 1")
            assert row is not None
            decorated = get_section_row("bulletins", int(row["id"]))
            assert decorated is not None
            self.assertEqual(decorated["target_display"], "BLNA")
            self.assertEqual(
                decorated["raw_frame_preview"],
            "SQ9XYZ-9>APBOX0,WIDE2-1::BLNA     :Net starts at 19:30 UTC",
            )

    def test_group_bulletin_preview_uses_bln_addressee(self) -> None:
        with temporary_database():
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "",
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
                "bulletins",
                {
                    "message_kind": "group_bulletin",
                    "bulletin_code": "1",
                    "group_name": "WX",
                    "interval_minutes": "30",
                    "path": "",
                    "message_text": "Wind 15 km/h",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)

            row = fetch_one("SELECT id FROM bulletins ORDER BY id DESC LIMIT 1")
            assert row is not None
            decorated = get_section_row("bulletins", int(row["id"]))
            assert decorated is not None
            self.assertEqual(decorated["target_display"], "BLN1WX")
            self.assertEqual(
                decorated["raw_frame_preview"],
            "SQ9XYZ>APBOX0::BLN1WX   :Wind 15 km/h",
            )

    def test_bulletin_text_longer_than_sixty_seven_characters_is_rejected(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "bulletins",
                {
                    "message_kind": "bulletin",
                    "bulletin_code": "1",
                    "interval_minutes": "30",
                    "path": "",
                    "message_text": "X" * 68,
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Message text must be 67 ASCII characters or fewer.")

    def test_bulletin_text_rejects_non_ascii_characters(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "bulletins",
                {
                    "message_kind": "bulletin",
                    "bulletin_code": "1",
                    "interval_minutes": "30",
                    "path": "",
                    "message_text": "Zażółć",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Message text may contain only printable ASCII characters.")

    def test_bulletin_text_allows_extended_printable_ascii_punctuation(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "bulletins",
                {
                    "message_kind": "bulletin",
                    "bulletin_code": "1",
                    "interval_minutes": "30",
                    "path": "",
                    "message_text": ''',.:?/\\()<>-_+=[]{}"'&$@#!''',
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)

    def test_bulletins_template_includes_counter_and_menu_label(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn('id="bulletins-message-count"', template_source)
        self.assertIn('id="bulletins-message-error"', template_source)

        base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
        self.assertNotIn("['igate']", base_source)
        self.assertNotIn("['digi-flows', 'igate', 'bulletins']", base_source)
        helpers_source = Path("app/template_helpers.py").read_text(encoding="utf-8")
        self.assertIn('"label": "Bulletins"', helpers_source)
        self.assertIn("Packet Routing", helpers_source)
        self.assertIn("iGATE settings", helpers_source)
        self.assertNotIn("Digi Settings", helpers_source)

    def test_igate_template_includes_realtime_diagnostics_bindings(self) -> None:
        template_source = Path("app/templates/igate_settings.html").read_text(encoding="utf-8")
        self.assertIn("api/igate/diagnostics", template_source)
        self.assertNotIn('id="igate-diag-last-sent-line"', template_source)
        self.assertNotIn('id="igate-diag-last-strict-line"', template_source)
        self.assertIn('id="igate-diag-tx-sent"', template_source)
        self.assertIn('id="igate-runtime-label"', template_source)
        router_source = Path("app/routers/pages.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("/api/igate/diagnostics")', router_source)


if __name__ == "__main__":
    unittest.main()
