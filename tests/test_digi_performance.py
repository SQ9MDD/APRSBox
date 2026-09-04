import unittest

from app.services.digi_performance import MIN_EVENT_LOOP_LAG_SAMPLES, evaluate_digi_performance


def snapshot_for_p95(p95_ms: float, *, samples: int = MIN_EVENT_LOOP_LAG_SAMPLES) -> dict:
    return {
        "event_loop_lag_ms": {"sample_count": samples, "p95_ms": p95_ms},
        "digiflow_queue": {"current_depth": 0, "capacity": 256, "recent_queue_overflows": 0},
        "rf_tx_dispatcher": {
            "current_queue_depth": 0,
            "queue_capacity": 128,
            "recent_stale_digi_tx_drops": 0,
            "recent_queue_overflows": 0,
        },
        "aprsis_tx_dispatcher": {"current_queue_depth": 0, "queue_capacity": 256},
        "rx_side_effect_dispatcher": {"current_queue_depth": 0, "queue_capacity": 256},
    }


class DigiPerformanceTests(unittest.TestCase):
    def test_warms_only_until_the_continuous_event_loop_probe_has_samples(self) -> None:
        result = evaluate_digi_performance(snapshot_for_p95(10.0, samples=MIN_EVENT_LOOP_LAG_SAMPLES - 1))

        self.assertEqual(result["status"], "warming")
        self.assertIsNone(result["score"])
        self.assertEqual(result["minimum_samples"], MIN_EVENT_LOOP_LAG_SAMPLES)

    def test_missing_loop_measurement_never_becomes_a_false_excellent_score(self) -> None:
        snapshot = snapshot_for_p95(10.0)
        snapshot["event_loop_lag_ms"].pop("p95_ms")

        result = evaluate_digi_performance(snapshot)

        self.assertEqual(result["status"], "warming")

    def test_classifies_event_loop_responsiveness_bands(self) -> None:
        cases = (
            (20.0, 5, "Excellent"),
            (46.0, 4, "Good"),
            (75.0, 4, "Good"),
            (132.0, 3, "Sufficient"),
            (191.2, 3, "Sufficient"),
            (500.0, 2, "Marginal"),
            (500.1, 1, "Insufficient"),
        )

        for p95_ms, expected_score, expected_label in cases:
            with self.subTest(p95_ms=p95_ms):
                result = evaluate_digi_performance(snapshot_for_p95(p95_ms))
                self.assertEqual(result["status"], "ready")
                self.assertEqual(result["score"], expected_score)
                self.assertEqual(result["label"], expected_label)

    def test_recent_digi_drop_forces_insufficient_score(self) -> None:
        snapshot = snapshot_for_p95(1.0)
        snapshot["rf_tx_dispatcher"]["recent_stale_digi_tx_drops"] = 1

        result = evaluate_digi_performance(snapshot)

        self.assertEqual(result["score"], 1)

    def test_queue_pressure_reduces_an_otherwise_healthy_score(self) -> None:
        snapshot = snapshot_for_p95(1.0)
        snapshot["rx_side_effect_dispatcher"] = {"current_queue_depth": 180, "queue_capacity": 256}

        result = evaluate_digi_performance(snapshot)

        self.assertEqual(result["score"], 2)
        self.assertEqual(result["queue_name"], "RX side effects")

    def test_one_busy_rf_interface_is_not_hidden_by_other_idle_interfaces(self) -> None:
        snapshot = snapshot_for_p95(1.0)
        snapshot["rf_tx_dispatcher"] = {
            "current_queue_depth": 120,
            "queue_capacity": 384,
            "max_queue_utilisation": 120 / 128,
            "recent_stale_digi_tx_drops": 0,
            "recent_queue_overflows": 0,
        }

        result = evaluate_digi_performance(snapshot)

        self.assertEqual(result["score"], 1)
        self.assertEqual(result["queue_name"], "RF TX")

    def test_unavailable_core_is_reported_instead_of_collecting_forever(self) -> None:
        result = evaluate_digi_performance({"status": "unavailable"})

        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["score"])


if __name__ == "__main__":
    unittest.main()
