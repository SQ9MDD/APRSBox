import concurrent.futures
import contextlib
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import execute, fetch_all, fetch_one, init_db
from app.services.alerts import (
    attention_alert_count,
    delete_alert,
    get_alert,
    get_traffic_frame,
    list_alerts,
    mute_alert,
    unmute_alert,
)
from app.services.content import traffic_snapshot
from app.services.maintenance_scheduler import MaintenanceSchedulerService
from app.services.traffic import process_normalized_tnc2_rx


EMERGENCY_LINE = "SP8ABC-9>APRS:!5218.37N\\02104.87E$!EMERGENCY!Need help"
GROUP_WARNING_LINE = (
    "PLWXSR>APRS,TCPIP*::PL-WARN  :302200z,TSTORM3,@A7F3,1/1,1465{91AC2"
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


def receive_emergency(
    *,
    timestamp: str,
    line: str = EMERGENCY_LINE,
    source: str = "TNC-2m",
) -> None:
    accepted = process_normalized_tnc2_rx(
        line,
        source=source,
        band="2m",
        timestamp=timestamp,
    )
    if not accepted:
        raise AssertionError("Emergency frame was rejected")


class AprsAlertTests(unittest.TestCase):
    def test_backend_maintenance_expires_group_alert_without_open_map_and_preserves_frame(self) -> None:
        with temporary_database():
            self.assertTrue(
                process_normalized_tnc2_rx(
                    GROUP_WARNING_LINE,
                    source="APRS-IS",
                    source_kind="aprsis",
                    timestamp="2026-07-30T20:00:00+00:00",
                )
            )
            stored = fetch_one(
                "SELECT id, is_active, expires_at FROM aprs_alerts"
            )
            assert stored is not None
            self.assertEqual(stored["expires_at"], "2026-07-30T22:00:00+00:00")
            self.assertEqual(int(stored["is_active"]), 1)

            scheduler = MaintenanceSchedulerService()
            with patch(
                "app.services.maintenance_scheduler.prune_traffic_frames_batch"
            ):
                scheduler._tick(
                    now=datetime(2026, 7, 30, 22, 1, tzinfo=timezone.utc)
                )

            expired = fetch_one(
                "SELECT is_active FROM aprs_alerts WHERE id = ?",
                (int(stored["id"]),),
            )
            frame_count = fetch_one(
                "SELECT COUNT(*) AS total FROM traffic_frames"
            )
            relation_count = fetch_one(
                "SELECT COUNT(*) AS total FROM aprs_alert_frames"
            )
            active_page = list_alerts(
                now="2026-07-30T22:01:00+00:00"
            )

        assert expired is not None
        assert frame_count is not None
        assert relation_count is not None
        self.assertEqual(int(expired["is_active"]), 0)
        self.assertEqual(active_page["items"], [])
        self.assertEqual(int(frame_count["total"]), 1)
        self.assertEqual(int(relation_count["total"]), 1)

    def test_application_restart_expires_overdue_alert(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        with temporary_database():
            self.assertTrue(
                process_normalized_tnc2_rx(
                    GROUP_WARNING_LINE,
                    source="APRS-IS",
                    source_kind="aprsis",
                    timestamp="2026-07-30T20:00:00+00:00",
                )
            )
            execute(
                """
                UPDATE aprs_alerts
                SET expires_at = '2000-01-01T00:00:00+00:00',
                    is_active = 1
                """
            )

            with TestClient(app):
                restarted = fetch_one(
                    "SELECT is_active FROM aprs_alerts"
                )
                preserved_frame = fetch_one(
                    "SELECT id FROM traffic_frames LIMIT 1"
                )

        assert restarted is not None
        self.assertEqual(int(restarted["is_active"]), 0)
        self.assertIsNotNone(preserved_frame)

    def test_mic_e_alert_preserves_complete_operator_comment(self) -> None:
        line = "SQ9MDD-7>521U02,RFONLY:'0SWl \x1c[/>144.800MHz op. Rysiek&"
        with temporary_database():
            receive_emergency(
                timestamp="2026-07-30T09:55:00+00:00",
                line=line,
                source="vpdigi",
            )

            stored_alert = fetch_one("SELECT * FROM aprs_alerts")
            self.assertIsNotNone(stored_alert)
            assert stored_alert is not None
            self.assertEqual(stored_alert["message"], "144.800MHz op. Rysiek&")

            alert = get_alert(int(stored_alert["id"]))
            self.assertIsNotNone(alert)
            assert alert is not None
            self.assertEqual(alert["message"], "144.800MHz op. Rysiek&")

    def test_first_emergency_frame_creates_alert(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")

            alert = fetch_one("SELECT * FROM aprs_alerts")
            self.assertIsNotNone(alert)
            assert alert is not None
            self.assertEqual(alert["source_callsign"], "SP8ABC-9")
            self.assertEqual(alert["frame_count"], 1)
            self.assertEqual(attention_alert_count(now="2026-07-28T10:00:01+00:00"), 1)

    def test_second_frame_updates_same_alert_and_counter(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            first_alert_id = int(fetch_one("SELECT id FROM aprs_alerts")["id"])
            receive_emergency(
                timestamp="2026-07-28T10:30:00+00:00",
                line=f"{EMERGENCY_LINE} now",
                source="APRS-IS",
            )

            alerts = fetch_all("SELECT * FROM aprs_alerts")
            self.assertEqual(len(alerts), 1)
            self.assertEqual(int(alerts[0]["id"]), first_alert_id)
            self.assertEqual(int(alerts[0]["frame_count"]), 2)
            self.assertEqual(alerts[0]["message"], "Need help now")

    def test_first_seen_is_unchanged_and_last_seen_is_updated(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            receive_emergency(timestamp="2026-07-28T10:30:00+00:00")

            alert = fetch_one("SELECT first_seen_at, last_seen_at FROM aprs_alerts")
            assert alert is not None
            self.assertEqual(alert["first_seen_at"], "2026-07-28T10:00:00+00:00")
            self.assertEqual(alert["last_seen_at"], "2026-07-28T10:30:00+00:00")

    def test_all_frames_are_related_to_same_alert(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            receive_emergency(timestamp="2026-07-28T10:30:00+00:00")

            relations = fetch_all(
                "SELECT alert_id, frame_id FROM aprs_alert_frames ORDER BY frame_id"
            )
            self.assertEqual(len(relations), 2)
            self.assertEqual(relations[0]["alert_id"], relations[1]["alert_id"])
            self.assertNotEqual(relations[0]["frame_id"], relations[1]["frame_id"])

    def test_each_latest_unmuted_frame_requests_modal_notification(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            receive_emergency(timestamp="2026-07-28T10:30:00+00:00")

            snapshot = traffic_snapshot(limit=10)
            frames = sorted(snapshot["frames"], key=lambda item: item["id"])
            self.assertFalse(frames[0]["alert_should_notify"])
            self.assertTrue(frames[1]["alert_should_notify"])
            self.assertEqual(frames[0]["alert_id"], frames[1]["alert_id"])

    def test_muted_alert_still_updates_and_does_not_notify(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            alert_id = int(fetch_one("SELECT id FROM aprs_alerts")["id"])
            self.assertTrue(mute_alert(alert_id, "indefinite"))

            receive_emergency(
                timestamp="2026-07-28T11:00:00+00:00",
                line=f"{EMERGENCY_LINE} updated",
            )

            alert = fetch_one("SELECT * FROM aprs_alerts WHERE id = ?", (alert_id,))
            assert alert is not None
            self.assertEqual(int(alert["frame_count"]), 2)
            self.assertEqual(alert["last_seen_at"], "2026-07-28T11:00:00+00:00")
            snapshot = traffic_snapshot(limit=10)
            self.assertFalse(any(frame["alert_should_notify"] for frame in snapshot["frames"]))

    def test_temporary_mute_expires_logically_and_can_be_cancelled(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            alert_id = int(fetch_one("SELECT id FROM aprs_alerts")["id"])

            self.assertTrue(mute_alert(alert_id, "1h"))
            muted = fetch_one(
                "SELECT muted_until, muted_indefinitely FROM aprs_alerts WHERE id = ?",
                (alert_id,),
            )
            assert muted is not None
            self.assertIsNotNone(muted["muted_until"])
            self.assertEqual(int(muted["muted_indefinitely"]), 0)
            self.assertEqual(attention_alert_count(now="2099-01-01T00:00:00+00:00"), 1)

            self.assertTrue(unmute_alert(alert_id))
            unmuted = fetch_one(
                "SELECT muted_until, muted_indefinitely FROM aprs_alerts WHERE id = ?",
                (alert_id,),
            )
            assert unmuted is not None
            self.assertIsNone(unmuted["muted_until"])
            self.assertEqual(int(unmuted["muted_indefinitely"]), 0)

    def test_delete_preserves_original_frames(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            alert_id = int(fetch_one("SELECT id FROM aprs_alerts")["id"])
            frame_id = int(fetch_one("SELECT id FROM traffic_frames")["id"])

            self.assertTrue(delete_alert(alert_id))

            self.assertIsNone(fetch_one("SELECT id FROM aprs_alerts WHERE id = ?", (alert_id,)))
            self.assertIsNotNone(fetch_one("SELECT id FROM traffic_frames WHERE id = ?", (frame_id,)))
            self.assertIsNone(fetch_one("SELECT frame_id FROM aprs_alert_frames WHERE frame_id = ?", (frame_id,)))

    def test_next_frame_after_delete_creates_new_alert(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            original_alert_id = int(fetch_one("SELECT id FROM aprs_alerts")["id"])
            self.assertTrue(delete_alert(original_alert_id))

            receive_emergency(timestamp="2026-07-28T11:00:00+00:00")

            new_alert_id = int(fetch_one("SELECT id FROM aprs_alerts")["id"])
            self.assertNotEqual(new_alert_id, original_alert_id)
            alert = get_alert(new_alert_id)
            assert alert is not None
            self.assertEqual(alert["frame_count"], 1)

    def test_deleted_alert_is_safe_in_historical_frame_detail(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            alert_id = int(fetch_one("SELECT id FROM aprs_alerts")["id"])
            frame_id = int(fetch_one("SELECT id FROM traffic_frames")["id"])
            self.assertTrue(delete_alert(alert_id))

            frame = get_traffic_frame(frame_id)

            self.assertIsNotNone(frame)
            assert frame is not None
            self.assertTrue(frame["emergency"])
            self.assertIsNone(frame.get("alert_id"))
            self.assertEqual(frame["alert_href"], "")

    def test_nearly_simultaneous_frames_do_not_create_duplicate_alerts(self) -> None:
        with temporary_database():
            timestamps = (
                "2026-07-28T10:00:00+00:00",
                "2026-07-28T10:00:01+00:00",
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        receive_emergency,
                        timestamp=timestamp,
                        line=f"{EMERGENCY_LINE} {index}",
                        source=f"TNC-{index}",
                    )
                    for index, timestamp in enumerate(timestamps)
                ]
                for future in futures:
                    future.result(timeout=10)

            alerts = fetch_all("SELECT * FROM aprs_alerts")
            self.assertEqual(len(alerts), 1)
            self.assertEqual(int(alerts[0]["frame_count"]), 2)
            self.assertEqual(
                int(fetch_one("SELECT COUNT(*) AS total FROM aprs_alert_frames")["total"]),
                2,
            )

    def test_database_schema_has_identity_uniqueness_and_safe_relations(self) -> None:
        with temporary_database():
            indexes = {
                row["name"]: int(row["unique"])
                for row in fetch_all("PRAGMA index_list(aprs_alerts)")
            }
            foreign_keys = fetch_all("PRAGMA foreign_key_list(aprs_alert_frames)")

            self.assertEqual(indexes.get("idx_aprs_alerts_source_callsign"), 0)
            self.assertEqual(indexes.get("idx_aprs_alerts_identity_key"), 1)
            self.assertEqual(
                {row["table"] for row in foreign_keys},
                {"aprs_alerts", "aprs_alert_parts", "traffic_frames"},
            )
            delete_modes = {
                row["table"]: str(row["on_delete"]).upper()
                for row in foreign_keys
            }
            self.assertEqual(delete_modes["aprs_alerts"], "CASCADE")
            self.assertEqual(delete_modes["traffic_frames"], "CASCADE")
            self.assertEqual(delete_modes["aprs_alert_parts"], "SET NULL")

    def test_identity_migration_preserves_and_backfills_existing_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy-alerts.db"
            previous = os.environ.get("APRSBOX_DB_PATH")
            os.environ["APRSBOX_DB_PATH"] = str(database_path)
            try:
                connection = sqlite3.connect(database_path)
                connection.executescript(
                    """
                    CREATE TABLE aprs_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_callsign TEXT NOT NULL COLLATE NOCASE,
                        alert_type TEXT NOT NULL,
                        message TEXT NOT NULL DEFAULT '',
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        frame_count INTEGER NOT NULL DEFAULT 1,
                        initial_frame_id INTEGER,
                        last_frame_id INTEGER,
                        latitude REAL,
                        longitude REAL,
                        muted_until TEXT,
                        muted_indefinitely INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE UNIQUE INDEX idx_aprs_alerts_source_callsign
                    ON aprs_alerts(source_callsign COLLATE NOCASE);
                    INSERT INTO aprs_alerts(
                        id, source_callsign, alert_type, message,
                        first_seen_at, last_seen_at, frame_count,
                        created_at, updated_at
                    )
                    VALUES
                        (7, 'SP8ABC-9', 'EMERGENCY', 'Need help',
                         '2026-01-01T00:00:00+00:00',
                         '2026-01-01T00:00:00+00:00', 1,
                         '2026-01-01T00:00:00+00:00',
                         '2026-01-01T00:00:00+00:00'),
                        (9, 'PLWXSR', 'PL-WARN',
                         '310100z,TSTORM1,1465{129AA',
                         '2026-01-01T00:01:00+00:00',
                         '2026-01-01T00:01:00+00:00', 1,
                         '2026-01-01T00:01:00+00:00',
                         '2026-01-01T00:01:00+00:00');
                    """
                )
                connection.commit()
                connection.close()

                init_db()
                rows = fetch_all(
                    """
                    SELECT id, source_callsign, alarm_group, area_code,
                           message_id, identity_key
                    FROM aprs_alerts
                    ORDER BY id
                    """
                )
                indexes = {
                    row["name"]: int(row["unique"])
                    for row in fetch_all("PRAGMA index_list(aprs_alerts)")
                }
            finally:
                if previous is None:
                    os.environ.pop("APRSBOX_DB_PATH", None)
                else:
                    os.environ["APRSBOX_DB_PATH"] = previous

        self.assertEqual([int(row["id"]) for row in rows], [7, 9])
        self.assertIsNone(rows[0]["alarm_group"])
        self.assertIn("aprs-emergency", rows[0]["identity_key"])
        self.assertEqual(
            (
                rows[1]["alarm_group"],
                rows[1]["area_code"],
                rows[1]["message_id"],
            ),
            ("PL-WARN", "1465", "129AA"),
        )
        self.assertIn("aprs-group-message", rows[1]["identity_key"])
        self.assertEqual(indexes["idx_aprs_alerts_source_callsign"], 0)
        self.assertEqual(indexes["idx_aprs_alerts_identity_key"], 1)

    def test_multipart_migration_preserves_rows_and_builds_one_visible_logical_alert(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "multipart-alerts.db"
            previous = os.environ.get("APRSBOX_DB_PATH")
            os.environ["APRSBOX_DB_PATH"] = str(database_path)
            try:
                connection = sqlite3.connect(database_path)
                connection.executescript(
                    """
                    CREATE TABLE aprs_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        identity_key TEXT,
                        source_callsign TEXT NOT NULL COLLATE NOCASE,
                        alert_type TEXT NOT NULL,
                        message TEXT NOT NULL DEFAULT '',
                        alarm_group TEXT,
                        expiry TEXT,
                        event_code TEXT,
                        area_code TEXT,
                        message_id TEXT,
                        area_codes_json TEXT NOT NULL DEFAULT '[]',
                        is_active INTEGER NOT NULL DEFAULT 1,
                        valid_until_utc TEXT,
                        first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL,
                        frame_count INTEGER NOT NULL DEFAULT 1,
                        initial_frame_id INTEGER,
                        last_frame_id INTEGER,
                        latitude REAL,
                        longitude REAL,
                        muted_until TEXT,
                        muted_indefinitely INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE UNIQUE INDEX idx_aprs_alerts_identity_key
                    ON aprs_alerts(identity_key);
                    INSERT INTO aprs_alerts(
                        id, identity_key, source_callsign, alert_type, message,
                        alarm_group, area_codes_json,
                        first_seen_at, last_seen_at, frame_count,
                        created_at, updated_at
                    )
                    VALUES
                        (11, 'old-part-1', 'PLWXSR', 'PL-WARN',
                         '302200z,TSTORM2,@A7F3,1/3,1465,1466{91AC2',
                         'PL-WARN', '["@A7F3","1/3","1465","1466"]',
                         '2026-01-30T20:00:01+00:00',
                         '2026-01-30T20:00:01+00:00', 1,
                         '2026-01-30T20:00:01+00:00',
                         '2026-01-30T20:00:01+00:00'),
                        (12, 'old-part-2', 'PLWXSR', 'PL-WARN',
                         '302200z,TSTORM2,@A7F3,2/3,1466,1412{77BD1',
                         'PL-WARN', '["@A7F3","2/3","1466","1412"]',
                         '2026-01-30T20:00:02+00:00',
                         '2026-01-30T20:00:02+00:00', 1,
                         '2026-01-30T20:00:02+00:00',
                         '2026-01-30T20:00:02+00:00'),
                        (13, 'old-part-3', 'PLWXSR', 'PL-WARN',
                         '302200z,TSTORM2,@A7F3,3/3,1415{A40E8',
                         'PL-WARN', '["@A7F3","3/3","1415"]',
                         '2026-01-30T20:00:03+00:00',
                         '2026-01-30T20:00:03+00:00', 1,
                         '2026-01-30T20:00:03+00:00',
                         '2026-01-30T20:00:03+00:00');
                    """
                )
                connection.commit()
                connection.close()

                init_db()
                init_db()
                physical_rows = fetch_all(
                    """
                    SELECT id, identity_key, superseded_by_alert_id, expires_at
                    FROM aprs_alerts
                    ORDER BY id
                    """
                )
                parts = fetch_all(
                    """
                    SELECT alert_id, part_number, aprs_message_id
                    FROM aprs_alert_parts
                    ORDER BY part_number
                    """
                )
                page = list_alerts(now="2026-01-30T21:00:00+00:00")
            finally:
                if previous is None:
                    os.environ.pop("APRSBOX_DB_PATH", None)
                else:
                    os.environ["APRSBOX_DB_PATH"] = previous

        self.assertEqual([int(row["id"]) for row in physical_rows], [11, 12, 13])
        self.assertIsNone(physical_rows[0]["superseded_by_alert_id"])
        self.assertEqual(
            [int(row["superseded_by_alert_id"]) for row in physical_rows[1:]],
            [11, 11],
        )
        self.assertIn("aprs-group-logical", physical_rows[0]["identity_key"])
        self.assertEqual(
            physical_rows[0]["expires_at"],
            "2026-01-30T22:00:00+00:00",
        )
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(int(part["alert_id"]) == 11 for part in parts))
        self.assertEqual(
            [part["aprs_message_id"] for part in parts],
            ["91AC2", "77BD1", "A40E8"],
        )
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["logical_alert_id"], "A7F3")
        self.assertEqual(page["items"][0]["received_parts"], 3)
        self.assertEqual(page["items"][0]["completion_status"], "complete")
        self.assertEqual(
            page["items"][0]["area_codes"],
            ["1465", "1466", "1412", "1415"],
        )

    def test_mutating_alert_routes_are_post_only(self) -> None:
        from app.routers.pages import router

        mutation_paths = {
            "/alerts/{alert_id}/mute",
            "/alerts/{alert_id}/unmute",
            "/alerts/{alert_id}/delete",
            "/alerts/delete-selected",
        }
        methods_by_path = {
            route.path: set(route.methods or set())
            for route in router.routes
            if getattr(route, "path", None) in mutation_paths
        }
        self.assertEqual(set(methods_by_path), mutation_paths)
        self.assertTrue(all(methods == {"POST"} for methods in methods_by_path.values()))

    def test_alert_action_return_path_only_accepts_alert_list(self) -> None:
        from app.routers.pages import _alert_action_return_path

        self.assertEqual(_alert_action_return_path(7, "/alerts"), "/alerts")
        self.assertEqual(_alert_action_return_path(7, "/alerts?page=3"), "/alerts?page=3")
        self.assertEqual(_alert_action_return_path(7, None), "/alerts/7")
        self.assertEqual(_alert_action_return_path(7, "https://example.com"), "/alerts/7")
        self.assertEqual(_alert_action_return_path(7, "//example.com"), "/alerts/7")

    def test_alert_list_exposes_latest_frame_for_shared_modal(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            receive_emergency(
                timestamp="2026-07-28T10:30:00+00:00",
                line=f"{EMERGENCY_LINE} with the complete operator comment",
                source="APRS-IS",
            )

            page = list_alerts()
            self.assertEqual(len(page["items"]), 1)
            item = page["items"][0]
            modal_frame = item["modal_frame"]

            self.assertEqual(item["message"], "Need help with the complete operator comment")
            self.assertTrue(modal_frame["emergency"])
            self.assertEqual(modal_frame["alert_id"], item["id"])
            self.assertEqual(modal_frame["source"], "APRS-IS")
            self.assertEqual(
                modal_frame["emergency_data"]["summary"],
                "Need help with the complete operator comment",
            )
            self.assertFalse(modal_frame["alert_should_notify"])

    def test_alert_list_renders_compact_color_categorization_and_contextual_time(self) -> None:
        from fastapi.testclient import TestClient

        from app.dependencies import get_current_user
        from app.main import app
        from app.models import UserIdentity

        with temporary_database():
            received_at = datetime.now(timezone.utc).replace(microsecond=0)
            expires_at = received_at + timedelta(hours=6)
            expiry = f"{expires_at.day:02d}{expires_at.hour:02d}{expires_at.minute:02d}z"
            receive_emergency(timestamp=received_at.isoformat())
            self.assertTrue(
                process_normalized_tnc2_rx(
                    (
                        "PLWXSR>APRS,TCPIP*::PL-WARN  :"
                        f"{expiry},TSTORM2,@A7F4,1/1,1465{{91AC3"
                    ),
                    source="APRS-IS",
                    source_kind="aprsis",
                    timestamp=received_at.isoformat(),
                )
            )
            app.dependency_overrides[get_current_user] = lambda: UserIdentity(
                id=1,
                username="admin",
                role="admin",
                is_active=True,
            )
            try:
                response = TestClient(app).get("/alerts")
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200)
        self.assertIn("alert-category-badge-level-2", response.text)
        self.assertIn("alert-category-badge-emergency", response.text)
        self.assertIn("Expiry / last received", response.text)
        self.assertNotIn("<th>Destination group</th>", response.text)
        self.assertNotIn("<th>Logical alert ID</th>", response.text)
        self.assertNotIn("<th>Completion status</th>", response.text)

    def test_shared_modal_is_rendered_from_base_and_opened_by_alert_list(self) -> None:
        base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
        map_source = Path("app/templates/map.html").read_text(encoding="utf-8")
        alerts_source = Path("app/templates/alerts.html").read_text(encoding="utf-8")
        alert_detail_source = Path("app/templates/alert_detail.html").read_text(
            encoding="utf-8"
        )
        traffic_source = Path("app/templates/traffic.html").read_text(encoding="utf-8")
        modal_source = Path("app/templates/partials/emergency_modal.html").read_text(
            encoding="utf-8"
        )
        modal_js_source = Path("app/static/js/map-emergency-modal.js").read_text(
            encoding="utf-8"
        )
        map_js_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        style_source = Path("app/static/css/style.css").read_text(encoding="utf-8")

        self.assertIn('{% include "partials/emergency_modal.html" %}', base_source)
        self.assertIn("map-emergency-modal.js", base_source)
        self.assertNotIn('id="aprs-emergency-modal"', map_source)
        self.assertNotIn("alerts-col-comment", alerts_source)
        self.assertIn("alerts-col-category", alerts_source)
        self.assertIn('{{ t("Expiry / last received") }}', alerts_source)
        self.assertNotIn("alerts-col-group", alerts_source)
        self.assertNotIn("alerts-col-logical-id", alerts_source)
        self.assertNotIn("alerts-col-severity", alerts_source)
        self.assertNotIn("alerts-col-parts", alerts_source)
        self.assertNotIn("alerts-col-status", alerts_source)
        self.assertNotIn("alerts-col-first-seen", alerts_source)
        self.assertNotIn("alerts-col-last-seen", alerts_source)
        self.assertIn("alert-category-badge-level-1", alerts_source)
        self.assertIn("alert-category-badge-level-2", alerts_source)
        self.assertIn("alert-category-badge-level-3", alerts_source)
        self.assertIn("alert-category-badge-unknown", alerts_source)
        self.assertIn("alert-category-badge-emergency", alerts_source)
        self.assertIn("alert.expires_at_label", alerts_source)
        self.assertIn("alert.last_seen_label", alerts_source)
        self.assertIn("alert-list-muted-indicator", alerts_source)
        self.assertNotIn("alert-mute-form", alerts_source)
        self.assertIn("min-width: 42rem", style_source)
        self.assertIn(".alert-category-badge-level-1", style_source)
        self.assertIn(".alert-category-badge-level-2", style_source)
        self.assertIn(".alert-category-badge-level-3", style_source)
        self.assertIn(".alert-category-badge-unknown", style_source)
        self.assertIn("file-document-alert-outline.svg", alerts_source)
        self.assertNotIn("data-alert-unmute-placeholder", alerts_source)
        self.assertIn('href="{{ request.scope.root_path }}{{ alert.detail_href }}"', alerts_source)
        self.assertIn("alert-emergency-panel alert-detail-panel", alert_detail_source)
        self.assertIn("alert-emergency-panel alert-history-panel", alert_detail_source)
        self.assertIn('{{ t("Expires at") }}', alert_detail_source)
        self.assertIn("alert-detail-header-tools", alert_detail_source)
        self.assertIn("alert-detail-help-button", alert_detail_source)
        self.assertNotIn(
            'class="help-icon-button page-help-button"',
            alert_detail_source,
        )
        self.assertIn('data-help-page="application/alerts"', alerts_source)
        self.assertIn('data-help-page="application/alerts"', alert_detail_source)
        self.assertIn('{% include "partials/help_modal.html" %}', alerts_source)
        self.assertIn("help-viewer.js", alerts_source)
        self.assertGreater(
            alerts_source.index('id="bulk-delete-form"'),
            alerts_source.index("</table>"),
        )
        self.assertIn("window.aprsboxOpenEmergencyModal", alerts_source)
        self.assertNotIn("frame.detail_href", traffic_source)
        self.assertNotIn("detailsText", traffic_source)
        self.assertIn("frame.alert_href", traffic_source)
        self.assertIn("aprsbox-emergency-frames-shown", modal_js_source)
        self.assertIn("playSound: !frame.alert_muted", modal_js_source)
        self.assertIn("aprs-emergency-audio", modal_js_source)
        self.assertIn("keepChannelWarm: !frame.alert_muted", modal_js_source)
        self.assertIn("unlockEmergencyAlarmAudio", modal_js_source)
        self.assertIn("warmEmergencyAlarmAudio", modal_js_source)
        self.assertIn('id="aprs-emergency-audio"', modal_source)
        self.assertIn("autoplay", modal_source)
        self.assertIn("muted", modal_source)
        self.assertIn("looksLikeModalRegressionView", map_js_source)
        self.assertNotIn("URLSearchParams(window.location.search)", map_js_source)


if __name__ == "__main__":
    unittest.main()
