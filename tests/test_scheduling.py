import random
import unittest
from datetime import datetime

from backend.app.services.scheduling import (
    SendSettingsView,
    add_random_jitter,
    in_quiet_hours,
    lock_ttl_seconds,
    next_run_after_failure,
    next_run_after_success,
)


class SchedulingTestCase(unittest.TestCase):
    def test_default_settings_view(self) -> None:
        view = SendSettingsView.from_dict(None)
        self.assertEqual(view.success_interval_seconds, 60)
        self.assertEqual(view.failure_interval_seconds, 120)

    def test_view_reads_quiet_hours(self) -> None:
        view = SendSettingsView.from_dict({"quiet_hours_start": "22:00", "quiet_hours_end": "09:00"})
        self.assertEqual(view.quiet_hours_start, "22:00")
        self.assertEqual(view.quiet_hours_end, "09:00")

    def test_in_quiet_hours_same_day_window(self) -> None:
        now = datetime(2026, 5, 15, 12, 30)
        self.assertTrue(in_quiet_hours(now, "12:00", "13:00"))
        self.assertFalse(in_quiet_hours(now, "13:00", "14:00"))

    def test_in_quiet_hours_overnight_window(self) -> None:
        late = datetime(2026, 5, 15, 23, 0)
        early = datetime(2026, 5, 15, 7, 0)
        midday = datetime(2026, 5, 15, 12, 0)
        self.assertTrue(in_quiet_hours(late, "22:00", "09:00"))
        self.assertTrue(in_quiet_hours(early, "22:00", "09:00"))
        self.assertFalse(in_quiet_hours(midday, "22:00", "09:00"))

    def test_quiet_hours_invalid_returns_false(self) -> None:
        now = datetime(2026, 5, 15, 12, 0)
        self.assertFalse(in_quiet_hours(now, None, None))
        self.assertFalse(in_quiet_hours(now, "abc", "def"))

    def test_jitter_is_within_range(self) -> None:
        rng = random.Random(42)
        result = add_random_jitter(60, 5, 15, rng)
        self.assertGreaterEqual(result, 65)
        self.assertLessEqual(result, 75)

    def test_jitter_clamps_invalid_bounds(self) -> None:
        rng = random.Random(0)
        result = add_random_jitter(60, -5, -10, rng)
        self.assertEqual(result, 60)

    def test_next_run_after_success_uses_success_interval(self) -> None:
        now = datetime(2026, 5, 15, 0, 0)
        view = SendSettingsView(success_interval_seconds=30, random_min_seconds=0, random_max_seconds=0)
        nxt = next_run_after_success(now, view)
        self.assertEqual((nxt - now).total_seconds(), 30)

    def test_next_run_after_failure_uses_failure_interval(self) -> None:
        now = datetime(2026, 5, 15, 0, 0)
        view = SendSettingsView(failure_interval_seconds=240, random_min_seconds=0, random_max_seconds=0)
        nxt = next_run_after_failure(now, view)
        self.assertEqual((nxt - now).total_seconds(), 240)

    def test_lock_ttl_padding_added(self) -> None:
        view = SendSettingsView(success_interval_seconds=60, random_max_seconds=10)
        self.assertEqual(lock_ttl_seconds(view, padding=5), 75)


if __name__ == "__main__":
    unittest.main()
