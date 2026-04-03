import unittest
from pathlib import Path

from app.services.band_condition import (
    _condition_score,
    _dx_station_score,
    _occupancy_score,
    _select_activity_baseline,
    _select_reference_baseline,
    build_station_key,
    format_band_label,
)
from app.services.content import parse_tnc2_frame


class BandConditionHelpersTests(unittest.TestCase):
    def test_reference_station_rows_use_canonical_band_condition_edit_url(self) -> None:
        template = Path("/Users/rysiek/Documents/GitHub/APRSBox/app/templates/band_condition.html").read_text(encoding="utf-8")
        self.assertIn('data-href="{{ request.scope.root_path }}/band-condition?edit_reference={{ row.id }}"', template)

    def test_parse_tnc2_frame_accepts_spacing_from_kiss_decoder(self) -> None:
        parsed = parse_tnc2_frame("SRCCALL-9 > APRS , WIDE1-1,WIDE2-1 :!5218.37N/02104.87E-Test")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["source_key"], "SRCCALL-9")
        self.assertEqual(parsed["destination"], "APRS")
        self.assertEqual(parsed["classification"], "fixed")

    def test_build_station_key_normalizes_callsign_and_ssid(self) -> None:
        self.assertEqual(build_station_key("sq9mdd", "9"), "SQ9MDD-9")
        self.assertEqual(build_station_key("sq9mdd", "abc"), "SQ9MDD")

    def test_format_band_label_preserves_common_aprs_band_names(self) -> None:
        self.assertEqual(format_band_label("2m"), "2m")
        self.assertEqual(format_band_label("70cm"), "70cm")
        self.assertEqual(format_band_label("hf"), "HF")

    def test_dx_station_score_rewards_new_or_rare_fixed_stations(self) -> None:
        self.assertEqual(_dx_station_score(0.0, 0), 1.0)
        self.assertGreater(_dx_station_score(0.05, 3), 0.6)
        self.assertEqual(_dx_station_score(0.4, 20), 0.0)

    def test_occupancy_score_rises_when_activity_is_high_and_references_drop(self) -> None:
        score = _occupancy_score(
            current_total_activity=20.0,
            baseline_total_activity=8.0,
            current_mobile_activity=10.0,
            baseline_mobile_activity=3.0,
            local_reference_score=-0.4,
        )
        self.assertGreater(score, 0.6)

    def test_condition_score_prefers_dx_opening_over_occupancy_penalty(self) -> None:
        dx_condition = _condition_score(dx_opening_score=0.8, local_reference_score=0.1, occupancy_score=0.5)
        crowded_no_dx = _condition_score(dx_opening_score=0.0, local_reference_score=-0.2, occupancy_score=0.5)
        self.assertGreater(dx_condition, 0.25)
        self.assertLess(crowded_no_dx, 0.0)

    def test_reference_baseline_falls_back_to_all_hours_when_current_hour_is_sparse(self) -> None:
        baseline = _select_reference_baseline(
            baseline_by_station_hour={("SQ5AAG-2", 12): {"sample_count": 11, "heard_ratio": 0.5, "ema_heard_ratio": 0.45}},
            baseline_rows_by_station={
                "SQ5AAG-2": [
                    {"hour_of_day": 12, "sample_count": 11, "heard_ratio": 0.5, "ema_heard_ratio": 0.45},
                    {"hour_of_day": 13, "sample_count": 14, "heard_ratio": 0.6, "ema_heard_ratio": 0.55},
                ]
            },
            station_key="SQ5AAG-2",
            baseline_hour=12,
        )
        assert baseline is not None
        self.assertEqual(baseline["sample_count"], 25)
        self.assertGreater(baseline["heard_ratio"], 0.5)

    def test_activity_baseline_falls_back_to_all_hours_when_current_hour_is_sparse(self) -> None:
        baseline = _select_activity_baseline(
            [
                {"hour_of_day": 12, "sample_count": 11, "avg_mobile_frames": 2.0, "avg_total_frames": 5.0},
                {"hour_of_day": 13, "sample_count": 20, "avg_mobile_frames": 3.0, "avg_total_frames": 7.0},
            ],
            current_hour_activity_baseline={"hour_of_day": 12, "sample_count": 11, "avg_mobile_frames": 2.0, "avg_total_frames": 5.0},
        )
        assert baseline is not None
        self.assertEqual(baseline["sample_count"], 31)
        self.assertGreater(baseline["avg_total_frames"], 6.0)


if __name__ == "__main__":
    unittest.main()
