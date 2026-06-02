import unittest
from datetime import datetime, timezone

from app.services.activation_schedule import compute_activation_state, normalize_activation_schedule


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class ActivationScheduleTests(unittest.TestCase):
    def test_manual_active_true_without_valid_until(self) -> None:
        state = compute_activation_state({"is_enabled": 1}, utc("2026-06-02T12:00"))
        self.assertTrue(state.active_now)
        self.assertEqual(state.reason, "manual_active")

    def test_manual_active_false(self) -> None:
        state = compute_activation_state({"is_enabled": 0}, utc("2026-06-02T12:00"))
        self.assertFalse(state.active_now)
        self.assertEqual(state.reason, "disabled")

    def test_manual_valid_until_in_future(self) -> None:
        state = compute_activation_state(
            {"is_enabled": 1, "activation_mode": "manual", "valid_until_utc": "2026-06-02 13:00"},
            utc("2026-06-02T12:00"),
        )
        self.assertTrue(state.active_now)

    def test_manual_valid_until_in_past(self) -> None:
        state = compute_activation_state(
            {"is_enabled": 1, "activation_mode": "manual", "valid_until_utc": "2026-06-02 11:00"},
            utc("2026-06-02T12:00"),
        )
        self.assertFalse(state.active_now)
        self.assertEqual(state.reason, "manual_expired")

    def test_scheduled_before_start(self) -> None:
        state = compute_activation_state(self._scheduled_record(), utc("2026-06-09T17:59"))
        self.assertFalse(state.active_now)
        self.assertEqual(state.next_activation_utc, utc("2026-06-09T18:00"))

    def test_scheduled_during_window(self) -> None:
        state = compute_activation_state(self._scheduled_record(), utc("2026-06-09T19:00"))
        self.assertTrue(state.active_now)
        self.assertEqual(state.current_window_until_utc, utc("2026-06-09T21:00"))

    def test_scheduled_after_end(self) -> None:
        state = compute_activation_state(self._scheduled_record(), utc("2026-06-09T21:01"))
        self.assertFalse(state.active_now)
        self.assertEqual(state.reason, "scheduled_ended")

    def test_recurring_before_first_activation(self) -> None:
        state = compute_activation_state(self._weekly_record(), utc("2026-06-09T17:59"))
        self.assertFalse(state.active_now)
        self.assertEqual(state.next_activation_utc, utc("2026-06-09T18:00"))

    def test_recurring_during_first_window(self) -> None:
        state = compute_activation_state(self._weekly_record(), utc("2026-06-09T19:00"))
        self.assertTrue(state.active_now)
        self.assertEqual(state.current_window_until_utc, utc("2026-06-09T21:00"))

    def test_recurring_between_windows(self) -> None:
        state = compute_activation_state(self._weekly_record(), utc("2026-06-10T12:00"))
        self.assertFalse(state.active_now)
        self.assertEqual(state.next_activation_utc, utc("2026-06-16T18:00"))

    def test_recurring_during_later_window(self) -> None:
        state = compute_activation_state(self._weekly_record(), utc("2026-06-16T20:00"))
        self.assertTrue(state.active_now)
        self.assertEqual(state.current_window_until_utc, utc("2026-06-16T21:00"))

    def test_recurring_after_repeat_until(self) -> None:
        record = self._weekly_record()
        record["recurrence_until_utc"] = "2026-06-16 18:00"
        state = compute_activation_state(record, utc("2026-06-23T18:00"))
        self.assertFalse(state.active_now)
        self.assertEqual(state.reason, "recurring_ended")
        self.assertIsNone(state.next_activation_utc)

    def test_recurring_last_window_remains_active_after_repeat_until(self) -> None:
        record = self._weekly_record()
        record["recurrence_duration_minutes"] = 1500
        record["recurrence_interval_value"] = 1
        record["recurrence_interval_unit"] = "day"
        record["recurrence_until_utc"] = "2026-06-10 18:00"
        state = compute_activation_state(record, utc("2026-06-11T18:30"))
        self.assertTrue(state.active_now)
        self.assertEqual(state.reason, "recurring_active")
        self.assertEqual(state.current_window_until_utc, utc("2026-06-11T19:00"))

    def test_recurring_every_seven_days(self) -> None:
        record = self._weekly_record()
        record["recurrence_interval_value"] = 7
        record["recurrence_interval_unit"] = "day"
        state = compute_activation_state(record, utc("2026-06-16T19:00"))
        self.assertTrue(state.active_now)

    def test_monthly_recurring_from_month_end_uses_anchor_day(self) -> None:
        record = self._weekly_record()
        record["first_activation_utc"] = "2026-01-31 18:00"
        record["recurrence_interval_value"] = 1
        record["recurrence_interval_unit"] = "month"
        state = compute_activation_state(record, utc("2026-02-28T19:00"))
        self.assertTrue(state.active_now)
        self.assertEqual(state.next_activation_utc, utc("2026-03-31T18:00"))

    def test_invalid_duration_is_rejected(self) -> None:
        record = self._weekly_record()
        record["recurrence_duration_minutes"] = "0"
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            normalize_activation_schedule(record)

    def test_invalid_interval_value_is_rejected(self) -> None:
        record = self._weekly_record()
        record["recurrence_interval_value"] = "-1"
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            normalize_activation_schedule(record)

    def test_missing_activation_mode_is_treated_as_manual(self) -> None:
        state = compute_activation_state({"is_enabled": 1}, utc("2026-06-02T12:00"))
        self.assertTrue(state.active_now)
        self.assertEqual(state.reason, "manual_active")

    def test_scheduled_end_before_start_is_rejected(self) -> None:
        record = self._scheduled_record()
        record["active_until_utc"] = "2026-06-09 17:00"
        with self.assertRaisesRegex(ValueError, "cannot be earlier"):
            normalize_activation_schedule(record)

    def test_recurring_end_before_first_activation_is_rejected(self) -> None:
        record = self._weekly_record()
        record["recurrence_until_utc"] = "2026-06-09 17:00"
        with self.assertRaisesRegex(ValueError, "cannot be earlier"):
            normalize_activation_schedule(record)

    def _scheduled_record(self) -> dict[str, object]:
        return {
            "is_enabled": 1,
            "activation_mode": "scheduled",
            "active_from_utc": "2026-06-09 18:00",
            "active_until_utc": "2026-06-09 21:00",
        }

    def _weekly_record(self) -> dict[str, object]:
        return {
            "is_enabled": 1,
            "activation_mode": "recurring",
            "first_activation_utc": "2026-06-09 18:00",
            "recurrence_duration_minutes": 180,
            "recurrence_interval_value": 1,
            "recurrence_interval_unit": "week",
        }


if __name__ == "__main__":
    unittest.main()
