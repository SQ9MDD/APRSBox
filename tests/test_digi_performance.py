import unittest

from app.services.digi_performance import DIGI_STALE_LIMIT_MS, MIN_RF_DIGI_HOT_PATH_SAMPLES, evaluate_digi_performance


def snapshot_for_p99(p99_ms: float, *, samples: int = MIN_RF_DIGI_HOT_PATH_SAMPLES) -> dict:
    return {
        "rf_digi_hot_path_ms": {"sample_count": samples, "p99_ms": p99_ms},
        "digiflow_queue": {"recent_queue_overflows": 0},
        "rf_tx_dispatcher": {
            "recent_stale_digi_tx_drops": 0,
            "recent_queue_overflows": 0,
        },
    }


class DigiPerformanceTests(unittest.TestCase):
    def test_collects_until_enough_rf_digi_samples_exist(self) -> None:
        result = evaluate_digi_performance(snapshot_for_p99(100.0, samples=MIN_RF_DIGI_HOT_PATH_SAMPLES - 1))

        self.assertEqual(result["status"], "collecting")
        self.assertIsNone(result["score"])
        self.assertEqual(result["minimum_samples"], MIN_RF_DIGI_HOT_PATH_SAMPLES)

    def test_classifies_all_headroom_bands(self) -> None:
        cases = (
            (10.0, 5, "Excellent"),
            (5.0, 4, "Good"),
            (2.0, 3, "Fair"),
            (1.0, 2, "Marginal"),
            (0.99, 1, "Insufficient"),
        )

        for headroom, expected_score, expected_label in cases:
            with self.subTest(headroom=headroom):
                result = evaluate_digi_performance(snapshot_for_p99(DIGI_STALE_LIMIT_MS / headroom))
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["score"], expected_score)
                self.assertEqual(result["label"], expected_label)

    def test_recent_hot_path_drop_forces_insufficient_score(self) -> None:
        snapshot = snapshot_for_p99(100.0)
        snapshot["rf_tx_dispatcher"]["recent_stale_digi_tx_drops"] = 1

        result = evaluate_digi_performance(snapshot)

        self.assertEqual(result["score"], 1)
        self.assertTrue(result["forced_insufficient"])


if __name__ == "__main__":
    unittest.main()
