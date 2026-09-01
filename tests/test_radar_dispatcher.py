import asyncio
import contextlib
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import fetch_one, init_db, set_app_setting
from app.services.notifications import (
    RadarFrameObservation,
    RadarNotificationDispatcher,
    evaluate_radar_frame_observation,
    safe_save_notification_radar_rule,
)
from app.services.traffic import process_normalized_tnc2_rx


POSITION_LINE = "SQ6ODL-9>APRS,TCPIP*:!5000.00N/01900.00E>test"


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-radar-test.db"
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


def observation(
    *,
    callsign: str = "SQ6ODL-9",
    latitude: float | None = 50.001,
    longitude: float | None = 19.001,
    timestamp: str = "2026-01-01T00:00:00+00:00",
) -> RadarFrameObservation:
    return RadarFrameObservation(
        callsign=callsign,
        latitude=latitude,
        longitude=longitude,
        timestamp=timestamp,
        source="Internet RX",
        source_kind="aprsis",
        fingerprint="traffic:1",
    )


class RadarFrameEvaluationTests(unittest.TestCase):
    station_settings = {
        "callsign": "SQ0BOX",
        "ssid": "1",
        "latitude": "50.0",
        "longitude": "19.0",
    }

    def _evaluate(self, item: RadarFrameObservation) -> list[dict]:
        with patch(
            "app.services.notifications.get_station_settings",
            return_value=self.station_settings,
        ), patch(
            "app.services.notifications.get_wx_config",
            return_value={"enabled": False},
        ):
            return evaluate_radar_frame_observation(item)

    def _save_rule(self, pattern: str, distance_m: int) -> int:
        ok, error, rule_id = safe_save_notification_radar_rule(
            {"enabled": True, "pattern": pattern, "distance_m": distance_m}
        )
        self.assertTrue(ok, error)
        assert rule_id is not None
        return rule_id

    def test_exact_rule_matches_one_parsed_frame(self) -> None:
        with temporary_database():
            self._save_rule("SQ6ODL-9", 0)
            set_app_setting("radar_enabled", "1")

            events = self._evaluate(observation())

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["data"]["station"], "SQ6ODL-9")

    def test_wildcard_rule_matches_one_parsed_frame(self) -> None:
        with temporary_database():
            self._save_rule("SQ6ODL*", 0)
            set_app_setting("radar_enabled", "1")

            events = self._evaluate(observation())

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["data"]["matched_rule"]["pattern"], "SQ6ODL*")

    def test_missing_position_is_dropped_without_state(self) -> None:
        with temporary_database():
            rule_id = self._save_rule("*", 0)
            set_app_setting("radar_enabled", "1")

            events = self._evaluate(observation(latitude=None, longitude=None))

            self.assertEqual(events, [])
            state = fetch_one(
                "SELECT COUNT(*) AS total FROM notification_radar_state WHERE rule_id = ?",
                (rule_id,),
            )
            self.assertEqual(int(state["total"]), 0)

    def test_no_matching_rule_does_not_create_state(self) -> None:
        with temporary_database():
            rule_id = self._save_rule("SP5ABC", 0)
            set_app_setting("radar_enabled", "1")

            events = self._evaluate(observation())

            self.assertEqual(events, [])
            state = fetch_one(
                "SELECT COUNT(*) AS total FROM notification_radar_state WHERE rule_id = ?",
                (rule_id,),
            )
            self.assertEqual(int(state["total"]), 0)

    def test_distance_match_and_no_match_update_transition_state(self) -> None:
        with temporary_database():
            rule_id = self._save_rule("SQ6ODL*", 1000)
            set_app_setting("radar_enabled", "1")

            inside_events = self._evaluate(observation(latitude=50.001, longitude=19.001))
            outside_events = self._evaluate(
                observation(
                    latitude=51.0,
                    longitude=20.0,
                    timestamp="2026-01-01T00:01:00+00:00",
                )
            )
            state = fetch_one(
                "SELECT is_inside FROM notification_radar_state WHERE rule_id = ? AND station_key = ?",
                (rule_id, "SQ6ODL-9"),
            )

            self.assertEqual(len(inside_events), 1)
            self.assertEqual(outside_events, [])
            self.assertEqual(int(state["is_inside"]), 0)

    def test_cooldown_deduplicates_repeated_inside_frame(self) -> None:
        with temporary_database():
            rule_id = self._save_rule("SQ6ODL*", 1000)
            set_app_setting("radar_enabled", "1")

            first_events = self._evaluate(observation())
            second_events = self._evaluate(
                observation(timestamp="2026-01-01T00:01:00+00:00")
            )
            state = fetch_one(
                "SELECT is_inside, last_matched_at FROM notification_radar_state WHERE rule_id = ? AND station_key = ?",
                (rule_id, "SQ6ODL-9"),
            )

            self.assertEqual(len(first_events), 1)
            self.assertEqual(second_events, [])
            self.assertEqual(int(state["is_inside"]), 1)
            self.assertEqual(state["last_matched_at"], "2026-01-01T00:00:00+00:00")

    def test_runtime_uses_existing_parse_without_station_snapshot(self) -> None:
        with temporary_database(), patch(
            "app.services.traffic.queue_radar_frame"
        ) as radar_enqueue, patch(
            "app.services.notifications.get_visible_station_snapshots"
        ) as snapshot_fetch:
            self.assertTrue(
                process_normalized_tnc2_rx(
                    POSITION_LINE,
                    source="Internet RX",
                    source_kind="aprsis",
                )
            )

            snapshot_fetch.assert_not_called()
            radar_enqueue.assert_called_once()
            payload = radar_enqueue.call_args.kwargs
            self.assertEqual(payload["callsign"], "SQ6ODL-9")
            self.assertEqual(payload["latitude"], "50.00000")
            self.assertEqual(payload["longitude"], "19.00000")
            self.assertEqual(payload["source_kind"], "aprsis")
            self.assertTrue(payload["fingerprint"].startswith("traffic:"))


class RadarDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_worker_emits_notification_for_matching_frame(self) -> None:
        with temporary_database():
            ok, error, _rule_id = safe_save_notification_radar_rule(
                {"enabled": True, "pattern": "SQ6ODL*", "distance_m": 1000}
            )
            self.assertTrue(ok, error)
            set_app_setting("radar_enabled", "1")
            dispatcher = RadarNotificationDispatcher(queue_capacity=2)
            with patch(
                "app.services.notifications.get_station_settings",
                return_value=RadarFrameEvaluationTests.station_settings,
            ), patch(
                "app.services.notifications.get_wx_config",
                return_value={"enabled": False},
            ), patch(
                "app.services.notifications._NOTIFICATION_EXECUTOR.submit"
            ) as notification_submit:
                await dispatcher.start()
                try:
                    self.assertTrue(dispatcher.enqueue(observation()))
                    await dispatcher.wait_until_idle()
                    notification_submit.assert_called_once()
                    event = notification_submit.call_args.args[1]
                    self.assertEqual(event["event_type"], "radar_station_match")
                    metrics = dispatcher.snapshot()
                    self.assertEqual(metrics["completed"], 1)
                    self.assertIn("callsign_rule_filter", metrics["radar_breakdown_ms"])
                finally:
                    await dispatcher.stop()

    async def test_invalid_position_is_measurably_dropped(self) -> None:
        dispatcher = RadarNotificationDispatcher(queue_capacity=2, processor=lambda _item: None)
        await dispatcher.start()
        try:
            self.assertFalse(dispatcher.enqueue(observation(latitude=None)))
            metrics = dispatcher.snapshot()
            self.assertEqual(metrics["dropped"], 1)
            self.assertEqual(metrics["dropped_invalid"], 1)
            self.assertEqual(metrics["enqueued"], 0)
        finally:
            await dispatcher.stop()

    async def test_worker_exception_does_not_stop_later_frames(self) -> None:
        processed: list[str] = []

        def processor(item: RadarFrameObservation) -> None:
            processed.append(item.callsign)
            if len(processed) == 1:
                raise RuntimeError("radar observer failed")

        dispatcher = RadarNotificationDispatcher(queue_capacity=2, processor=processor)
        with patch("app.services.notifications.log_event"):
            await dispatcher.start()
            try:
                self.assertTrue(dispatcher.enqueue(observation(callsign="SQ6AAA")))
                self.assertTrue(dispatcher.enqueue(observation(callsign="SQ6BBB")))
                await dispatcher.wait_until_idle()
                metrics = dispatcher.snapshot()
                self.assertEqual(processed, ["SQ6AAA", "SQ6BBB"])
                self.assertEqual(metrics["failed"], 1)
                self.assertEqual(metrics["completed"], 1)
                self.assertTrue(metrics["running"])
            finally:
                await dispatcher.stop()

    async def test_overflow_is_bounded_and_measurable(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def slow_processor(_item: RadarFrameObservation) -> None:
            started.set()
            release.wait(timeout=2.0)

        dispatcher = RadarNotificationDispatcher(queue_capacity=1, processor=slow_processor)
        await dispatcher.start()
        try:
            self.assertTrue(dispatcher.enqueue(observation(callsign="SQ6AAA")))
            self.assertTrue(
                await asyncio.wait_for(asyncio.to_thread(started.wait, 1.0), timeout=1.5)
            )
            self.assertTrue(dispatcher.enqueue(observation(callsign="SQ6BBB")))
            enqueue_started = time.monotonic()
            self.assertFalse(dispatcher.enqueue(observation(callsign="SQ6CCC")))
            self.assertLess(time.monotonic() - enqueue_started, 0.1)
            metrics = dispatcher.snapshot()
            self.assertEqual(metrics["capacity"], 1)
            self.assertEqual(metrics["high_water"], 1)
            self.assertEqual(metrics["enqueued"], 2)
            self.assertEqual(metrics["dropped"], 1)
            self.assertEqual(metrics["dropped_overflow"], 1)
        finally:
            release.set()
            await dispatcher.stop()

    async def test_shutdown_drains_fifo_and_joins_worker(self) -> None:
        processed: list[str] = []
        dispatcher = RadarNotificationDispatcher(
            queue_capacity=2,
            processor=lambda item: processed.append(item.callsign),
        )
        await dispatcher.start()
        self.assertTrue(dispatcher.enqueue(observation(callsign="SQ6AAA")))
        self.assertTrue(dispatcher.enqueue(observation(callsign="SQ6BBB")))

        await dispatcher.stop()

        metrics = dispatcher.snapshot()
        self.assertEqual(processed, ["SQ6AAA", "SQ6BBB"])
        self.assertEqual(metrics["completed"], 2)
        self.assertEqual(metrics["depth"], 0)
        self.assertFalse(metrics["running"])
        self.assertEqual(metrics["metrics_ms"]["radar_queue_wait"]["count"], 2)
        self.assertEqual(metrics["metrics_ms"]["radar_processing"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
