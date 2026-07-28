import concurrent.futures
import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import fetch_all, fetch_one, init_db
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
from app.services.traffic import process_normalized_tnc2_rx


EMERGENCY_LINE = "SP8ABC-9>APRS:!5218.37N\\02104.87E$!EMERGENCY!Need help"


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

    def test_repeated_frame_does_not_request_another_notification(self) -> None:
        with temporary_database():
            receive_emergency(timestamp="2026-07-28T10:00:00+00:00")
            receive_emergency(timestamp="2026-07-28T10:30:00+00:00")

            snapshot = traffic_snapshot(limit=10)
            frames = sorted(snapshot["frames"], key=lambda item: item["id"])
            self.assertTrue(frames[0]["alert_should_notify"])
            self.assertFalse(frames[1]["alert_should_notify"])
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

    def test_database_schema_has_source_uniqueness_and_safe_relations(self) -> None:
        with temporary_database():
            indexes = {
                row["name"]: int(row["unique"])
                for row in fetch_all("PRAGMA index_list(aprs_alerts)")
            }
            foreign_keys = fetch_all("PRAGMA foreign_key_list(aprs_alert_frames)")

            self.assertEqual(indexes.get("idx_aprs_alerts_source_callsign"), 1)
            self.assertEqual(
                {row["table"] for row in foreign_keys},
                {"aprs_alerts", "traffic_frames"},
            )
            self.assertTrue(all(str(row["on_delete"]).upper() == "CASCADE" for row in foreign_keys))

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

    def test_shared_modal_is_rendered_from_base_and_opened_by_alert_list(self) -> None:
        base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
        map_source = Path("app/templates/map.html").read_text(encoding="utf-8")
        alerts_source = Path("app/templates/alerts.html").read_text(encoding="utf-8")

        self.assertIn('{% include "partials/emergency_modal.html" %}', base_source)
        self.assertIn("map-emergency-modal.js", base_source)
        self.assertNotIn('id="aprs-emergency-modal"', map_source)
        self.assertIn('{{ t("Comment") }}', alerts_source)
        self.assertIn("window.aprsboxOpenEmergencyModal", alerts_source)


if __name__ == "__main__":
    unittest.main()
