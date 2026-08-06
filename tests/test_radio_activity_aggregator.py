import contextlib
import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.db import connect, execute, fetch_one, init_db
from app.services.radio_activity import (
    _floor_to_bucket_start,
    get_dashboard_radio_activity,
    get_traffic_direct_heard_statistics,
    get_traffic_devices_statistics,
    get_traffic_users_statistics,
    record_traffic_device_station_observation,
    run_radio_activity_aggregation,
)

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


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


def insert_frame(
    *,
    source: str,
    interface_id: int | None,
    direction: str,
    frame_format: str,
    line: str,
    created_at: str,
    command: str = "",
    band: str = "2m",
) -> None:
    execute(
        """
        INSERT INTO traffic_frames(
            source, interface_id, direction, band, format, line, port, command, length, hex, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, '0', ?, ?, '', ?)
        """,
        (
            source,
            interface_id,
            direction,
            band,
            frame_format,
            line,
            command,
            len(line.encode("utf-8")),
            created_at,
        ),
    )


class RadioActivityAggregatorTests(unittest.TestCase):
    def test_init_db_creates_radio_activity_tables(self) -> None:
        with temporary_database():
            connection = connect()
            try:
                activity_columns = {row["name"] for row in connection.execute("PRAGMA table_info(radio_activity_5m)").fetchall()}
                state_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(radio_activity_aggregator_state)").fetchall()
                }
                devices_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(traffic_device_station_device_hourly)").fetchall()
                }
                activity_indexes = {
                    row["name"] for row in connection.execute("PRAGMA index_list('radio_activity_5m')").fetchall()
                }
                devices_indexes = {
                    row["name"] for row in connection.execute("PRAGMA index_list('traffic_device_station_device_hourly')").fetchall()
                }
            finally:
                connection.close()

            self.assertIn("bucket_start_utc", activity_columns)
            self.assertIn("bucket_end_utc", activity_columns)
            self.assertIn("source_name", activity_columns)
            self.assertIn("rx_total", activity_columns)
            self.assertIn("duplicate_total", activity_columns)
            self.assertIn("last_processed_bucket_start_utc", state_columns)
            self.assertIn("bucket_start_utc", devices_columns)
            self.assertIn("station_key", devices_columns)
            self.assertIn("device_key", devices_columns)
            self.assertIn("destination_key", devices_columns)
            self.assertIn("idx_radio_activity_5m_bucket_start", activity_indexes)
            self.assertIn("idx_radio_activity_5m_bucket_source", activity_indexes)
            self.assertIn("idx_traffic_device_station_device_hourly_bucket", devices_indexes)

    def test_bucket_floor_uses_utc_5m_resolution(self) -> None:
        value = datetime(2026, 5, 4, 10, 7, 52, tzinfo=timezone.utc)
        self.assertEqual(
            _floor_to_bucket_start(value, bucket_minutes=5).isoformat(),
            datetime(2026, 5, 4, 10, 5, 0, tzinfo=timezone.utc).isoformat(),
        )

    def test_bucket_floor_uses_full_day_boundaries_for_1d_buckets(self) -> None:
        value = datetime(2026, 5, 5, 15, 50, 12, tzinfo=timezone.utc)
        self.assertEqual(
            _floor_to_bucket_start(value, bucket_minutes=1440).isoformat(),
            datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        )

    def test_band_condition_runtime_is_skipped_when_no_interface_has_assessment_enabled(self) -> None:
        with temporary_database():
            bucket_start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS:!5218.37N/02104.87E>Test",
                created_at=(bucket_start + timedelta(minutes=1)).isoformat(),
            )

            with (
                patch("app.services.radio_activity.aggregate_band_condition_parsed_bucket") as aggregate_band,
                patch("app.services.radio_activity.finalize_band_condition_hours") as finalize_band,
            ):
                result = run_radio_activity_aggregation(
                    now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                    safety_delay_seconds=30,
                )

            self.assertGreaterEqual(int(result.get("processed_buckets") or 0), 1)
            aggregate_band.assert_not_called()
            finalize_band.assert_not_called()
            activity_row = fetch_one(
                """
                SELECT rx_total
                FROM radio_activity_5m
                WHERE bucket_start_utc = ? AND source_name = 'Main TNC'
                """,
                (bucket_start.isoformat(),),
            )
            self.assertIsNotNone(activity_row)
            assert activity_row is not None
            self.assertEqual(int(activity_row["rx_total"]), 1)

    def test_aggregates_single_closed_bucket_and_saves_state(self) -> None:
        with temporary_database():
            execute(
                """
                UPDATE station_settings
                SET callsign = 'SQ9MDD', ssid = '4', updated_at = ?
                WHERE id = 1
                """,
                (datetime.now(timezone.utc).replace(microsecond=0).isoformat(),),
            )
            execute(
                """
                UPDATE wx_config
                SET callsign = 'SQ9MDD', ssid = '13', enabled = 1, updated_at = ?
                WHERE id = 1
                """,
                (datetime.now(timezone.utc).replace(microsecond=0).isoformat(),),
            )

            bucket_start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS,WIDE1-1*::SQ9MDD-4 :hello{01",
                created_at=(bucket_start + timedelta(minutes=1)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS::APRS:?APRSD",
                created_at=(bucket_start + timedelta(minutes=2)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="TX",
                frame_format="TNC2-TX",
                line="SQ9MDD-4>APRS:!5218.37N/02104.87E>Own",
                command="TX",
                created_at=(bucket_start + timedelta(minutes=3)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="TX",
                frame_format="TNC2-TX",
                line="SP9XYZ-1>APRS::SQ9MDD-4 :relay{02",
                command="TX",
                created_at=(bucket_start + timedelta(minutes=3, seconds=30)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="TX",
                frame_format="TNC2-TX",
                line="SQ9MDD-4>APRS:>TX skipped",
                command="TX-SKIP",
                created_at=(bucket_start + timedelta(minutes=4)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP7AAA-1>APRS,RFONLY:!5218.37N/02104.87E>Rf",
                created_at=(bucket_start + timedelta(minutes=4, seconds=20)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="not-a-valid-tnc2-line",
                created_at=(bucket_start + timedelta(minutes=4, seconds=40)).isoformat(),
            )

            result = run_radio_activity_aggregation(
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=30,
            )
            self.assertGreaterEqual(int(result.get("processed_buckets") or 0), 1)

            row = fetch_one(
                """
                SELECT *
                FROM radio_activity_5m
                WHERE bucket_start_utc = ?
                  AND source_name = 'Main TNC'
                """,
                (bucket_start.isoformat(),),
            )
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row["rx_total"]), 4)
            self.assertEqual(int(row["tx_total"]), 2)
            self.assertEqual(int(row["digipeated_total"]), 1)
            self.assertEqual(int(row["own_frames_total"]), 2)
            self.assertEqual(int(row["messages_total"]), 2)
            self.assertEqual(int(row["queries_total"]), 1)
            self.assertEqual(int(row["rfonly_total"]), 1)
            self.assertEqual(int(row["parse_error_total"]), 1)
            self.assertEqual(int(row["duplicate_total"]), 0)
            self.assertEqual(int(row["direct_heard_total"]), 2)
            self.assertEqual(int(row["indirect_heard_total"]), 1)
            self.assertEqual(int(row["unique_stations_total"]), 4)

            state = fetch_one(
                """
                SELECT last_processed_bucket_start_utc, last_error
                FROM radio_activity_aggregator_state
                WHERE key = ?
                """,
                ("radio_activity_5m.default",),
            )
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(str(state["last_processed_bucket_start_utc"]), bucket_start.isoformat())
            self.assertFalse(str(state["last_error"] or "").strip())

    def test_reprocessing_bucket_does_not_duplicate_rows(self) -> None:
        with temporary_database():
            bucket_start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS::APRS:?APRSD",
                created_at=(bucket_start + timedelta(minutes=1)).isoformat(),
            )
            run_radio_activity_aggregation(
                state_key="radio_activity.replay.a",
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=30,
            )
            run_radio_activity_aggregation(
                state_key="radio_activity.replay.b",
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=30,
            )
            count_row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM radio_activity_5m
                WHERE bucket_start_utc = ?
                  AND source_name = 'Main TNC'
                """,
                (bucket_start.isoformat(),),
            )
            self.assertIsNotNone(count_row)
            assert count_row is not None
            self.assertEqual(int(count_row["total"]), 1)

    def test_open_bucket_is_not_aggregated(self) -> None:
        with temporary_database():
            bucket_start = datetime(2026, 5, 4, 10, 5, tzinfo=timezone.utc)
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8ABC-9>APRS::APRS:?APRSD",
                created_at=(bucket_start + timedelta(minutes=1)).isoformat(),
            )
            run_radio_activity_aggregation(
                now_utc=datetime(2026, 5, 4, 10, 7, tzinfo=timezone.utc),
                safety_delay_seconds=45,
            )
            row = fetch_one(
                """
                SELECT COUNT(*) AS total
                FROM radio_activity_5m
                WHERE bucket_start_utc = ?
                """,
                (bucket_start.isoformat(),),
            )
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(int(row["total"]), 0)

    def test_dashboard_downsampling_for_long_ranges(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket_start = _floor_to_bucket_start(now_utc - timedelta(hours=2), bucket_minutes=5)
            bucket_end = bucket_start + timedelta(minutes=5)
            execute(
                """
                INSERT INTO radio_activity_5m(
                    bucket_start_utc, bucket_end_utc, interface_id, source_name,
                    rx_total, tx_total, digipeated_total, own_frames_total,
                    messages_total, queries_total, objects_total, wx_total,
                    position_total, mobile_total, fixed_total, unique_stations_total,
                    direct_heard_total, indirect_heard_total, rfonly_total, nogate_total,
                    invalid_total, parse_error_total, duplicate_total, max_hops_seen, avg_hops,
                    created_at_utc, updated_at_utc
                )
                VALUES (
                    ?, ?, 1, 'Main TNC',
                    8, 3, 1, 1,
                    2, 1, 0, 0,
                    3, 1, 1, 2,
                    1, 1, 0, 0,
                    0, 0, 0, 2, 1.5,
                    ?, ?
                )
                """,
                (bucket_start.isoformat(), bucket_end.isoformat(), now_utc.isoformat(), now_utc.isoformat()),
            )

            payload_30d = get_dashboard_radio_activity(range_value="30d")
            self.assertEqual(payload_30d["range"], "30d")
            self.assertTrue(bool(payload_30d.get("downsampled")))
            self.assertGreater(int(payload_30d["output_bucket_minutes"]), 5)
            self.assertLessEqual(int(payload_30d["points"]), 1200)
            self.assertEqual(len(payload_30d["labels"]), int(payload_30d["points"]))

            payload_365d = get_dashboard_radio_activity(range_value="365d")
            self.assertEqual(payload_365d["range"], "365d")
            self.assertTrue(bool(payload_365d.get("downsampled")))
            self.assertGreater(int(payload_365d["output_bucket_minutes"]), int(payload_30d["output_bucket_minutes"]))
            self.assertLessEqual(int(payload_365d["points"]), 1200)
            self.assertEqual(len(payload_365d["labels"]), int(payload_365d["points"]))

    def test_dashboard_api_returns_aggregated_series(self) -> None:
        if not FASTAPI_AVAILABLE:
            self.skipTest("fastapi is not installed in this environment")
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket_start = _floor_to_bucket_start(now_utc - timedelta(minutes=10), bucket_minutes=5)
            bucket_end = bucket_start + timedelta(minutes=5)
            hour_start = bucket_start.replace(minute=0, second=0, microsecond=0)
            execute(
                """
                INSERT INTO radio_activity_5m(
                    bucket_start_utc, bucket_end_utc, interface_id, source_name,
                    rx_total, tx_total, digipeated_total, own_frames_total,
                    messages_total, queries_total, objects_total, wx_total,
                    position_total, mobile_total, fixed_total, unique_stations_total,
                    direct_heard_total, indirect_heard_total, rfonly_total, nogate_total,
                    invalid_total, parse_error_total, duplicate_total, max_hops_seen, avg_hops,
                    created_at_utc, updated_at_utc
                )
                VALUES (
                    ?, ?, 1, 'Main TNC',
                    5, 2, 1, 1,
                    3, 1, 0, 0,
                    4, 1, 2, 3,
                    2, 1, 0, 0,
                    0, 0, 0, 1, 1.0,
                    ?, ?
                )
                """,
                (bucket_start.isoformat(), bucket_end.isoformat(), now_utc.isoformat(), now_utc.isoformat()),
            )
            for station_key in ("SP5ABC-1", "SP5XYZ-2"):
                execute(
                    """
                    INSERT INTO traffic_device_station_device_hourly(
                        bucket_start_utc, station_key, device_key, destination_key,
                        device_label, recognized_flag, frame_count, last_seen_at
                    )
                    VALUES (?, ?, 'unknown', 'APRS', 'Unknown', 0, 1, ?)
                    """,
                    (hour_start.isoformat(), station_key, bucket_start.isoformat()),
                )

            from fastapi.testclient import TestClient
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
                response = client.get("/api/dashboard/radio-activity?range=24h")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("series", payload)
                self.assertIn("rx_total", payload["series"])
                self.assertGreaterEqual(sum(payload["series"]["rx_total"]), 5)
                self.assertEqual(payload.get("range"), "24h")
                self.assertEqual(int((payload.get("kpis") or {}).get("heard_stations") or 0), 2)
                self.assertEqual(int((payload.get("kpis") or {}).get("aprs_frames") or 0), 5)

                response_1h = client.get("/api/dashboard/radio-activity?range=1h")
                self.assertEqual(response_1h.status_code, 200)
                payload_1h = response_1h.json()
                self.assertEqual(payload_1h.get("range"), "1h")
                self.assertEqual(int(payload_1h.get("output_bucket_minutes") or 0), 5)
                self.assertFalse(bool(payload_1h.get("downsampled")))
                self.assertEqual(int((payload_1h.get("kpis") or {}).get("heard_stations") or 0), 2)
                self.assertEqual(int((payload_1h.get("kpis") or {}).get("aprs_frames") or 0), 5)

                response_3h = client.get("/api/dashboard/radio-activity?range=3h")
                self.assertEqual(response_3h.status_code, 200)
                payload_3h = response_3h.json()
                self.assertEqual(payload_3h.get("range"), "3h")
                self.assertEqual(int(payload_3h.get("output_bucket_minutes") or 0), 5)
                self.assertFalse(bool(payload_3h.get("downsampled")))

                response_6h = client.get("/api/dashboard/radio-activity?range=6h")
                self.assertEqual(response_6h.status_code, 200)
                payload_6h = response_6h.json()
                self.assertEqual(payload_6h.get("range"), "6h")
                self.assertEqual(int(payload_6h.get("output_bucket_minutes") or 0), 5)
                self.assertFalse(bool(payload_6h.get("downsampled")))

                response_12h = client.get("/api/dashboard/radio-activity?range=12h")
                self.assertEqual(response_12h.status_code, 200)
                payload_12h = response_12h.json()
                self.assertEqual(payload_12h.get("range"), "12h")
                self.assertEqual(int(payload_12h.get("output_bucket_minutes") or 0), 5)
                self.assertFalse(bool(payload_12h.get("downsampled")))

                response_7d = client.get("/api/dashboard/radio-activity?range=7d")
                self.assertEqual(response_7d.status_code, 200)
                payload_7d = response_7d.json()
                self.assertEqual(payload_7d.get("range"), "7d")
                self.assertEqual(len(payload_7d.get("labels") or []), 2016)
                self.assertEqual(
                    len(payload_7d.get("labels") or []),
                    len(payload_7d.get("bucket_starts_utc") or []),
                )
                self.assertEqual(int(payload_7d.get("output_bucket_minutes") or 0), 5)
                self.assertFalse(bool(payload_7d.get("downsampled")))

                response_30d = client.get("/api/dashboard/radio-activity?range=30d")
                self.assertEqual(response_30d.status_code, 200)
                payload_30d = response_30d.json()
                self.assertEqual(payload_30d.get("range"), "30d")
                self.assertTrue(bool(payload_30d.get("downsampled")))
                self.assertGreater(int(payload_30d.get("output_bucket_minutes") or 0), 5)
                self.assertLessEqual(int(payload_30d.get("points") or 0), 1200)

                response_365d = client.get("/api/dashboard/radio-activity?range=365d")
                self.assertEqual(response_365d.status_code, 200)
                payload_365d = response_365d.json()
                self.assertEqual(payload_365d.get("range"), "365d")
                self.assertTrue(bool(payload_365d.get("downsampled")))
                self.assertGreater(
                    int(payload_365d.get("output_bucket_minutes") or 0),
                    int(payload_30d.get("output_bucket_minutes") or 0),
                )

                unsupported = client.get("/api/dashboard/radio-activity?range=2h")
                self.assertEqual(unsupported.status_code, 400)
            finally:
                app.dependency_overrides.clear()

    def test_statistics_api_returns_aggregated_series(self) -> None:
        if not FASTAPI_AVAILABLE:
            self.skipTest("fastapi is not installed in this environment")
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket_start = _floor_to_bucket_start(now_utc - timedelta(minutes=10), bucket_minutes=5)
            bucket_end = bucket_start + timedelta(minutes=5)
            execute(
                """
                INSERT INTO radio_activity_5m(
                    bucket_start_utc, bucket_end_utc, interface_id, source_name,
                    rx_total, tx_total, digipeated_total, own_frames_total,
                    messages_total, queries_total, objects_total, wx_total,
                    position_total, mobile_total, fixed_total, unique_stations_total,
                    direct_heard_total, indirect_heard_total, rfonly_total, nogate_total,
                    invalid_total, parse_error_total, duplicate_total,
                    type_position_total, type_weather_total, type_message_total, type_object_item_total,
                    type_status_total, type_telemetry_total, type_query_total, type_user_defined_total,
                    type_third_party_total, type_other_unknown_total,
                    max_hops_seen, avg_hops,
                    created_at_utc, updated_at_utc
                )
                VALUES (
                    ?, ?, 1, 'Main TNC',
                    10, 4, 2, 1,
                    3, 1, 1, 1,
                    4, 2, 2, 5,
                    6, 2, 0, 0,
                    0, 0, 0,
                    4, 1, 2, 1,
                    1, 1, 1, 0,
                    0, 0,
                    2, 1.5,
                    ?, ?
                )
                """,
                (bucket_start.isoformat(), bucket_end.isoformat(), now_utc.isoformat(), now_utc.isoformat()),
            )

            from fastapi.testclient import TestClient
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
                response = client.get("/api/statistics/traffic?range=24h")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload.get("range"), "24h")
                self.assertEqual(int(payload.get("bucket_minutes") or 0), 60)
                self.assertIn("charts", payload)
                self.assertIn("frame_types", payload["charts"])
                self.assertIn("heard", payload["charts"])
                self.assertIn("actions", payload["charts"])

                frame_types = payload["charts"]["frame_types"]["series"]
                series_by_key = {item.get("key"): item for item in frame_types}
                self.assertIn("position", series_by_key)
                self.assertGreaterEqual(sum(series_by_key["position"].get("data") or []), 4)

                heard = payload["charts"]["heard"]["series"]
                heard_by_key = {item.get("key"): item for item in heard}
                self.assertGreaterEqual(sum(heard_by_key["direct_heard"].get("data") or []), 6)
                self.assertGreaterEqual(sum(heard_by_key["all_heard"].get("data") or []), 10)

                actions = payload["charts"]["actions"]["series"]
                action_keys = {item.get("key") for item in actions}
                self.assertIn("filtered_dropped", action_keys)
                self.assertNotIn("duplicate_ignored", action_keys)

                response_year = client.get("/api/statistics/traffic?range=365d")
                self.assertEqual(response_year.status_code, 200)
                payload_year = response_year.json()
                self.assertEqual(payload_year.get("range"), "365d")
                self.assertEqual(int(payload_year.get("bucket_minutes") or 0), 1440)

                response_7d = client.get("/api/statistics/traffic?range=7d")
                self.assertEqual(response_7d.status_code, 200)
                payload_7d = response_7d.json()
                self.assertEqual(payload_7d.get("range"), "7d")
                self.assertEqual(int(payload_7d.get("bucket_minutes") or 0), 1440)
                frame_types_7d = payload_7d["charts"]["frame_types"]["series"]
                series_7d_by_key = {item.get("key"): item for item in frame_types_7d}
                self.assertGreaterEqual(sum(series_7d_by_key["position"].get("data") or []), 4)

                response_shift = client.get("/api/statistics/traffic?range=24h&shift=1")
                self.assertEqual(response_shift.status_code, 200)
                payload_shift = response_shift.json()
                self.assertEqual(payload_shift.get("range"), "24h")
                self.assertEqual(int(payload_shift.get("bucket_minutes") or 0), 60)
                self.assertEqual(str(payload_shift.get("window_end_utc") or ""), str(payload.get("window_start_utc") or ""))

                unsupported = client.get("/api/statistics/traffic?range=2h")
                self.assertEqual(unsupported.status_code, 400)
                invalid_shift = client.get("/api/statistics/traffic?range=24h&shift=-1")
                self.assertEqual(invalid_shift.status_code, 400)
            finally:
                app.dependency_overrides.clear()

    def test_traffic_devices_statistics_counts_unique_stations_by_default(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=15)

            for index in range(20):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP1AAA-1>APA001,WIDE1-1:>a",
                    created_at=(base_time + timedelta(seconds=index)).isoformat(),
                )

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP2BBB-2>APA002,WIDE1-1:>b",
                created_at=(base_time + timedelta(seconds=25)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP3CCC-3>APA003,WIDE1-1:>c",
                created_at=(base_time + timedelta(seconds=26)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP4DDD-4>APA004,WIDE1-1:>d",
                created_at=(base_time + timedelta(seconds=27)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP4DDD-4>APA005,WIDE1-1:>e",
                created_at=(base_time + timedelta(seconds=28)).isoformat(),
            )

            for index in range(10):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="TX",
                    frame_format="TNC2-TX",
                    line="SP9TX-1>TX9999:>tx",
                    command="TX",
                    created_at=(base_time + timedelta(seconds=120 + index)).isoformat(),
                )

            stations_payload = get_traffic_devices_statistics(range_value="24h")
            self.assertEqual(stations_payload.get("window"), "range")
            self.assertEqual(stations_payload.get("count_basis"), "unique_callsign_ssid_per_model")
            self.assertEqual(int(stations_payload.get("unique_station_keys_total") or 0), 4)
            self.assertEqual(int(stations_payload.get("unique_station_device_pairs_total") or 0), 4)
            self.assertEqual(int(stations_payload.get("unique_callsign_ssid_tocall_pairs_total") or 0), 5)
            self.assertEqual(int(stations_payload.get("total") or 0), 4)
            station_items = list(stations_payload.get("items") or [])
            station_counts = [int(item.get("count") or 0) for item in station_items]
            self.assertEqual(sum(station_counts), 4)
            unknown_item = next((item for item in station_items if str(item.get("key") or "") == "unknown"), None)
            self.assertIsNotNone(unknown_item)
            self.assertEqual(int((unknown_item or {}).get("count") or 0), 4)
            self.assertEqual(len(list((unknown_item or {}).get("entries") or [])), 4)

            shifted_payload = get_traffic_devices_statistics(range_value="24h", shift_windows=1)
            self.assertEqual(shifted_payload.get("window"), "range")
            self.assertEqual(shifted_payload.get("count_basis"), "unique_callsign_ssid_per_model")
            self.assertEqual(int(shifted_payload.get("total") or 0), 0)

    def test_traffic_devices_range_uses_buffer_when_traffic_frames_are_pruned(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            old_timestamp = (now_utc - timedelta(hours=2)).isoformat()
            line = "SP8OLD-7>APY05D,WIDE1-1:>legacy"

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line=line,
                created_at=old_timestamp,
            )
            record_traffic_device_station_observation(
                frame_format="TNC2",
                line=line,
                timestamp=old_timestamp,
            )

            execute(
                "DELETE FROM traffic_frames WHERE created_at < ?",
                ((now_utc - timedelta(hours=1)).isoformat(),),
            )

            payload = get_traffic_devices_statistics(range_value="24h")
            self.assertEqual(int(payload.get("total") or 0), 1)
            self.assertEqual(payload.get("count_basis"), "unique_callsign_ssid_per_model")
            self.assertEqual(payload.get("window"), "range")

    def test_traffic_devices_counts_station_in_each_observed_device_bucket(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=10)

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8AAA-1>APK005,WIDE1-1:>d75",
                created_at=(base_time + timedelta(seconds=1)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8AAA-1>APY05D,WIDE1-1:>ft5d",
                created_at=(base_time + timedelta(seconds=2)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8BBB-2>APK005,WIDE1-1:>d75",
                created_at=(base_time + timedelta(seconds=3)).isoformat(),
            )

            payload = get_traffic_devices_statistics(range_value="24h")
            self.assertEqual(payload.get("count_basis"), "unique_callsign_ssid_per_model")
            self.assertEqual(int(payload.get("total") or 0), 3)

            items = list(payload.get("items") or [])
            counts_by_key = {
                str(item.get("key") or ""): int(item.get("count") or 0)
                for item in items
            }
            self.assertEqual(int(counts_by_key.get("APK005") or 0), 2)
            self.assertEqual(int(counts_by_key.get("APY05D") or 0), 1)
            apy05d_item = next((item for item in items if str(item.get("key") or "") == "APY05D"), None)
            self.assertIsNotNone(apy05d_item)
            apy_entries = list((apy05d_item or {}).get("entries") or [])
            self.assertEqual(len(apy_entries), 1)
            self.assertEqual(str((apy_entries[0] or {}).get("callsign_ssid") or ""), "SP8AAA-1")
            self.assertEqual(str((apy_entries[0] or {}).get("tocall") or ""), "APY05D")

    def test_traffic_devices_merges_same_model_from_multiple_identifiers(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=10)

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8AAA-1>APNK01,WIDE1-1:>d700",
                created_at=(base_time + timedelta(seconds=1)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8BBB-2>APK123,WIDE1-1:>d700",
                created_at=(base_time + timedelta(seconds=2)).isoformat(),
            )

            payload = get_traffic_devices_statistics(range_value="24h")
            items = list(payload.get("items") or [])
            tm_d700_items = [item for item in items if str(item.get("label") or "") == "TM-D700"]
            self.assertEqual(len(tm_d700_items), 1)
            self.assertEqual(int(tm_d700_items[0].get("count") or 0), 2)
            self.assertEqual(len(list(tm_d700_items[0].get("entries") or [])), 2)

    def test_traffic_devices_deduplicates_station_with_multiple_identifiers_of_same_model(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=10)

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8AAA-1>APNK01,WIDE1-1:>d700-a",
                created_at=(base_time + timedelta(seconds=1)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8AAA-1>APK123,WIDE1-1:>d700-b",
                created_at=(base_time + timedelta(seconds=2)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8BBB-2>APNK01,WIDE1-1:>d700-c",
                created_at=(base_time + timedelta(seconds=3)).isoformat(),
            )

            payload = get_traffic_devices_statistics(range_value="24h")
            self.assertEqual(int(payload.get("unique_station_keys_total") or 0), 2)
            self.assertEqual(int(payload.get("unique_station_device_pairs_total") or 0), 2)
            items = list(payload.get("items") or [])
            tm_d700_item = next((item for item in items if str(item.get("label") or "") == "TM-D700"), None)
            self.assertIsNotNone(tm_d700_item)
            self.assertEqual(int((tm_d700_item or {}).get("count") or 0), 2)
            tm_entries = list((tm_d700_item or {}).get("entries") or [])
            self.assertEqual(len(tm_entries), 2)
            sp8aaa_entry = next((entry for entry in tm_entries if str(entry.get("callsign_ssid") or "") == "SP8AAA-1"), None)
            self.assertIsNotNone(sp8aaa_entry)
            self.assertEqual(sorted(list((sp8aaa_entry or {}).get("tocalls") or [])), ["APK123", "APNK01"])

    def test_traffic_devices_exposes_entries_for_unknown_model(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=10)

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP8AAA-1>APRS,WIDE1-1:>generic",
                created_at=(base_time + timedelta(seconds=1)).isoformat(),
            )

            payload = get_traffic_devices_statistics(range_value="24h")
            items = list(payload.get("items") or [])
            unknown_item = next((item for item in items if str(item.get("key") or "") == "unknown"), None)
            self.assertIsNotNone(unknown_item)
            self.assertEqual(str((unknown_item or {}).get("ident") or ""), "unknown")
            self.assertEqual(int((unknown_item or {}).get("count") or 0), 1)
            entries = list((unknown_item or {}).get("entries") or [])
            self.assertEqual(len(entries), 1)
            self.assertEqual(str((entries[0] or {}).get("callsign_ssid") or ""), "SP8AAA-1")
            self.assertEqual(str((entries[0] or {}).get("tocall") or ""), "APRS")

    def test_traffic_devices_counts_missing_tocall_once_per_station_pair(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket_start_older = _floor_to_bucket_start(now_utc - timedelta(hours=3), bucket_minutes=60).isoformat()
            bucket_start_newer = _floor_to_bucket_start(now_utc - timedelta(hours=2), bucket_minutes=60).isoformat()
            last_seen_old = (now_utc - timedelta(hours=3)).isoformat()
            last_seen_new = (now_utc - timedelta(hours=2)).isoformat()

            with connect() as connection:
                connection.execute(
                    """
                    INSERT INTO traffic_device_station_device_hourly(
                        bucket_start_utc, station_key, device_key, destination_key,
                        device_label, recognized_flag, frame_count, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0, 5, ?)
                    """,
                    (
                        bucket_start_older,
                        "SP8AAA-1",
                        "unknown",
                        "",
                        "Unknown",
                        last_seen_old,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO traffic_device_station_device_hourly(
                        bucket_start_utc, station_key, device_key, destination_key,
                        device_label, recognized_flag, frame_count, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0, 8, ?)
                    """,
                    (
                        bucket_start_newer,
                        "SP8AAA-1",
                        "unknown",
                        "",
                        "Unknown",
                        last_seen_new,
                    ),
                )

            payload = get_traffic_devices_statistics(range_value="24h")
            self.assertEqual(int(payload.get("total") or 0), 1)
            items = list(payload.get("items") or [])
            unknown_item = next((item for item in items if str(item.get("key") or "") == "unknown"), None)
            self.assertIsNotNone(unknown_item)
            self.assertEqual(int((unknown_item or {}).get("count") or 0), 1)
            entries = list((unknown_item or {}).get("entries") or [])
            self.assertEqual(len(entries), 1)
            self.assertEqual(str((entries[0] or {}).get("callsign_ssid") or ""), "SP8AAA-1")
            self.assertEqual(str((entries[0] or {}).get("tocall") or ""), "UNKNOWN")

    def test_traffic_devices_collapses_non_tocall_destinations_to_unknown_pair(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=10)

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP5MRF-9>UR1P88,WIDE1-1:>x",
                created_at=(base_time + timedelta(seconds=1)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP5MRF-9>UR1P89,WIDE1-1:>y",
                created_at=(base_time + timedelta(seconds=2)).isoformat(),
            )

            payload = get_traffic_devices_statistics(range_value="24h")
            self.assertEqual(int(payload.get("total") or 0), 1)
            items = list(payload.get("items") or [])
            unknown_item = next((item for item in items if str(item.get("key") or "") == "unknown"), None)
            self.assertIsNotNone(unknown_item)
            self.assertEqual(int((unknown_item or {}).get("count") or 0), 1)
            entries = list((unknown_item or {}).get("entries") or [])
            self.assertEqual(len(entries), 1)
            self.assertEqual(str((entries[0] or {}).get("callsign_ssid") or ""), "SP5MRF-9")
            self.assertEqual(str((entries[0] or {}).get("tocall") or ""), "UNKNOWN")

    def test_traffic_devices_top_list_is_capped_to_top_limit(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket_start_utc = _floor_to_bucket_start(now_utc - timedelta(hours=1), bucket_minutes=60).isoformat()
            last_seen_at = now_utc.isoformat()

            with connect() as connection:
                for index in range(25):
                    device_key = f"DEV{index:02d}"
                    station_key = f"SP8{index:03d}-1"
                    destination_key = f"AP{index:04d}"
                    device_label = f"Device {index:02d}"
                    connection.execute(
                        """
                        INSERT INTO traffic_device_station_device_hourly(
                            bucket_start_utc, station_key, device_key, destination_key,
                            device_label, recognized_flag, frame_count, last_seen_at
                        )
                        VALUES (?, ?, ?, ?, ?, 1, 1, ?)
                        """,
                        (
                            bucket_start_utc,
                            station_key,
                            device_key,
                            destination_key,
                            device_label,
                            last_seen_at,
                        ),
                    )

            payload = get_traffic_devices_statistics(range_value="24h")
            items = list(payload.get("items") or [])
            self.assertEqual(len(items), 20)
            for item in items:
                self.assertEqual(int(item.get("count") or 0), len(list(item.get("entries") or [])))
            other_item = next((item for item in items if str(item.get("key") or "") == "other"), None)
            self.assertIsNotNone(other_item)
            self.assertEqual(int((other_item or {}).get("count") or 0), 6)
            self.assertEqual(len(list((other_item or {}).get("entries") or [])), 6)

    def test_traffic_devices_merges_unknown_synonyms_into_single_bucket(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            bucket_start_utc = _floor_to_bucket_start(now_utc - timedelta(hours=1), bucket_minutes=60).isoformat()
            last_seen_at = now_utc.isoformat()

            with connect() as connection:
                connection.execute(
                    """
                    INSERT INTO traffic_device_station_device_hourly(
                        bucket_start_utc, station_key, device_key, destination_key,
                        device_label, recognized_flag, frame_count, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0, 1, ?)
                    """,
                    (
                        bucket_start_utc,
                        "SP8AAA-1",
                        "unknown",
                        "APRS",
                        "Unknown",
                        last_seen_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO traffic_device_station_device_hourly(
                        bucket_start_utc, station_key, device_key, destination_key,
                        device_label, recognized_flag, frame_count, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0, 1, ?)
                    """,
                    (
                        bucket_start_utc,
                        "SP8BBB-2",
                        "DEVZZ",
                        "APRS",
                        "Nieznany",
                        last_seen_at,
                    ),
                )

            payload = get_traffic_devices_statistics(range_value="24h")
            items = list(payload.get("items") or [])
            unknown_items = [item for item in items if str(item.get("key") or "") == "unknown"]
            self.assertEqual(len(unknown_items), 1)
            self.assertEqual(int(unknown_items[0].get("count") or 0), 2)
            self.assertEqual(len(list(unknown_items[0].get("entries") or [])), 2)

    def test_traffic_users_statistics_counts_frames_per_station(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=15)

            for index in range(20):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP1AAA-1>QZ1234,WIDE1-1:>a",
                    created_at=(base_time + timedelta(seconds=index)).isoformat(),
                )
            for index in range(2):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP2BBB-2>QZ1234,WIDE1-1:>b",
                    created_at=(base_time + timedelta(seconds=40 + index)).isoformat(),
                )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP3CCC-3>QZ1234,WIDE1-1:>c",
                created_at=(base_time + timedelta(seconds=50)).isoformat(),
            )
            for index in range(4):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="TX",
                    frame_format="TNC2-TX",
                    line="SP9TX-1>TX9999:>tx",
                    command="TX",
                    created_at=(base_time + timedelta(seconds=80 + index)).isoformat(),
                )

            payload = get_traffic_users_statistics(range_value="24h")
            self.assertEqual(payload.get("count_basis"), "frames_rx_tnc2")
            self.assertEqual(int(payload.get("total") or 0), 23)
            items = list(payload.get("items") or [])
            self.assertGreaterEqual(len(items), 1)
            self.assertEqual(str(items[0].get("key") or ""), "SP1AAA-1")
            self.assertEqual(int(items[0].get("count") or 0), 20)

            shifted_payload = get_traffic_users_statistics(range_value="24h", shift_windows=1)
            self.assertEqual(int(shifted_payload.get("total") or 0), 0)

    def test_traffic_users_statistics_aggregates_station_frames_across_multiple_device_keys(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=15)

            for index in range(3):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP8AAA-1>APNK01,WIDE1-1:>d700-a",
                    created_at=(base_time + timedelta(seconds=index)).isoformat(),
                )
            for index in range(2):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP8AAA-1>APK123,WIDE1-1:>d700-b",
                    created_at=(base_time + timedelta(seconds=10 + index)).isoformat(),
                )

            payload = get_traffic_users_statistics(range_value="24h")
            items = list(payload.get("items") or [])
            self.assertGreaterEqual(len(items), 1)
            self.assertEqual(str(items[0].get("key") or ""), "SP8AAA-1")
            self.assertEqual(int(items[0].get("count") or 0), 5)

    def test_traffic_direct_heard_statistics_counts_only_frames_without_consumed_hops(self) -> None:
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=10)

            for index in range(5):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP1AAA-1>QZ1234,WIDE1-1:>direct",
                    created_at=(base_time + timedelta(seconds=index)).isoformat(),
                )
            for index in range(3):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP2BBB-2>QZ1234,SR9XYZ*,WIDE1-1:>digipeated",
                    created_at=(base_time + timedelta(seconds=20 + index)).isoformat(),
                )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP3CCC-3>QZ1234:>direct-no-path",
                created_at=(base_time + timedelta(seconds=40)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="TX",
                frame_format="TNC2-TX",
                line="SP9TX-1>TX9999:>tx",
                command="TX",
                created_at=(base_time + timedelta(seconds=50)).isoformat(),
            )

            payload = get_traffic_direct_heard_statistics(range_value="24h")
            self.assertEqual(payload.get("count_basis"), "frames_rx_tnc2_direct_heard")
            self.assertEqual(int(payload.get("total") or 0), 6)
            items = list(payload.get("items") or [])
            self.assertGreaterEqual(len(items), 2)
            self.assertEqual(str(items[0].get("key") or ""), "SP1AAA-1")
            self.assertEqual(int(items[0].get("count") or 0), 5)
            self.assertEqual(str(items[1].get("key") or ""), "SP3CCC-3")
            self.assertEqual(int(items[1].get("count") or 0), 1)

            shifted_payload = get_traffic_direct_heard_statistics(range_value="24h", shift_windows=1)
            self.assertEqual(int(shifted_payload.get("total") or 0), 0)

    def test_statistics_devices_api_supports_main_range_windows(self) -> None:
        if not FASTAPI_AVAILABLE:
            self.skipTest("fastapi is not installed in this environment")
        with temporary_database():
            now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            base_time = now_utc - timedelta(minutes=15)

            for index in range(20):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="RX",
                    frame_format="TNC2",
                    line="SP1AAA-1>QZ1234,WIDE1-1:>a",
                    created_at=(base_time + timedelta(seconds=index)).isoformat(),
                )

            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP2BBB-2>WZ5678,WIDE1-1:>b",
                created_at=(base_time + timedelta(seconds=25)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP3CCC-3>XZ9ABC,WIDE1-1:>c",
                created_at=(base_time + timedelta(seconds=26)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP4DDD-4>YZ9AAA,WIDE1-1:>d",
                created_at=(base_time + timedelta(seconds=27)).isoformat(),
            )
            insert_frame(
                source="Main TNC",
                interface_id=1,
                direction="RX",
                frame_format="TNC2",
                line="SP4DDD-4>YZ9BBB,WIDE1-1:>e",
                created_at=(base_time + timedelta(seconds=28)).isoformat(),
            )

            for index in range(10):
                insert_frame(
                    source="Main TNC",
                    interface_id=1,
                    direction="TX",
                    frame_format="TNC2-TX",
                    line="SP9TX-1>TX9999:>tx",
                    command="TX",
                    created_at=(base_time + timedelta(seconds=120 + index)).isoformat(),
                )

            from fastapi.testclient import TestClient
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

                stations_response = client.get("/api/statistics/devices?range=24h")
                self.assertEqual(stations_response.status_code, 200)
                stations_payload = stations_response.json()
                self.assertEqual(stations_payload.get("window"), "range")
                self.assertEqual(stations_payload.get("count_basis"), "unique_callsign_ssid_per_model")
                self.assertEqual(int(stations_payload.get("total") or 0), 5)
                station_items = list(stations_payload.get("items") or [])
                station_counts = [int(item.get("count") or 0) for item in station_items]
                self.assertEqual(sum(station_counts), 5)
                unknown_item = next((item for item in station_items if str(item.get("key") or "") == "unknown"), None)
                self.assertIsNotNone(unknown_item)
                self.assertEqual(int((unknown_item or {}).get("count") or 0), 5)
                self.assertEqual(len(list((unknown_item or {}).get("entries") or [])), 5)

                shifted_response = client.get("/api/statistics/devices?range=24h&shift=1")
                self.assertEqual(shifted_response.status_code, 200)
                shifted_payload = shifted_response.json()
                self.assertEqual(shifted_payload.get("window"), "range")
                self.assertEqual(shifted_payload.get("count_basis"), "unique_callsign_ssid_per_model")
                self.assertEqual(int(shifted_payload.get("total") or 0), 0)

                hour_response = client.get("/api/statistics/devices?range=1h")
                self.assertEqual(hour_response.status_code, 200)

                users_response = client.get("/api/statistics/users?range=24h")
                self.assertEqual(users_response.status_code, 200)
                users_payload = users_response.json()
                self.assertEqual(users_payload.get("count_basis"), "frames_rx_tnc2")
                self.assertEqual(int(users_payload.get("total") or 0), 24)
                users_items = list(users_payload.get("items") or [])
                self.assertGreaterEqual(len(users_items), 1)
                self.assertEqual(str(users_items[0].get("key") or ""), "SP1AAA-1")
                self.assertEqual(int(users_items[0].get("count") or 0), 20)

                users_shifted_response = client.get("/api/statistics/users?range=24h&shift=1")
                self.assertEqual(users_shifted_response.status_code, 200)
                users_shifted_payload = users_shifted_response.json()
                self.assertEqual(int(users_shifted_payload.get("total") or 0), 0)

                users_hour_response = client.get("/api/statistics/users?range=1h")
                self.assertEqual(users_hour_response.status_code, 200)

                direct_heard_response = client.get("/api/statistics/direct-heard?range=24h")
                self.assertEqual(direct_heard_response.status_code, 200)
                direct_heard_payload = direct_heard_response.json()
                self.assertEqual(direct_heard_payload.get("count_basis"), "frames_rx_tnc2_direct_heard")
                self.assertEqual(int(direct_heard_payload.get("total") or 0), 24)

                direct_heard_shifted_response = client.get("/api/statistics/direct-heard?range=24h&shift=1")
                self.assertEqual(direct_heard_shifted_response.status_code, 200)
                direct_heard_shifted_payload = direct_heard_shifted_response.json()
                self.assertEqual(int(direct_heard_shifted_payload.get("total") or 0), 0)

                invalid_window = client.get("/api/statistics/devices?range=24h&window=invalid")
                self.assertEqual(invalid_window.status_code, 400)
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
