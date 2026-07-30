import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, fetch_all, fetch_one, get_app_setting, init_db, set_app_setting
from app.services.alerts import list_alerts
from app.services.alarm_groups import (
    APRS_ALARM_GROUPS_SETTING_KEY,
    DEFAULT_APRS_ALARM_GROUPS,
    build_automatic_aprsis_alarm_filter,
    build_effective_aprsis_filter,
    get_aprs_alarm_groups,
    normalize_aprs_alarm_groups,
    save_aprs_alarm_groups,
)
from app.services.aprsis import (
    AprsisClientService,
    build_aprsis_login_line,
    get_enabled_aprsis_interface,
)
from app.services.aprs_warning_identity import parse_aprs_group_warning_content
from app.services.messages import (
    DEFAULT_MESSAGE_TARGET_GROUPS,
    get_effective_message_target_groups,
    get_message_settings,
    save_message_settings,
)
from app.services.content import traffic_snapshot
from app.services.traffic import process_normalized_tnc2_rx


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SP0BOX', ssid = '1', updated_at = '2026-01-01T00:00:00+00:00'
                WHERE id = 1
                """
            )
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def insert_aprsis_interface(user_filter: str) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, enabled, notes, created_at, updated_at
        )
        VALUES (
            'Internet RX', 'APRSIS', '', ?, 1, '',
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
        )
        """,
        (user_filter,),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = 'Internet RX'")
    assert row is not None
    return int(row["id"])


class AprsAlarmGroupConfigurationTests(unittest.TestCase):
    def test_default_alarm_group_is_pl_warn_and_standard_groups_are_unchanged(self) -> None:
        with temporary_database():
            self.assertEqual(DEFAULT_APRS_ALARM_GROUPS, ("PL-WARN",))
            self.assertEqual(get_aprs_alarm_groups(), ["PL-WARN"])
            self.assertEqual(DEFAULT_MESSAGE_TARGET_GROUPS, ("ALL", "QST", "CQ"))
            self.assertEqual(get_message_settings()["target_groups"], ["ALL", "QST", "CQ"])
            self.assertIsNone(get_app_setting(APRS_ALARM_GROUPS_SETTING_KEY))

    def test_alarm_groups_are_trimmed_uppercased_deduplicated_and_empty_values_are_skipped(self) -> None:
        self.assertEqual(
            normalize_aprs_alarm_groups(
                " pl-warn, , localwarn,PL-WARN,\nlocalwarn "
            ),
            ["PL-WARN", "LOCALWARN"],
        )
        self.assertEqual(normalize_aprs_alarm_groups(" , \n, "), [])
        with self.assertRaises(ValueError):
            normalize_aprs_alarm_groups("TOO-LONG-10")

    def test_alarm_groups_are_stored_separately_from_standard_message_groups(self) -> None:
        with temporary_database():
            saved = save_aprs_alarm_groups(" localwarn, PL-WARN, localwarn ")
            self.assertEqual(saved, ["LOCALWARN", "PL-WARN"])
            self.assertEqual(
                get_app_setting(APRS_ALARM_GROUPS_SETTING_KEY),
                "LOCALWARN,PL-WARN",
            )
            self.assertIsNone(get_app_setting("messages.target_groups"))
            self.assertEqual(get_message_settings()["target_groups"], ["ALL", "QST", "CQ"])

    def test_effective_rf_groups_append_alarm_groups_without_changing_standard_groups(self) -> None:
        with temporary_database():
            standard_groups = get_message_settings()["target_groups"]
            self.assertEqual(
                get_effective_message_target_groups(),
                ["ALL", "QST", "CQ", "PL-WARN"],
            )
            self.assertEqual(standard_groups, ["ALL", "QST", "CQ"])

    def test_settings_form_saves_and_renders_effective_diagnostics(self) -> None:
        from fastapi.testclient import TestClient

        from app.dependencies import get_current_user
        from app.main import app
        from app.models import UserIdentity

        with temporary_database():
            set_app_setting("app_language", "pl")
            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=1,
                username="admin",
                role="admin",
                is_active=True,
            )
            try:
                client = TestClient(app)
                saved = client.post(
                    "/settings/alarm-groups",
                    data={"alarm_groups": " pl-warn, , localwarn, PL-WARN "},
                )
                self.assertEqual(saved.status_code, 200)
                self.assertEqual(
                    saved.json()["alarm_groups"],
                    ["PL-WARN", "LOCALWARN"],
                )

                page = client.get("/settings")
                self.assertEqual(page.status_code, 200)
                self.assertIn("Grupy alarmowe APRS", page.text)
                self.assertIn("PL-WARN, LOCALWARN", page.text)
                self.assertIn("ALL, QST, CQ, PL-WARN, LOCALWARN", page.text)
                self.assertIn("g/PL-WARN/LOCALWARN", page.text)
            finally:
                app.dependency_overrides.clear()


