import contextlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import execute, fetch_one, init_db
from app.services.band_condition import (
    _confidence_score,
    _evaluate_hour,
    _model_progress,
    _score_condition,
    aggregate_band_condition_bucket,
    format_band_label,
    get_band_condition_history,
    monitored_band_options,
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


def insert_interface(*, band: str) -> int:
    execute(
        """
        INSERT INTO modems(
            name, modem_type, band, device_path, enabled, notes, created_at, updated_at
        )
        VALUES (?, 'TCP', ?, '127.0.0.1:8001', 1, '', ?, ?)
        """,
        (f"RF-{band or 'off'}", band, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    row = fetch_one("SELECT id FROM modems WHERE name = ?", (f"RF-{band or 'off'}",))
    assert row is not None
    return int(row["id"])


class BandConditionHelpersTests(unittest.TestCase):
    def test_interface_assessment_defaults_to_disabled_and_supports_only_requested_bands(self) -> None:
        self.assertEqual(
            [item["value"] for item in monitored_band_options()],
            ["", "2m", "70cm"],
        )

    def test_format_band_label_preserves_supported_band_names(self) -> None:
        self.assertEqual(format_band_label("2m"), "2m")
        self.assertEqual(format_band_label("70cm"), "70cm")

    def test_w_scale_prioritizes_geographic_opening_evidence(self) -> None:
        common = {
            "normal_station_count": 10.0,
            "normal_p90_distance_km": 120.0,
            "rx_total": 30,
        }
        self.assertEqual(
            _score_condition(
                **common,
                fixed_station_count=17,
                current_p90_distance_km=260.0,
                far_station_count=6,
                confirmed_far_station_count=4,
                very_far_station_count=4,
                confirmed_very_far_station_count=2,
                new_area_count=3,
            ),
            5,
        )
        self.assertEqual(
            _score_condition(
                **common,
                fixed_station_count=11,
                current_p90_distance_km=230.0,
                far_station_count=1,
                confirmed_far_station_count=1,
                very_far_station_count=1,
                confirmed_very_far_station_count=1,
                new_area_count=1,
            ),
            4,
        )
        self.assertEqual(
            _score_condition(
                **common,
                fixed_station_count=14,
                current_p90_distance_km=130.0,
                far_station_count=0,
                confirmed_far_station_count=0,
                very_far_station_count=0,
                confirmed_very_far_station_count=0,
                new_area_count=0,
            ),
            3,
        )
        self.assertEqual(
            _score_condition(
                **common,
                fixed_station_count=10,
                current_p90_distance_km=120.0,
                far_station_count=0,
                confirmed_far_station_count=0,
                very_far_station_count=0,
                confirmed_very_far_station_count=0,
                new_area_count=0,
            ),
            2,
        )

    def test_w_scale_keeps_degradation_coarse(self) -> None:
        common = {
            "normal_station_count": 10.0,
            "current_p90_distance_km": 80.0,
            "normal_p90_distance_km": 120.0,
            "far_station_count": 0,
            "confirmed_far_station_count": 0,
            "very_far_station_count": 0,
            "confirmed_very_far_station_count": 0,
            "new_area_count": 0,
            "rx_total": 10,
        }
        self.assertEqual(_score_condition(**common, fixed_station_count=5), 1)
        self.assertEqual(_score_condition(**common, fixed_station_count=2), 0)
        self.assertIsNone(_score_condition(**{**common, "rx_total": 0}, fixed_station_count=0))

    def test_confidence_increases_with_history_and_station_coverage(self) -> None:
        early = _confidence_score(
            history_hours=24,
            history_span_hours=24,
            baseline_rows=12,
            stable_station_count=3,
            positioned_ratio=0.4,
            current_segment_count=3,
            fixed_station_count=4,
        )
        mature = _confidence_score(
            history_hours=24 * 28,
            history_span_hours=24 * 28,
            baseline_rows=14,
            stable_station_count=16,
            positioned_ratio=0.9,
            current_segment_count=10,
            fixed_station_count=18,
        )
        self.assertGreater(mature, early)
        self.assertLess(early, 0.6)
        self.assertGreater(mature, 0.85)

    def test_first_assessment_appears_after_24_hours_and_detects_opening(self) -> None:
        with temporary_database():
            interface_id = insert_interface(band="2m")
            assessed_hour = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)

            for offset in range(24, 1, -1):
                history_hour = assessed_hour - timedelta(hours=offset)
                execute(
                    """
                    INSERT INTO band_condition_hourly(
                        hour_start_utc, interface_id, interface_name, band,
                        condition_index, confidence_score, fixed_station_count,
                        positioned_station_count, direct_station_count,
                        median_distance_km, p90_distance_km, max_confirmed_distance_km,
                        normal_station_count, normal_p90_distance_km,
                        far_station_count, very_far_station_count, new_area_count,
                        history_hours, created_at
                    )
                    VALUES (?, ?, 'RF-2m', '2m', 2, 0.3, 10, 10, 8,
                            70, 100, 110, 10, 100, 0, 0, 0, ?, ?)
                    """,
                    (
                        history_hour.isoformat(),
                        interface_id,
                        24 - offset,
                        history_hour.isoformat(),
                    ),
                )

            station_distances = [55, 65, 70, 75, 80, 90, 100, 280, 310, 340, 370, 410]
            station_locations = [
                (52.0, 21.0),
                (52.1, 21.1),
                (52.2, 21.2),
                (52.3, 21.3),
                (52.4, 21.4),
                (52.5, 21.5),
                (52.6, 21.6),
                (54.0, 18.0),
                (55.0, 14.0),
                (54.0, 24.0),
                (57.0, 20.0),
                (56.0, 26.0),
            ]
            for index, (distance, location) in enumerate(zip(station_distances, station_locations)):
                execute(
                    """
                    INSERT INTO band_condition_station_hours(
                        hour_start_utc, interface_id, interface_name, band,
                        station_key, segment_mask, direct_segment_mask,
                        fixed_hint, mobile_hint, latitude, longitude, distance_km, updated_at
                    )
                    VALUES (?, ?, 'RF-2m', '2m', ?, 7, 7, 1, 0, ?, ?, ?, ?)
                    """,
                    (
                        assessed_hour.isoformat(),
                        interface_id,
                        f"SP5T{index:02d}",
                        location[0],
                        location[1],
                        distance,
                        assessed_hour.isoformat(),
                    ),
                )
            execute(
                """
                INSERT INTO radio_activity_5m(
                    bucket_start_utc, bucket_end_utc, interface_id, source_name,
                    rx_total, created_at_utc, updated_at_utc
                )
                VALUES (?, ?, ?, 'RF-2m', 50, ?, ?)
                """,
                (
                    assessed_hour.isoformat(),
                    (assessed_hour + timedelta(minutes=5)).isoformat(),
                    interface_id,
                    assessed_hour.isoformat(),
                    assessed_hour.isoformat(),
                ),
            )

            too_early = _evaluate_hour(
                interface_id=interface_id,
                interface_name="RF-2m",
                band="2m",
                hour_start=assessed_hour,
            )
            self.assertFalse(too_early["model_ready"])
            self.assertIsNone(too_early["condition_index"])

            final_history_hour = assessed_hour - timedelta(hours=1)
            execute(
                """
                INSERT INTO band_condition_hourly(
                    hour_start_utc, interface_id, interface_name, band,
                    condition_index, confidence_score, fixed_station_count,
                    positioned_station_count, direct_station_count,
                    median_distance_km, p90_distance_km, max_confirmed_distance_km,
                    normal_station_count, normal_p90_distance_km,
                    far_station_count, very_far_station_count, new_area_count,
                    history_hours, created_at
                )
                VALUES (?, ?, 'RF-2m', '2m', 2, 0.3, 10, 10, 8,
                        70, 100, 110, 10, 100, 0, 0, 0, 23, ?)
                """,
                (
                    final_history_hour.isoformat(),
                    interface_id,
                    final_history_hour.isoformat(),
                ),
            )
            ready = _evaluate_hour(
                interface_id=interface_id,
                interface_name="RF-2m",
                band="2m",
                hour_start=assessed_hour,
            )
            self.assertTrue(ready["model_ready"])
            self.assertEqual(ready["history_hours"], 24)
            self.assertEqual(ready["data_hours"], 24)
            self.assertEqual(ready["condition_index"], 5)

            execute(
                """
                INSERT INTO band_condition_station_profiles(
                    interface_id, band, station_key, first_heard_at, last_heard_at,
                    observed_hours, direct_hours, positioned_hours, fixed_hours, mobile_hours,
                    latitude, longitude, distance_km, updated_at
                )
                VALUES (?, '2m', 'SP5BASE', ?, ?, 8, 6, 8, 8, 0, 52.5, 21.5, 42, ?)
                """,
                (
                    interface_id,
                    (assessed_hour - timedelta(hours=20)).isoformat(),
                    (assessed_hour - timedelta(hours=1)).isoformat(),
                    assessed_hour.isoformat(),
                ),
            )
            progress = _model_progress(
                interface_id,
                "2m",
                assessed_hour,
                model_ready=True,
            )
            self.assertEqual(progress["model_stage_label"], "Initial assessment")
            self.assertEqual(progress["first_assessment_percent"], 100)
            self.assertEqual(progress["maturity_percent"], 3)
            self.assertEqual(progress["days_to_mature"], 29)
            self.assertEqual(progress["data_hours"], 24)
            self.assertEqual(progress["learned_station_count"], 1)
            self.assertEqual(progress["learned_positioned_station_count"], 1)
            self.assertEqual(progress["repeatable_station_count"], 1)

    def test_disabled_interface_does_not_collect_band_condition_rows(self) -> None:
        with temporary_database():
            interface_id = insert_interface(band="")
            bucket_start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
            execute(
                """
                INSERT INTO traffic_frames(
                    source, source_kind, interface_id, direction, band, format, line,
                    port, command, length, hex, created_at
                )
                VALUES ('RF-off', 'rf', ?, 'RX', '', 'TNC2', ?, '', '', 40, '', ?)
                """,
                (
                    interface_id,
                    "SP5ABC>APRS:!5223.45N/02101.23E>Test",
                    (bucket_start + timedelta(minutes=1)).isoformat(),
                ),
            )
            result = aggregate_band_condition_bucket(
                bucket_start_utc=bucket_start,
                bucket_end_utc=bucket_start + timedelta(minutes=5),
            )
            self.assertEqual(result["stations"], 0)
            row = fetch_one("SELECT COUNT(*) AS total FROM band_condition_station_hours")
            self.assertEqual(int((row or {"total": -1})["total"]), 0)

    def test_monitored_interface_collects_one_hourly_station_mask_with_distance(self) -> None:
        with temporary_database():
            interface_id = insert_interface(band="2m")
            execute(
                "UPDATE station_settings SET latitude = '52.2297', longitude = '21.0122' WHERE id = 1"
            )
            bucket_start = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
            execute(
                """
                INSERT INTO traffic_frames(
                    source, source_kind, interface_id, direction, band, format, line,
                    port, command, length, hex, created_at
                )
                VALUES ('RF-2m', 'rf', ?, 'RX', '2m', 'TNC2', ?, '', '', 40, '', ?)
                """,
                (
                    interface_id,
                    "SP5ABC>APRS:!5223.45N/02101.23E>Test",
                    (bucket_start + timedelta(minutes=1)).isoformat(),
                ),
            )
            result = aggregate_band_condition_bucket(
                bucket_start_utc=bucket_start,
                bucket_end_utc=bucket_start + timedelta(minutes=5),
            )
            self.assertEqual(result["stations"], 1)
            row = fetch_one(
                """
                SELECT band, station_key, segment_mask, fixed_hint, mobile_hint, distance_km
                FROM band_condition_station_hours
                WHERE interface_id = ?
                """,
                (interface_id,),
            )
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["band"], "2m")
            self.assertEqual(row["station_key"], "SP5ABC")
            self.assertEqual(int(row["segment_mask"]), 1)
            self.assertEqual(int(row["fixed_hint"]), 1)
            self.assertEqual(int(row["mobile_hint"]), 0)
            self.assertIsNotNone(row["distance_km"])

    def test_hourly_history_exposes_a_full_365_day_timeline(self) -> None:
        with temporary_database():
            interface_id = insert_interface(band="70cm")
            current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            saved_hour = current_hour - timedelta(hours=1)
            execute(
                """
                INSERT INTO band_condition_hourly(
                    hour_start_utc, interface_id, interface_name, band,
                    condition_index, confidence_score, history_hours, created_at
                )
                VALUES (?, ?, 'RF-70cm', '70cm', 4, 0.75, 168, ?)
                """,
                (saved_hour.isoformat(), interface_id, saved_hour.isoformat()),
            )
            history = get_band_condition_history(days=365)
            self.assertEqual(history["resolution_minutes"], 60)
            self.assertEqual(len(history["labels"]), 365 * 24)
            self.assertEqual(len(history["items"]), 1)
            self.assertEqual(len(history["items"][0]["indexes"]), 365 * 24)
            self.assertEqual(history["items"][0]["indexes"][-1], 4)
            self.assertEqual(history["items"][0]["confidence"][-1], 75)

    def test_template_is_simple_and_has_no_manual_reference_station_form(self) -> None:
        template = Path("app/templates/band_condition.html").read_text(encoding="utf-8")
        self.assertIn("band-condition-index", template)
        self.assertIn("band-condition-model-data", template)
        self.assertIn("30-day baseline", template)
        self.assertIn("/api/band-condition/history?days=365", template)
        self.assertNotIn("reference-stations", template)


if __name__ == "__main__":
    unittest.main()
