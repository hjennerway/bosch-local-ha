"""Run with python -m unittest discover -s tests."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "schedule", Path(__file__).parents[1] / "custom_components/bosch_local/schedule.py"
)
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)


class ScheduleValidationTests(unittest.TestCase):
    def test_future_is_normalized_to_utc(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        value = datetime(2026, 10, 24, 1, tzinfo=timezone(timedelta(hours=1)))
        self.assertEqual(schedule.validate_start(value, now).hour, 0)

    def test_naive_and_elapsed_times_are_rejected(self):
        now = datetime.now(timezone.utc)
        for value in (datetime.now(), now, now - timedelta(seconds=1)):
            with self.assertRaises(ValueError):
                schedule.validate_start(value, now)

    def test_only_configured_positive_ids_can_be_started(self):
        self.assertEqual(schedule.program_payload("Nightwash", {"Nightwash": 123}),
                         [{"program": 123}])
        for uid in (0, -1, True, "123", None):
            with self.assertRaises(ValueError):
                schedule.program_payload("Nightwash", {"Nightwash": uid})
        with self.assertRaises(ValueError):
            schedule.program_payload("Unknown", {"Nightwash": 123})


if __name__ == "__main__":
    unittest.main()