class AprsAlarmGroupFilterTests(unittest.TestCase):
    def test_automatic_filter_supports_one_or_multiple_alarm_groups(self) -> None:
        with temporary_database():
            self.assertEqual(build_automatic_aprsis_alarm_filter(), "g/PL-WARN")
            self.assertEqual(
                build_automatic_aprsis_alarm_filter(["PL-WARN", "LOCALWARN"]),
                "g/PL-WARN/LOCALWARN",
            )
            save_aprs_alarm_groups("")
            self.assertEqual(build_automatic_aprsis_alarm_filter(), "")

    def test_effective_filter_appends_missing_groups_without_mutating_manual_filter(self) -> None:
        with temporary_database():
            interface_id = insert_aprsis_interface("m/100")
            interface = get_enabled_aprsis_interface()
            self.assertEqual((interface or {}).get("filter"), "m/100")
            self.assertEqual(
                (interface or {}).get("effective_filter"),
                "m/100 g/PL-WARN",
            )
            stored = fetch_one(
                "SELECT device_path FROM modems WHERE id = ?",
                (interface_id,),
            )
            assert stored is not None
            self.assertEqual(stored["device_path"], "m/100")
            self.assertIn(
                "filter m/100 g/PL-WARN",
                build_aprsis_login_line(
                    login="SP0BOX-1",
                    passcode="12345",
                    server_filter="m/100",
                ),
            )

    def test_effective_filter_does_not_duplicate_existing_group_subscriptions(self) -> None:
        self.assertEqual(
            build_effective_aprsis_filter("m/100 g/PL-WARN"),
            "m/100 g/PL-WARN",
        )
        self.assertEqual(
            build_effective_aprsis_filter(
                "m/100 g/pl-warn/LOCALWARN",
                ["PL-WARN", "LOCALWARN", "REGIONAL"],
            ),
            "m/100 g/pl-warn/LOCALWARN g/REGIONAL",
        )

    def test_alarm_group_change_uses_existing_filter_signature_reconnect(self) -> None:
        with temporary_database():
            insert_aprsis_interface("m/100")
            before = get_enabled_aprsis_interface()
            assert before is not None
            service = AprsisClientService()
            config_key = ("example.aprs2.net", 14580, "SP0BOX-1", "12345")
            service._writer = object()  # type: ignore[assignment]
            service._connected_config = config_key
            service._connected_rx_signature = service._rx_signature(before)

            save_aprs_alarm_groups("PL-WARN,LOCALWARN")
            after = get_enabled_aprsis_interface()

            self.assertTrue(
                service._connection_needs_reconnect(
                    config_key=config_key,
                    desired_rx_signature=service._rx_signature(after),
                )
            )


