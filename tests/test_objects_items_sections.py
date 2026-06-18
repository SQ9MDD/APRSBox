import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.sections import SECTION_DEFINITIONS
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
    def test_object_item_translation_keys_are_present_in_en_pl_es(self) -> None:
        required_keys = [
            "Item List",
            "Active from (UTC)",
            "Active until (UTC)",
            "Active from",
            "Active until",
            "Active for (hours)",
            "Manual: Leave empty to keep sending until manually disabled. Scheduled: required end. Recurring: optional repeat end.",
            "Active now",
            "Inactive now",
            "Activation",
            "Recurring",
            "Activation summary",
            "Activation schedule controls when sending is allowed. Send interval remains separate.",
            "Manual activation.",
            "Manual activation. Valid until: {validUntil} UTC.",
            "Active from {fromDate} UTC to {toDate} UTC.",
            "Active every {value} {unit} from {fromDate} UTC for {duration}.",
            "Every {value} {unit}",
            "First activation (UTC)",
            "Delete this bulletin?",
            "Delete this object?",
            "Object transmission is not implemented yet. APRS object names are stored unpadded here, but will later be encoded into the fixed 9-character APRS object field with an automatic timestamp.",
            "Prepare APRS object records with protocol-safe names, status, position, symbol and future RF path.",
            "Repeat until (UTC)",
            "Next activation: {date} UTC.",
            "Scheduled",
            "Scheduled: active now",
            "Scheduled: inactive",
            "Scheduled: starts {date} UTC",
            "Announcement",
            "Bulletins / Announcements",
            "Bulletins / Announcements List",
            "Add Bulletin / Announcement",
            "Edit Bulletin / Announcement",
            "General Bulletin",
            "Group Bulletin",
            "Prepare APRS message-format frames for bulletins and announcements.",
            "Type must be bulletin, announcement or group bulletin.",
            "Use <code>0-9</code> for general/group bulletins and <code>A-Z</code> for announcements.",
            "{prefix}: active now",
            "{prefix}: inactive",
            "{prefix}: next {date} UTC",
            "Repeat until {repeatUntil} UTC.",
            "Recurring schedule has no end date.",
            "Record will be active for more than 24h per cycle.",
            "WIDE2-2 with interval below 60m is not recommended.",
            "Direct path is recommended for local/simple records.",
            "Day(s)",
            "Week(s)",
            "Month(s)",
            "Year(s)",
            "Select",
        ]
        self.assertEqual(SECTION_DEFINITIONS["items"].list_title, "Item List")
        for language in ("en", "pl", "es", "tlh"):
            catalog = json.loads((Path("app/languages") / f"{language}.json").read_text())
            for key in required_keys:
                self.assertIn(key, catalog, msg=f"Missing {key!r} in {language}.json")

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

    def test_object_edit_post_redirects_back_to_edit_page_with_data(self) -> None:
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
                    "path": "WIDE2-2",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one("SELECT id FROM aprs_objects WHERE name = ?", ("VOICE",))
            assert row is not None

            try:
                from fastapi.testclient import TestClient
            except ModuleNotFoundError:
                self.skipTest("fastapi is not installed in this environment")

            from app.dependencies import get_current_user
            from app.main import app
            from app.models import UserIdentity

            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=1,
                username="tester",
                role="admin",
                is_active=True,
            )
            try:
                client = TestClient(app)
                response = client.post(
                    "/objects",
                    data={
                        "record_id": str(int(row["id"])),
                        "name": "VOICE",
                        "lifetime": "temporary",
                        "state": "live",
                        "latitude": "52.2297",
                        "longitude": "21.0122",
                        "symbol_table": "/",
                        "symbol_code": "r",
                        "interval_minutes": "30",
                        "path": "WIDE2-2",
                        "comment": "Updated voice repeater",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("/objects?edit=", str(response.url))
                self.assertIn('value="VOICE"', response.text)
                self.assertIn("Updated voice repeater", response.text)
                self.assertIn("Edit Object", response.text)
            finally:
                app.dependency_overrides.pop(get_current_user, None)

    def test_object_manual_send_queues_force_send_job(self) -> None:
        with temporary_database():
            update_station_settings(
                {
                    "callsign": "SQ9XYZ",
                    "ssid": "9",
                    "beacon_interface_id": "1",
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
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, enabled, notes, created_at, updated_at)
                VALUES ('Test TNC', 'TCP', '2m', '127.0.0.1:9001', 1, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
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

            try:
                from fastapi.testclient import TestClient
            except ModuleNotFoundError:
                self.skipTest("fastapi is not installed in this environment")

            from app.dependencies import get_current_user
            from app.main import app
            from app.models import UserIdentity

            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=1,
                username="tester",
                role="admin",
                is_active=True,
            )
            try:
                client = TestClient(app)
                response = client.post(f"/settings/objects/{int(row['id'])}/send")
                self.assertEqual(response.status_code, 200)
                job = fetch_one(
                    "SELECT payload_json, status FROM outbound_jobs WHERE kind = 'object' ORDER BY id DESC LIMIT 1"
                )
                assert job is not None
                payload = json.loads(job["payload_json"])
                self.assertTrue(payload["force_send"])
                self.assertEqual(payload["trigger"], "manual")
                self.assertEqual(job["status"], "queued")
            finally:
                app.dependency_overrides.pop(get_current_user, None)

    def test_object_preview_uses_overlay_for_alternate_symbol_table(self) -> None:
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
                    "symbol_table": "\\",
                    "symbol_code": "r",
                    "symbol_overlay": "9",
                    "interval_minutes": "30",
                    "path": "",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one("SELECT id, symbol_overlay FROM aprs_objects WHERE name = ?", ("VOICE",))
            assert row is not None
            self.assertEqual(row["symbol_overlay"], "9")
            decorated = get_section_row("objects", int(row["id"]))
            assert decorated is not None
            self.assertRegex(
                decorated["raw_frame_preview"],
                r"^SQ9XYZ-9>APBOX0:;VOICE {4}\*[0-9]{6}z5213\.78N902100\.73ErLocal voice repeater$",
            )

    def test_object_record_accepts_optional_valid_until_utc(self) -> None:
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
                    "valid_until_utc": "2026-12-31T23:45",
                    "path": "WIDE2-2",
                    "is_enabled": "1",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one("SELECT valid_until_utc FROM aprs_objects WHERE name = ?", ("VOICE",))
            assert row is not None
            self.assertEqual(row["valid_until_utc"], "2026-12-31 23:45")

    def test_object_manual_form_reuses_active_until_as_valid_until(self) -> None:
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
                    "activation_mode": "manual",
                    "active_until_utc": "2026-12-31T23:45",
                    "path": "",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one("SELECT id, valid_until_utc, active_until_utc FROM aprs_objects WHERE name = ?", ("VOICE",))
            assert row is not None
            self.assertEqual(row["valid_until_utc"], "2026-12-31 23:45")
            self.assertEqual(row["active_until_utc"], "2026-12-31 23:45")
            decorated = get_section_row("objects", int(row["id"]))
            assert decorated is not None
            self.assertEqual(decorated["activation_form_active_until_utc"], "2026-12-31 23:45")

    def test_object_recurring_form_reuses_active_dates_for_storage_model(self) -> None:
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
                    "activation_mode": "recurring",
                    "active_from_utc": "2026-06-09T18:00",
                    "active_until_utc": "2026-12-31T23:45",
                    "recurrence_duration_minutes": "180",
                    "recurrence_interval_value": "1",
                    "recurrence_interval_unit": "week",
                    "path": "",
                    "comment": "Local voice repeater",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one(
                """
                SELECT id, active_from_utc, active_until_utc, first_activation_utc, recurrence_until_utc
                FROM aprs_objects
                WHERE name = ?
                """,
                ("VOICE",),
            )
            assert row is not None
            self.assertEqual(row["active_from_utc"], "2026-06-09 18:00")
            self.assertEqual(row["active_until_utc"], "2026-12-31 23:45")
            self.assertEqual(row["first_activation_utc"], "2026-06-09 18:00")
            self.assertEqual(row["recurrence_until_utc"], "2026-12-31 23:45")
            decorated = get_section_row("objects", int(row["id"]))
            assert decorated is not None
            self.assertEqual(decorated["activation_form_active_from_utc"], "2026-06-09 18:00")
            self.assertEqual(decorated["activation_form_active_until_utc"], "2026-12-31 23:45")

    def test_object_valid_until_utc_requires_yyyy_mm_dd_format(self) -> None:
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
                    "valid_until_utc": "31-12-2026",
                    "path": "",
                    "comment": "Local voice repeater",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Valid until date must use YYYY-MM-DD or YYYY-MM-DD HH:MM format.")

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
        self.assertIn("Objects TX Log", template_source)
        self.assertIn("No object outbound jobs yet.", template_source)
        self.assertIn("data-clear-date-target", template_source)
        self.assertIn("Leave empty to keep sending until manually disabled.", template_source)
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

    def test_switching_item_symbol_table_to_primary_clears_overlay(self) -> None:
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
            created, error = safe_create_section_row(
                "items",
                {
                    "name": "AID01",
                    "state": "live",
                    "latitude": "52.0",
                    "longitude": "21.0",
                    "symbol_table": "\\",
                    "symbol_code": "A",
                    "symbol_overlay": "B",
                    "interval_minutes": "30",
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
                    "state": "live",
                    "latitude": "52.0",
                    "longitude": "21.0",
                    "symbol_table": "/",
                    "symbol_code": "A",
                    "symbol_overlay": "C",
                    "interval_minutes": "30",
                    "path": "",
                    "comment": "Aid station",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(update_error)
            updated_row = fetch_one("SELECT symbol_table, symbol_overlay FROM aprs_items WHERE id = ?", (int(row["id"]),))
            assert updated_row is not None
            self.assertEqual(updated_row["symbol_table"], "/")
            self.assertIsNone(updated_row["symbol_overlay"])

    def test_item_without_overlay_remains_valid_alternate_symbol(self) -> None:
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
            execute(
                """
                INSERT INTO aprs_items(
                    name, state, is_enabled, interval_minutes, latitude, longitude,
                    symbol_table, symbol_code, path, comment, updated_at
                )
                VALUES (?, 'live', 1, 30, '52.0', '21.0', '\\', 'A', '', 'Aid station', '2026-01-01T00:00:00+00:00')
                """,
                ("AID01",),
            )
            row = fetch_one("SELECT id FROM aprs_items WHERE name = ?", ("AID01",))
            assert row is not None
            decorated = get_section_row("items", int(row["id"]))
            assert decorated is not None
            self.assertEqual(decorated["symbol_overlay"], "")
            self.assertIn("5200.00N\\02100.00EA", decorated["raw_frame_preview"])

    def test_overlay_rejects_invalid_character_for_alternate_table(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "items",
                {
                    "name": "AID01",
                    "state": "live",
                    "latitude": "52.0",
                    "longitude": "21.0",
                    "symbol_table": "\\",
                    "symbol_code": "A",
                    "symbol_overlay": "*",
                    "interval_minutes": "30",
                    "path": "",
                    "comment": "Aid station",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Symbol overlay must be one of: None, 0-9, A-Z.")

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

    def test_bulletin_record_accepts_optional_valid_until_utc(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "bulletins",
                {
                    "message_kind": "bulletin",
                    "bulletin_code": "1",
                    "group_name": "",
                    "interval_minutes": "30",
                    "valid_until_utc": "2026-12-31 23:45",
                    "path": "",
                    "message_text": "Wind 15 km/h",
                },
            )
            self.assertTrue(success)
            self.assertIsNone(error)
            row = fetch_one("SELECT valid_until_utc FROM bulletins ORDER BY id DESC LIMIT 1")
            assert row is not None
            self.assertEqual(row["valid_until_utc"], "2026-12-31 23:45")

    def test_bulletin_valid_until_utc_requires_yyyy_mm_dd_format(self) -> None:
        with temporary_database():
            success, error = safe_create_section_row(
                "bulletins",
                {
                    "message_kind": "bulletin",
                    "bulletin_code": "1",
                    "group_name": "",
                    "interval_minutes": "30",
                    "valid_until_utc": "31-12-2026",
                    "path": "",
                    "message_text": "Wind 15 km/h",
                },
            )
            self.assertFalse(success)
            self.assertEqual(error, "Valid until date must use YYYY-MM-DD or YYYY-MM-DD HH:MM format.")

    def test_bulletins_template_includes_counter_and_menu_label(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn('id="bulletins-message-count"', template_source)
        self.assertIn('id="bulletins-message-error"', template_source)
        self.assertIn("datetime-local", template_source)
        self.assertIn("Bulletins TX Log", template_source)
        self.assertIn("No bulletin outbound jobs yet.", template_source)

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
