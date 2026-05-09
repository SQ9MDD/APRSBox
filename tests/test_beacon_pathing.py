import unittest

from app.services.beacon_pathing import (
    BEACON_INTERVAL_MODE_FIXED,
    BEACON_INTERVAL_MODE_PROPORTIONAL,
    build_proportional_schedule_tooltip,
    classify_beacon_path,
    evaluate_beacon_health,
)


class BeaconPathingClassificationTests(unittest.TestCase):
    def test_empty_path_is_direct(self) -> None:
        result = classify_beacon_path("")
        self.assertEqual(result["hop_class"], 0)
        self.assertTrue(result["is_direct"])

    def test_wide2_1_is_one_hop(self) -> None:
        self.assertEqual(classify_beacon_path("WIDE2-1")["hop_class"], 1)

    def test_sp2_1_is_one_hop(self) -> None:
        self.assertEqual(classify_beacon_path("SP2-1")["hop_class"], 1)

    def test_wide2_2_is_two_hop(self) -> None:
        self.assertEqual(classify_beacon_path("WIDE2-2")["hop_class"], 2)

    def test_sp2_2_is_two_hop(self) -> None:
        self.assertEqual(classify_beacon_path("SP2-2")["hop_class"], 2)

    def test_wide1_1_wide2_1_is_at_least_two_hop(self) -> None:
        result = classify_beacon_path("WIDE1-1,WIDE2-1")
        self.assertIsInstance(result["hop_class"], int)
        self.assertGreaterEqual(int(result["hop_class"]), 2)


class BeaconPathingHealthTests(unittest.TestCase):
    def test_two_hop_and_30m_is_not_recommended(self) -> None:
        result = evaluate_beacon_health(
            beacon_interval_mode=BEACON_INTERVAL_MODE_FIXED,
            beacon_interval_minutes=30,
            beacon_path="WIDE2-2",
        )
        self.assertEqual(result["tone"], "not_recommended")

    def test_two_hop_and_60m_is_ok(self) -> None:
        result = evaluate_beacon_health(
            beacon_interval_mode=BEACON_INTERVAL_MODE_FIXED,
            beacon_interval_minutes=60,
            beacon_path="WIDE2-2",
        )
        self.assertEqual(result["tone"], "ok")

    def test_one_hop_and_15m_is_warning(self) -> None:
        result = evaluate_beacon_health(
            beacon_interval_mode=BEACON_INTERVAL_MODE_FIXED,
            beacon_interval_minutes=15,
            beacon_path="WIDE2-1",
        )
        self.assertEqual(result["tone"], "warning")

    def test_one_hop_and_30m_is_ok(self) -> None:
        result = evaluate_beacon_health(
            beacon_interval_mode=BEACON_INTERVAL_MODE_FIXED,
            beacon_interval_minutes=30,
            beacon_path="WIDE2-1",
        )
        self.assertEqual(result["tone"], "ok")

    def test_proportional_is_always_ok(self) -> None:
        result = evaluate_beacon_health(
            beacon_interval_mode=BEACON_INTERVAL_MODE_PROPORTIONAL,
            beacon_interval_minutes=15,
            beacon_path="WIDE2-2",
        )
        self.assertEqual(result["tone"], "ok")
        self.assertTrue(result["is_recommended"])


class BeaconPathingTooltipTests(unittest.TestCase):
    def test_tooltip_for_wide2_2_contains_expected_paths(self) -> None:
        tooltip = build_proportional_schedule_tooltip("WIDE2-2")
        self.assertIn("DIRECT", tooltip)
        self.assertIn("WIDE1-1", tooltip)
        self.assertIn("WIDE2-2", tooltip)

    def test_tooltip_for_wide2_1_contains_expected_paths(self) -> None:
        tooltip = build_proportional_schedule_tooltip("WIDE2-1")
        self.assertIn("DIRECT", tooltip)
        self.assertIn("WIDE2-1", tooltip)


if __name__ == "__main__":
    unittest.main()