class AprsAlarmGroupReceiveTests(unittest.TestCase):
    _ALARM_LINE = (
        "PLWXSR>APRS::PL-WARN  :310100z,TSTORM1,1465{129AA"
    )

    @staticmethod
    def _group_alarm_line(
        *,
        source: str = "PLWXSR",
        group: str = "PL-WARN",
        expiry: str = "310100z",
        event_code: str = "TSTORM1",
        area_code: str,
        message_id: str | None,
    ) -> str:
        content = f"{expiry},{event_code},{area_code}"
        if message_id is not None:
            content = f"{content}{{{message_id}"
        return f"{source}>APRS,TCPIP*::{group:<9}:{content}"

    def _assert_alarm_message_stored(self, *, source_kind: str) -> None:
        stored = fetch_one(
            """
            SELECT m.direction, m.sender, m.addressee, m.message_text,
                   c.remote_callsign, c.conversation_kind
            FROM aprs_messages m
            JOIN aprs_message_conversations c ON c.id = m.conversation_id
            WHERE m.addressee = 'PL-WARN'
            """
        )
        assert stored is not None
        self.assertEqual(stored["direction"], "rx")
        self.assertEqual(stored["sender"], "PLWXSR")
        self.assertEqual(stored["addressee"], "PL-WARN")
        self.assertEqual(
            stored["message_text"],
            "310100z,TSTORM1,1465{129AA",
        )
        self.assertEqual(stored["remote_callsign"], "PL-WARN")
        self.assertEqual(stored["conversation_kind"], "group")

        alert = fetch_one(
            """
            SELECT alerts.*, frames.id AS frame_id, frames.line, frames.source_kind,
                   relations.received_at
            FROM aprs_alerts AS alerts
            JOIN aprs_alert_frames AS relations ON relations.alert_id = alerts.id
            JOIN traffic_frames AS frames ON frames.id = relations.frame_id
            """
        )
        assert alert is not None
        self.assertEqual(alert["source_callsign"], "PLWXSR")
        self.assertEqual(alert["alert_type"], "PL-WARN")
        self.assertEqual(alert["message"], "310100z,TSTORM1,1465{129AA")
        self.assertEqual(alert["alarm_group"], "PL-WARN")
        self.assertEqual(json.loads(alert["area_codes_json"]), ["1465"])
        self.assertEqual(alert["expiry"], "310100z")
        self.assertEqual(alert["event_code"], "TSTORM1")
        self.assertEqual(alert["area_code"], "1465")
        self.assertEqual(alert["message_id"], "129AA")
        self.assertIn("aprs-group-message", alert["identity_key"])
        self.assertEqual(int(alert["is_active"]), 1)
        self.assertEqual(int(alert["frame_count"]), 1)
        self.assertEqual(alert["initial_frame_id"], alert["frame_id"])
        self.assertEqual(alert["last_frame_id"], alert["frame_id"])
        self.assertEqual(alert["line"], self._ALARM_LINE)
        self.assertEqual(alert["source_kind"], source_kind)

        snapshot_frame = next(
            frame
            for frame in traffic_snapshot(limit=10)["frames"]
            if int(frame["id"]) == int(alert["frame_id"])
        )
        self.assertEqual(snapshot_frame["alert_id"], int(alert["id"]))
        self.assertFalse(snapshot_frame["emergency"])
        self.assertFalse(snapshot_frame["alert_should_notify"])

    def test_rf_alarm_group_message_creates_alert_and_keeps_message_and_traffic_frame(self) -> None:
        with temporary_database():
            accepted = process_normalized_tnc2_rx(
                self._ALARM_LINE,
                source="Main RF",
                source_kind="rf",
                band="2m",
                timestamp="2026-01-01T00:01:00+00:00",
            )
            self.assertTrue(accepted)
            self._assert_alarm_message_stored(source_kind="rf")

    def test_aprsis_alarm_group_message_creates_alert_and_keeps_message_and_traffic_frame(self) -> None:
        with temporary_database():
            accepted = process_normalized_tnc2_rx(
                self._ALARM_LINE,
                source="APRS-IS · Internet RX",
                source_kind="aprsis",
                timestamp="2026-01-01T00:01:00+00:00",
            )
            self.assertTrue(accepted)
            self._assert_alarm_message_stored(source_kind="aprsis")

    def test_direct_messages_and_existing_standard_groups_still_work(self) -> None:
        with temporary_database():
            for offset, line in enumerate(
                (
                    "SP8ABC>APRS::SP0BOX-1 :Direct message{01",
                    "SP9XYZ>APRS::CQ       :Standard group{02",
                )
            ):
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        line,
                        source="Main RF",
                        source_kind="rf",
                        band="2m",
                        timestamp=f"2026-01-01T00:01:0{offset}+00:00",
                    )
                )
            rows = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM aprs_messages
                WHERE direction = 'rx' AND addressee IN ('SP0BOX-1', 'CQ')
                """
            )
            self.assertEqual(int((rows or {"total": -1})["total"]), 2)
            alert_count = fetch_one("SELECT COUNT(*) AS total FROM aprs_alerts")
            self.assertEqual(int((alert_count or {"total": -1})["total"]), 0)

    def test_standard_message_group_not_configured_as_alarm_remains_message_only(self) -> None:
        with temporary_database():
            save_message_settings(
                {
                    "default_path": "",
                    "receive_any_ssid": False,
                    "target_groups": ["LOCALWARN"],
                }
            )
            accepted = process_normalized_tnc2_rx(
                "SP7ABC>APRS::LOCALWARN:Ordinary group{03",
                source="Main RF",
                source_kind="rf",
                band="2m",
                timestamp="2026-01-01T00:02:00+00:00",
            )
            self.assertTrue(accepted)
            stored = fetch_one(
                """
                SELECT addressee, message_text
                FROM aprs_messages
                WHERE direction = 'rx'
                """
            )
            assert stored is not None
            self.assertEqual(
                (stored["addressee"], stored["message_text"]),
                ("LOCALWARN", "Ordinary group"),
            )
            self.assertIsNone(fetch_one("SELECT id FROM aprs_alerts"))

    def test_group_warning_parser_extracts_generic_event_and_identity_fields(self) -> None:
        parsed = parse_aprs_group_warning_content(
            "310100z,FLOOD9,0012{Ab123"
        )

        self.assertEqual(
            parsed,
            {
                "expiry": "310100z",
                "event_code": "FLOOD9",
                "area_code": "0012",
                "area_codes": ["0012"],
                "message_id": "Ab123",
            },
        )

    def test_three_message_ids_create_three_area_alerts(self) -> None:
        frames = (
            ("1465", "129AA"),
            ("2401", "82BCD"),
            ("3262", "F913A"),
        )
        with temporary_database():
            for offset, (area_code, message_id) in enumerate(frames):
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        self._group_alarm_line(
                            area_code=area_code,
                            message_id=message_id,
                        ),
                        source="APRS-IS · Internet RX",
                        source_kind="aprsis",
                        timestamp=f"2026-01-01T00:03:0{offset}+00:00",
                    )
                )

            alerts = fetch_all(
                """
                SELECT source_callsign, alarm_group, expiry, event_code,
                       area_code, message_id, identity_key
                FROM aprs_alerts
                ORDER BY id ASC
                """
            )
            alert_page = list_alerts(page_size=10)

        self.assertEqual(len(alerts), 3)
        self.assertEqual(len(alert_page["items"]), 3)
        self.assertEqual(
            {(row["area_code"], row["message_id"]) for row in alerts},
            set(frames),
        )
        self.assertTrue(all(row["expiry"] == "310100z" for row in alerts))
        self.assertTrue(all(row["event_code"] == "TSTORM1" for row in alerts))
        self.assertEqual(len({row["identity_key"] for row in alerts}), 3)

    def test_repeated_identical_frame_updates_one_alarm(self) -> None:
        line = self._group_alarm_line(area_code="1465", message_id="129AA")
        with temporary_database():
            for offset in range(2):
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        line,
                        source="Main RF",
                        source_kind="rf",
                        band="2m",
                        timestamp=f"2026-01-01T00:04:0{offset}+00:00",
                    )
                )

            alerts = fetch_all("SELECT id, frame_count FROM aprs_alerts")
            relations = fetch_all("SELECT alert_id, frame_id FROM aprs_alert_frames")

        self.assertEqual(len(alerts), 1)
        self.assertEqual(int(alerts[0]["frame_count"]), 2)
        self.assertEqual(len(relations), 2)
        self.assertTrue(all(relations[0]["alert_id"] == row["alert_id"] for row in relations))

    def test_same_message_id_from_another_sender_does_not_collide(self) -> None:
        with temporary_database():
            for offset, source_callsign in enumerate(("PLWXSR", "PLWXS2")):
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        self._group_alarm_line(
                            source=source_callsign,
                            area_code="1465",
                            message_id="129AA",
                        ),
                        source="APRS-IS",
                        source_kind="aprsis",
                        timestamp=f"2026-01-01T00:05:0{offset}+00:00",
                    )
                )

            alerts = fetch_all(
                "SELECT source_callsign, message_id FROM aprs_alerts ORDER BY id"
            )

        self.assertEqual(
            [(row["source_callsign"], row["message_id"]) for row in alerts],
            [("PLWXSR", "129AA"), ("PLWXS2", "129AA")],
        )

    def test_same_message_id_for_another_group_does_not_collide(self) -> None:
        with temporary_database():
            save_aprs_alarm_groups("PL-WARN,DE-WARN")
            for offset, group in enumerate(("PL-WARN", "DE-WARN")):
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        self._group_alarm_line(
                            group=group,
                            area_code="1465",
                            message_id="129AA",
                        ),
                        source="APRS-IS",
                        source_kind="aprsis",
                        timestamp=f"2026-01-01T00:06:0{offset}+00:00",
                    )
                )

            alerts = fetch_all(
                "SELECT alarm_group, message_id FROM aprs_alerts ORDER BY id"
            )

        self.assertEqual(
            [(row["alarm_group"], row["message_id"]) for row in alerts],
            [("PL-WARN", "129AA"), ("DE-WARN", "129AA")],
        )

    def test_messages_without_message_id_use_stable_content_fallback(self) -> None:
        with temporary_database():
            for offset, area_code in enumerate(("1465", "2401", "1465")):
                self.assertTrue(
                    process_normalized_tnc2_rx(
                        self._group_alarm_line(
                            area_code=area_code,
                            message_id=None,
                        ),
                        source="Main RF",
                        source_kind="rf",
                        band="2m",
                        timestamp=f"2026-01-01T00:07:0{offset}+00:00",
                    )
                )

            alerts = fetch_all(
                """
                SELECT area_code, message_id, frame_count, identity_key
                FROM aprs_alerts
                ORDER BY area_code
                """
            )

        self.assertEqual(len(alerts), 2)
        self.assertEqual([row["area_code"] for row in alerts], ["1465", "2401"])
        self.assertTrue(all(row["message_id"] is None for row in alerts))
        self.assertEqual(
            {row["area_code"]: int(row["frame_count"]) for row in alerts},
            {"1465": 2, "2401": 1},
        )
        self.assertEqual(len({row["identity_key"] for row in alerts}), 2)


if __name__ == "__main__":
    unittest.main()
