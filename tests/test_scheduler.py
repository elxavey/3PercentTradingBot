"""Phase 1.6 calendar and scheduler tests; no Yahoo or broker calls."""
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch

from tradepilot.scheduler import MARKETS, calendar_slot, due_slot, tick

UTC = timezone.utc


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SchedulerTests(unittest.TestCase):
    def test_both_exchanges_open(self):
        slot = calendar_slot(date(2026, 10, 8))
        self.assertEqual(slot.markets, ("XNYS", "XMEX"))
        self.assertEqual(slot.scheduled_for_utc, utc("2026-10-08T14:45:00Z"))

    def test_us_holiday_blocks_combined_scan(self):
        # US Thanksgiving; Mexico trades, but combined scan is disallowed.
        self.assertIsNone(calendar_slot(date(2026, 11, 26)))

    def test_mexico_holiday_blocks_combined_scan(self):
        # Mexican Independence Day; US trades.
        self.assertIsNone(calendar_slot(date(2026, 9, 16)))

    def test_weekend_blocks_scan(self):
        self.assertIsNone(calendar_slot(date(2026, 10, 10)))

    def test_new_york_dst_transition(self):
        import exchange_calendars as xc
        ny = xc.get_calendar("XNYS")
        self.assertEqual(ny.session_open("2026-03-06").hour, 14)
        self.assertEqual(ny.session_open("2026-03-09").hour, 13)
        self.assertIsNotNone(calendar_slot(date(2026, 3, 9)))

    def test_session_window_boundaries(self):
        slot = calendar_slot(date(2026, 10, 8))
        self.assertIsNone(due_slot(slot.scheduled_for_utc - timedelta(seconds=1)))
        self.assertIsNotNone(due_slot(slot.scheduled_for_utc))
        self.assertIsNotNone(due_slot(slot.latest_start_utc - timedelta(seconds=1)))
        self.assertIsNone(due_slot(slot.latest_start_utc))

    def test_stale_previous_day_not_replayed(self):
        self.assertIsNone(due_slot(utc("2026-10-09T00:00:00Z")))

    def test_reject_naive_clock_and_invalid_delays(self):
        with self.assertRaises(ValueError):
            due_slot(datetime(2026, 10, 8, 14, 45))
        with self.assertRaises(ValueError):
            calendar_slot(date(2026, 10, 8), delay_minutes=-1)
        with self.assertRaises(ValueError):
            calendar_slot(date(2026, 10, 8), max_lateness_minutes=-1)

    def test_tick_dispatches_stable_utc_slot(self):
        worker = Mock(return_value=(0, "job"))
        code = tick(now=utc("2026-10-08T14:50:00Z"), worker=worker)
        self.assertEqual(code, 0)
        self.assertEqual(worker.call_args.kwargs["scheduled_for_utc"],
                         "2026-10-08T14:45:00.000Z")

    def test_tick_not_due_never_calls_worker(self):
        worker = Mock()
        self.assertEqual(tick(now=utc("2026-10-10T14:50:00Z"), worker=worker), 0)
        worker.assert_not_called()

    def test_dry_run_never_calls_worker(self):
        worker = Mock()
        self.assertEqual(tick(now=utc("2026-10-08T14:50:00Z"),
                              worker=worker, dry_run=True), 0)
        worker.assert_not_called()

    def test_worker_failure_propagates(self):
        worker = Mock(return_value=(1, "failed"))
        self.assertEqual(tick(now=utc("2026-10-08T14:50:00Z"), worker=worker), 1)

    def test_worker_duplicate_propagates(self):
        worker = Mock(return_value=(2, None))
        self.assertEqual(tick(now=utc("2026-10-08T14:50:00Z"), worker=worker), 2)

    def test_timezone_aware_local_input(self):
        offset = timezone(timedelta(hours=-4))
        local = utc("2026-10-08T14:50:00Z").astimezone(offset)
        self.assertIsNotNone(due_slot(local))

    def test_reject_short_session_without_enough_window(self):
        slot = calendar_slot(date(2026, 10, 8), delay_minutes=10000)
        self.assertIsNone(slot)


if __name__ == "__main__":
    unittest.main()
