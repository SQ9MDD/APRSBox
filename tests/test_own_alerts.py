import contextlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import execute, fetch_all, fetch_one, init_db, set_app_setting
from app.services.alarm_groups import (
    get_aprs_alarm_category_thresholds,
    save_aprs_alarm_category_thresholds,
    save_aprs_alarm_enabled,
    save_aprs_alarm_groups,
)
from app.services.alert_areas import (
    find_alarm_group_area_for_point,
    list_alarm_group_areas,
)
from app.services.aprs_warning_identity import (
    generate_aprs_group_warning_parts,
    parse_aprs_group_warning_content,
)
from app.services.own_alerts import (
    cancel_own_alert,
    create_own_alert,
    dispatch_due_own_alerts,
    expire_own_alerts,
    get_own_alert_compose_context,
    preview_own_alert,
    restore_own_alert_schedules,
    send_own_alert_now,
    validate_own_alert_payload,
)
from app.services.outbound import mark_outbound_job_failed
from app.services.warning_groups import list_supported_warning_groups
from app.services.traffic import process_normalized_tnc2_rx


NOW = datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc)


@contextlib.contextmanager
def temporary_database():
    with tempfile.TemporaryDirectory() as temp_dir:
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(Path(temp_dir) / "own-alerts.db")
        try:
            init_db()
            save_aprs_alarm_enabled(True)
            save_aprs_alarm_groups("PL-WARN,ES-WARN,NWS-WARN,LOCALWARN")
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SP5ABC', ssid = '1',
                    latitude = '52.2297', longitude = '21.0122',
                    tx_enabled = 1
                WHERE id = 1
                """
            )
            set_app_setting("station.tx.internal_mode", "1")
            yield
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def payload(**overrides):
    result = {
        "target_group": "PL-WARN",
        "area_code": "1465",
        "event_code": "TSTORM2",
        "validity_hours": 24,
        "repeat_interval_minutes": 30,
        "comment": "Silna burza",
    }
    result.update(overrides)
    return result


def family_level_payload(**overrides):
    result = {
        "target_group": "PL-WARN",
        "area_code": "1465",
        "event_family": "TSTORM",
        "severity_level": 2,
        "validity_hours": 24,
        "repeat_interval_minutes": 30,
        "comment": "Silna burza",
    }
    result.update(overrides)
    return result


def queued_payloads():
    return [
        json.loads(str(row["payload_json"]))
        for row in fetch_all("SELECT payload_json FROM outbound_jobs ORDER BY id")
    ]


class OwnAlertTests(unittest.TestCase):
    def test_supported_group_list_requires_complete_registered_profile(self):
        with temporary_database():
            self.assertEqual(
                list_supported_warning_groups(),
                ["PL-WARN", "ES-WARN"],
            )

    def test_area_lists_are_loaded_from_profile_geojson(self):
        pl_areas = list_alarm_group_areas("PL-WARN")
        es_areas = list_alarm_group_areas("ES-WARN")
        self.assertIn("1465", {area["code"] for area in pl_areas})
        madrid = next(area for area in es_areas if area["code"] == "722802")
        self.assertEqual(madrid["name"], "Metropolitana y Henares")
        self.assertIn("Madrid", madrid["parent"])

    def test_own_station_area_is_selected_with_point_in_polygon(self):
        with temporary_database():
            compose = get_own_alert_compose_context()
        pl = next(group for group in compose["groups"] if group["group"] == "PL-WARN")
        self.assertEqual(pl["default_area_code"], "1465")
        self.assertEqual(
            find_alarm_group_area_for_point(
                "ES-WARN",
                latitude=40.4168,
                longitude=-3.7038,
            )["code"],
            "722802",
        )

    def test_unknown_or_unmatched_station_position_leaves_area_empty(self):
        with temporary_database():
            execute("UPDATE station_settings SET latitude = '', longitude = '' WHERE id = 1")
            unknown = get_own_alert_compose_context()
            execute("UPDATE station_settings SET latitude = '0', longitude = '0' WHERE id = 1")
            unmatched = get_own_alert_compose_context()
        self.assertFalse(unknown["station_position_known"])
        self.assertTrue(all(not group["default_area_code"] for group in unknown["groups"]))
        self.assertTrue(unmatched["station_position_known"])
        self.assertTrue(all(not group["default_area_code"] for group in unmatched["groups"]))

    def test_backend_rejects_unknown_area_group_and_event(self):
        with temporary_database():
            for invalid in (
                payload(area_code="9999"),
                payload(target_group="LOCALWARN"),
                payload(event_code="ALIENS3"),
            ):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        validate_own_alert_payload(invalid, now=NOW, require_tx=False)

    def test_backend_accepts_separate_hazard_and_severity_fields(self):
        with temporary_database():
            validated = validate_own_alert_payload(
                family_level_payload(),
                now=NOW,
                require_tx=False,
            )
        self.assertEqual(validated["event_code"], "TSTORM2")
        self.assertEqual(validated["event_family"], "TSTORM")
        self.assertEqual(validated["severity_level"], 2)

    def test_generator_builds_single_and_multipart_messages_with_one_id(self):
        single = generate_aprs_group_warning_parts(
            expiry="031000z",
            event_code="TSTORM2",
            alert_id="A7F3",
            area_code="1465",
            comment="Krótko",
        )
        multipart = generate_aprs_group_warning_parts(
            expiry="031000z",
            event_code="TSTORM2",
            alert_id="A7F3",
            area_code="1465",
            comment="A" * 100,
        )
        self.assertEqual(len(single), 1)
        self.assertGreater(len(multipart), 1)
        self.assertTrue(all(len(part["payload"]) <= 67 for part in multipart))
        self.assertTrue(
            all(
                parse_aprs_group_warning_content(part["payload"])["logical_alert_id"] == "A7F3"
                for part in multipart
            )
        )

    def test_parser_keeps_area_when_legacy_comment_follows_it(self):
        parsed = parse_aprs_group_warning_content(
            "031000z,TSTORM2,@A7F3,1/1,1465 Silna burza, mozliwe podtopienia{AAAAA"
        )
        self.assertEqual(parsed["area_code"], "1465")
        self.assertEqual(parsed["area_codes"], ["1465"])
        self.assertEqual(parsed["comment"], "Silna burza,mozliwe podtopienia")
        parsed_comma_comment = parse_aprs_group_warning_content(
            "031000z,TSTORM2,@A7F3,1/1,1465,LOUD TEXT,RAIN{AAAAA"
        )
        self.assertEqual(parsed_comma_comment["area_codes"], ["1465"])
        self.assertEqual(parsed_comma_comment["comment"], "LOUD TEXT,RAIN")

    def test_dynamic_comment_limit_counts_headers_and_parts(self):
        with temporary_database():
            short = preview_own_alert(payload(comment="A"), now=NOW)
            long = preview_own_alert(payload(comment="A" * 100), now=NOW)
            capacity = int(short["remaining_characters"]) + 1
            at_limit = preview_own_alert(payload(comment="A" * capacity), now=NOW)
            with self.assertRaises(ValueError):
                preview_own_alert(payload(comment="A" * (capacity + 1)), now=NOW)
        self.assertEqual(
            short["remaining_characters"] - long["remaining_characters"],
            99,
        )
        self.assertEqual(short["parts_total"], 1)
        self.assertGreater(long["parts_total"], 1)
        self.assertEqual(at_limit["remaining_characters"], 0)
        self.assertEqual(at_limit["parts_total"], 9)

    def test_default_validity_is_exactly_24_hours(self):
        with temporary_database():
            preview = preview_own_alert(payload(), now=NOW)
        self.assertEqual(
            preview["valid_until"],
            (NOW + timedelta(hours=24)).isoformat(),
        )
        self.assertEqual(preview["expiry"], "031000z")

    def test_scheduler_accepts_15_30_and_60_minute_intervals(self):
        with temporary_database():
            rows = []
            for offset, interval in enumerate((15, 30, 60)):
                created = create_own_alert(
                    payload(
                        repeat_interval_minutes=interval,
                        event_code=("TSTORM1", "WIND2", "RAIN3")[offset],
                    ),
                    now=NOW + timedelta(seconds=offset),
                )
                rows.append(fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],)))
        self.assertEqual(
            [row["next_transmission_at"] for row in rows],
            [
                (NOW + timedelta(minutes=15)).isoformat(),
                (NOW + timedelta(seconds=1, minutes=30)).isoformat(),
                (NOW + timedelta(seconds=2, minutes=60)).isoformat(),
            ],
        )

    def test_repeat_and_send_now_keep_id_and_message_ids(self):
        with temporary_database():
            created = create_own_alert(payload(comment="A" * 80), now=NOW)
            first = queued_payloads()
            self.assertTrue(send_own_alert_now(created["id"], now=NOW + timedelta(minutes=1))[0])
            all_payloads = queued_payloads()
            repeated = all_payloads[len(first) :]
            row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
        self.assertEqual(
            [item["message_text"] for item in repeated],
            [item["message_text"] for item in first],
        )
        self.assertTrue(all(f"@{created['alert_id']}" in item["message_text"] for item in repeated))
        self.assertEqual(
            row["next_transmission_at"],
            (NOW + timedelta(minutes=31)).isoformat(),
        )

    def test_restart_restores_future_schedule_without_backlog(self):
        with temporary_database():
            created = create_own_alert(payload(), now=NOW)
            jobs_before = len(fetch_all("SELECT id FROM outbound_jobs"))
            execute(
                "UPDATE own_aprs_alerts SET next_transmission_at = ? WHERE id = ?",
                ((NOW - timedelta(hours=3)).isoformat(), created["id"]),
            )
            self.assertEqual(restore_own_alert_schedules(now=NOW), 1)
            row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
            jobs_after = len(fetch_all("SELECT id FROM outbound_jobs"))
        self.assertGreater(row["next_transmission_at"], NOW.isoformat())
        self.assertEqual(jobs_before, jobs_after)

    def test_due_scheduler_sends_only_once_after_multiple_missed_terms(self):
        with temporary_database():
            created = create_own_alert(payload(), now=NOW)
            execute(
                "UPDATE own_aprs_alerts SET next_transmission_at = ? WHERE id = ?",
                ((NOW + timedelta(minutes=30)).isoformat(), created["id"]),
            )
            parts = int(fetch_one("SELECT parts_total FROM own_aprs_alerts WHERE id = ?", (created["id"],))["parts_total"])
            jobs_before = len(fetch_all("SELECT id FROM outbound_jobs"))
            sent = dispatch_due_own_alerts(now=NOW + timedelta(hours=5))
            jobs_after = len(fetch_all("SELECT id FROM outbound_jobs"))
            row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
        self.assertEqual(sent, 1)
        self.assertEqual(jobs_after - jobs_before, parts)
        self.assertGreater(row["next_transmission_at"], (NOW + timedelta(hours=5)).isoformat())

    def test_expiration_stops_schedule(self):
        with temporary_database():
            created = create_own_alert(payload(validity_hours=1), now=NOW)
            self.assertEqual(expire_own_alerts(now=NOW + timedelta(hours=2)), 1)
            row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
        self.assertEqual(row["status"], "expired")
        self.assertIsNone(row["next_transmission_at"])

    def test_unavailable_tx_records_error_and_advances_repeat_schedule(self):
        with temporary_database():
            created = create_own_alert(payload(), now=NOW)
            execute("UPDATE station_settings SET tx_enabled = 0 WHERE id = 1")
            execute(
                "UPDATE own_aprs_alerts SET next_transmission_at = ? WHERE id = ?",
                ((NOW + timedelta(minutes=30)).isoformat(), created["id"]),
            )
            dispatched = dispatch_due_own_alerts(now=NOW + timedelta(minutes=30))
            row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
        self.assertEqual(dispatched, 0)
        self.assertEqual(row["status"], "error")
        self.assertEqual(
            row["next_transmission_at"],
            (NOW + timedelta(minutes=60)).isoformat(),
        )
        self.assertIn("disabled", row["last_error"].lower())

    def test_cancel_uses_same_identity_and_stops_future_transmissions(self):
        with temporary_database():
            created = create_own_alert(payload(), now=NOW)
            self.assertTrue(cancel_own_alert(created["id"], now=NOW + timedelta(minutes=2))[0])
            cancel_payload = queued_payloads()[-1]["message_text"]
            row = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
            jobs_before = len(fetch_all("SELECT id FROM outbound_jobs"))
            dispatched = dispatch_due_own_alerts(now=NOW + timedelta(days=1))
            jobs_after = len(fetch_all("SELECT id FROM outbound_jobs"))
        parsed = parse_aprs_group_warning_content(cancel_payload)
        self.assertTrue(parsed["is_cancel"])
        self.assertEqual(parsed["logical_alert_id"], created["alert_id"])
        self.assertEqual(row["status"], "cancelled")
        self.assertIsNone(row["next_transmission_at"])
        self.assertEqual(dispatched, 0)
        self.assertEqual(jobs_before, jobs_after)

    def test_failed_cancel_stays_stopped_and_can_retry_with_same_cancel_frame(self):
        with temporary_database():
            created = create_own_alert(payload(), now=NOW)
            self.assertTrue(cancel_own_alert(created["id"], now=NOW + timedelta(minutes=1))[0])
            first_cancel = queued_payloads()[-1]["message_text"]
            cancel_job = fetch_one(
                """
                SELECT outbound_job_id
                FROM own_aprs_alert_tx_jobs
                WHERE own_alert_id = ? AND dispatch_kind = 'cancel'
                ORDER BY outbound_job_id DESC
                LIMIT 1
                """,
                (created["id"],),
            )
            mark_outbound_job_failed(int(cancel_job["outbound_job_id"]), "Radio unavailable")
            failed = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
            self.assertEqual(restore_own_alert_schedules(now=NOW + timedelta(hours=1)), 0)
            self.assertFalse(send_own_alert_now(created["id"], now=NOW + timedelta(hours=1))[0])
            self.assertTrue(cancel_own_alert(created["id"], now=NOW + timedelta(hours=1))[0])
            repeated_cancel = queued_payloads()[-1]["message_text"]
            retried = fetch_one("SELECT * FROM own_aprs_alerts WHERE id = ?", (created["id"],))
        self.assertEqual(failed["status"], "error")
        self.assertIsNone(failed["next_transmission_at"])
        self.assertIsNotNone(failed["cancelled_at"])
        self.assertEqual(first_cancel, repeated_cancel)
        self.assertEqual(retried["status"], "cancelled")

    def test_other_sender_cannot_cancel_alarm(self):
        with temporary_database():
            created = create_own_alert(payload(), now=NOW)
            success, _ = cancel_own_alert(
                created["id"],
                sender_callsign="SP9OTHER",
                now=NOW + timedelta(minutes=1),
            )
            row = fetch_one("SELECT status, cancelled_at FROM own_aprs_alerts WHERE id = ?", (created["id"],))
        self.assertFalse(success)
        self.assertEqual(row["status"], "active")
        self.assertIsNone(row["cancelled_at"])

    def test_received_cancel_is_scoped_by_sender_group_and_logical_id(self):
        with temporary_database():
            thresholds = get_aprs_alarm_category_thresholds()
            for values in thresholds.values():
                values["alerts"] = 1
            save_aprs_alarm_category_thresholds(thresholds)
            frames = (
                "SP5AAA>APBOX0::PL-WARN  :031000z,TSTORM2,@A7F3,1/1,1465{AAAAA",
                "SP5BBB>APBOX0::PL-WARN  :031000z,TSTORM2,@A7F3,1/1,1465{BBBBB",
                "SP5AAA>APBOX0::PL-WARN  :031000z,CANCEL,@A7F3,1/1,1465{CCCCC",
            )
            for offset, frame in enumerate(frames):
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        frame,
                        source="TNC",
                        timestamp=(NOW + timedelta(minutes=offset)).isoformat(),
                    )
                )
            rows = fetch_all(
                """
                SELECT source_callsign, event_code, is_active, cancelled_at
                FROM aprs_alerts
                ORDER BY source_callsign
                """
            )
        self.assertEqual(
            [(row["source_callsign"], int(row["is_active"])) for row in rows],
            [("SP5AAA", 0), ("SP5BBB", 1)],
        )
        self.assertIsNotNone(rows[0]["cancelled_at"])
        self.assertIsNone(rows[1]["cancelled_at"])
        self.assertEqual(rows[0]["event_code"], "TSTORM2")

    def test_alert_page_and_structured_api_expose_compose_workflow(self):
        from fastapi.testclient import TestClient

        from app.dependencies import get_current_user
        from app.main import app
        from app.models import UserIdentity

        with temporary_database():
            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=1,
                username="admin",
                role="admin",
                is_active=True,
            )
            try:
                with TestClient(app) as client:
                    page = client.get("/alerts")
                    areas = client.get("/api/alerts/send/areas", params={"group": "PL-WARN"})
                    preview = client.post("/api/alerts/send/preview", json=payload())
                    rejected = client.post(
                        "/api/alerts/send/preview",
                        json=payload(target_group="LOCALWARN"),
                    )
                    sent = client.post("/api/alerts/send", json=payload())
                    refreshed_before_cancel = client.get("/alerts")
                    cancelled = client.post(
                        f"/alerts/own/{sent.json()['id']}/cancel",
                        follow_redirects=False,
                    )
                    cancelled_status = fetch_one(
                        "SELECT status FROM own_aprs_alerts WHERE id = ?",
                        (sent.json()["id"],),
                    )["status"]
                    refreshed = client.get("/alerts")
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(page.status_code, 200)
        self.assertLess(page.text.index("Send alarm"), page.text.index("My active alarms"))
        self.assertLess(page.text.index("My active alarms"), page.text.index("alerts-page-panel"))
        self.assertIn('id="own-alert-hazard"', page.text)
        self.assertIn('id="own-alert-level"', page.text)
        self.assertNotIn('id="own-alert-area-search"', page.text)
        self.assertEqual(areas.status_code, 200)
        self.assertIn("1465", {area["code"] for area in areas.json()["areas"]})
        self.assertEqual(preview.status_code, 200)
        self.assertIn("remaining_characters", preview.json())
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(cancelled.status_code, 303)
        self.assertEqual(cancelled_status, "cancelled")
        self.assertIn(sent.json()["alert_id"], refreshed_before_cancel.text)


if __name__ == "__main__":
    unittest.main()
