import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import fetch_one, init_db, set_app_setting
from app.services.notifications import (
    _send_notification_event,
    build_aprs_message_event,
    evaluate_radar_notifications,
    get_notifications_page_data,
    normalize_notification_distance_m,
    pattern_matches_callsign,
    queue_aprs_message_notification,
    queue_radar_notifications,
    safe_save_notification_radar_rule,
    safe_save_notification_transport,
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


class NotificationTests(unittest.TestCase):
    def test_pattern_matching_supports_wildcards_and_exact_matches(self) -> None:
        self.assertTrue(pattern_matches_callsign("*", "SQ5ABC-1"))
        self.assertTrue(pattern_matches_callsign("SQ6ODL*", "SQ6ODL-9"))
        self.assertTrue(pattern_matches_callsign("SQ6ODL-*", "SQ6ODL-9"))
        self.assertFalse(pattern_matches_callsign("SQ6ODL-*", "SQ6ODLA"))
        self.assertTrue(pattern_matches_callsign("SQ5WLA-9", "SQ5WLA-9"))

    def test_zero_distance_matches_any_station_distance(self) -> None:
        with temporary_database():
            self.assertEqual(normalize_notification_distance_m("0"), 0)
            ok, error, rule_id = safe_save_notification_radar_rule({"enabled": True, "pattern": "*", "distance_m": 0})
            self.assertTrue(ok, error)
            assert rule_id is not None
            set_app_setting("radar_enabled", "1")

            with patch(
                "app.services.notifications.get_station_settings",
                return_value={"callsign": "SQ0BOX", "ssid": "1", "latitude": "50.0", "longitude": "19.0"},
            ), patch(
                "app.services.notifications.get_visible_station_snapshots",
                return_value=[
                    {
                        "origin": "heard",
                        "display_callsign": "SQ6ODL-9",
                        "latitude": "60.0",
                        "longitude": "29.0",
                    }
                ],
            ):
                events = evaluate_radar_notifications(timestamp="2026-01-01T00:00:00+00:00")

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "radar_station_match")
            state = fetch_one(
                "SELECT is_inside FROM notification_radar_state WHERE rule_id = ? AND station_key = ?",
                (rule_id, "SQ6ODL-9"),
            )
            assert state is not None
            self.assertEqual(int(state["is_inside"]), 1)

    def test_radar_state_transitions_send_once_and_reset(self) -> None:
        with temporary_database():
            ok, error, rule_id = safe_save_notification_radar_rule({"enabled": True, "pattern": "SQ6ODL*", "distance_m": 5000})
            self.assertTrue(ok, error)
            assert rule_id is not None
            set_app_setting("radar_enabled", "1")

            station_settings = {"callsign": "SQ0BOX", "ssid": "1", "latitude": "50.0", "longitude": "19.0"}
            snapshot = {
                "origin": "heard",
                "display_callsign": "SQ6ODL-9",
                "latitude": "50.01",
                "longitude": "19.01",
            }
            with patch("app.services.notifications.get_station_settings", return_value=station_settings), patch(
                "app.services.notifications.get_visible_station_snapshots"
            ) as snapshots_mock:
                snapshots_mock.return_value = [snapshot]
                first_events = evaluate_radar_notifications(timestamp="2026-01-01T00:00:00+00:00")
                snapshots_mock.return_value = [snapshot]
                second_events = evaluate_radar_notifications(timestamp="2026-01-01T00:01:00+00:00")
                snapshots_mock.return_value = []
                third_events = evaluate_radar_notifications(timestamp="2026-01-01T00:02:00+00:00")
                snapshots_mock.return_value = [snapshot]
                fourth_events = evaluate_radar_notifications(timestamp="2026-01-01T00:03:00+00:00")

            self.assertEqual(len(first_events), 1)
            self.assertEqual(len(second_events), 0)
            self.assertEqual(len(third_events), 0)
            self.assertEqual(len(fourth_events), 1)

            state = fetch_one(
                "SELECT is_inside FROM notification_radar_state WHERE rule_id = ? AND station_key = ?",
                (rule_id, "SQ6ODL-9"),
            )
            assert state is not None
            self.assertEqual(int(state["is_inside"]), 1)

    def test_radar_ignores_my_station_and_wx_pairs(self) -> None:
        with temporary_database():
            ok, error, rule_id = safe_save_notification_radar_rule({"enabled": True, "pattern": "*", "distance_m": 0})
            self.assertTrue(ok, error)
            assert rule_id is not None
            set_app_setting("radar_enabled", "1")

            station_settings = {"callsign": "SQ0BOX", "ssid": "1", "latitude": "50.0", "longitude": "19.0"}
            snapshots = [
                {"origin": "heard", "display_callsign": "SQ0BOX-1", "latitude": "50.01", "longitude": "19.01"},
                {"origin": "heard", "display_callsign": "SQ0BOX-2", "latitude": "50.01", "longitude": "19.01"},
            ]
            with patch("app.services.notifications.get_station_settings", return_value=station_settings), patch(
                "app.services.notifications.get_wx_config",
                return_value={"enabled": True, "full_callsign": "SQ0BOX-2"},
            ), patch("app.services.notifications.get_visible_station_snapshots", return_value=snapshots):
                events = evaluate_radar_notifications(timestamp="2026-01-01T00:00:00+00:00")

            self.assertEqual(events, [])
            state = fetch_one(
                "SELECT COUNT(*) AS total FROM notification_radar_state WHERE rule_id = ?",
                (rule_id,),
            )
            assert state is not None
            self.assertEqual(int(state["total"]), 0)

    def test_radar_evaluates_local_tx_frames_from_other_ssids(self) -> None:
        with temporary_database():
            ok, error, rule_id = safe_save_notification_radar_rule({"enabled": True, "pattern": "*", "distance_m": 0})
            self.assertTrue(ok, error)
            assert rule_id is not None
            set_app_setting("radar_enabled", "1")

            station_settings = {"callsign": "SQ0BOX", "ssid": "1", "latitude": "50.0", "longitude": "19.0"}
            snapshots = [
                {"origin": "local_tx", "display_callsign": "SQ0BOX-7", "latitude": "50.01", "longitude": "19.01"},
            ]
            with patch("app.services.notifications.get_station_settings", return_value=station_settings), patch(
                "app.services.notifications.get_wx_config",
                return_value={"enabled": False, "full_callsign": "SQ0BOX"},
            ), patch("app.services.notifications.get_visible_station_snapshots", return_value=snapshots):
                events = evaluate_radar_notifications(timestamp="2026-01-01T00:00:00+00:00")

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["data"]["station"], "SQ0BOX-7")

    def test_aprs_message_event_omits_content_when_disabled(self) -> None:
        event = build_aprs_message_event(
            sender="SQ0ABC-7",
            destination="APRS",
            text="Secret payload",
            include_content=False,
            message_id=123,
            message_number="01",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        self.assertEqual(event["event_type"], "aprs_message")
        self.assertEqual(event["data"]["source"], "SQ0ABC-7")
        self.assertEqual(event["data"]["destination"], "APRS")
        self.assertFalse(event["data"]["content_included"])
        self.assertIsNone(event["data"]["text"])

    def test_disabled_transport_is_not_sent(self) -> None:
        with temporary_database():
            ok, error, transport_id = safe_save_notification_transport(
                {"name": "Disabled webhook", "transport_type": "webhook", "enabled": False}
            )
            self.assertTrue(ok, error)
            assert transport_id is not None
            set_app_setting("messages_enabled", "1")
            set_app_setting("messages_include_content", "1")
            event = build_aprs_message_event(
                sender="SQ0ABC-7",
                destination="APRS",
                text="Hello",
                include_content=True,
                timestamp="2026-01-01T00:00:00+00:00",
            )
            with patch("app.services.notifications._deliver_event_to_transport") as deliver_mock:
                _send_notification_event(event)
            deliver_mock.assert_not_called()

    def test_telegram_bot_token_is_loaded_for_editing(self) -> None:
        with temporary_database():
            ok, error, transport_id = safe_save_notification_transport(
                {
                    "name": "Telegram transport",
                    "transport_type": "telegram",
                    "enabled": True,
                    "bot_token": "123456:ABCDEF",
                    "chat_id": "-100123",
                }
            )
            self.assertTrue(ok, error)
            assert transport_id is not None

            page_data = get_notifications_page_data(edit_transport_id=transport_id)
            self.assertEqual(page_data["notification_transport_form"]["bot_token"], "123456:ABCDEF")

    def test_disabled_message_and_radar_notifications_do_not_queue(self) -> None:
        with temporary_database():
            set_app_setting("messages_enabled", "0")
            set_app_setting("radar_enabled", "0")
            with patch("app.services.notifications._NOTIFICATION_EXECUTOR.submit") as submit_mock:
                queue_aprs_message_notification(sender="SQ0ABC-7", destination="APRS", text="Hello")
                queue_radar_notifications()
            submit_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
