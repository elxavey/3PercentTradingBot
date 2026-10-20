"""Calendar-gated post-close V6 runner regression tests."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from tradepilot.v6_postclose_scheduler_cli import postclose_slot, tick

UTC = timezone.utc


class FakeCalendar:
    def __init__(self, close, active=True):
        self.close = close
        self.active = active

    def is_session(self, day):
        return self.active

    def session_close(self, day):
        import pandas as pd
        return pd.Timestamp(self.close)


class PostcloseSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.day = datetime(2026, 10, 20, tzinfo=UTC)
        self.calendars = {
            "XNYS": FakeCalendar(self.day + timedelta(hours=20)),
            "XMEX": FakeCalendar(self.day + timedelta(hours=21)),
        }

    def test_preclose_not_due(self):
        self.assertIsNone(postclose_slot(self.day + timedelta(hours=20), calendars=self.calendars))

    def test_later_exchange_close_controls_slot(self):
        now = self.day + timedelta(hours=21, minutes=30)
        self.assertEqual(postclose_slot(now, calendars=self.calendars),
                         self.day + timedelta(hours=21, minutes=20))

    def test_holiday_abstains(self):
        self.calendars["XMEX"].active = False
        self.assertIsNone(postclose_slot(self.day + timedelta(hours=22), calendars=self.calendars))

    def test_expired_slot_not_replayed(self):
        self.assertIsNone(postclose_slot(self.day + timedelta(hours=23, minutes=30),
                                         calendars=self.calendars))

    def test_not_due_never_scans(self):
        def forbidden(**kwargs):
            raise AssertionError("Worker must not run before close")
        result = tick(now=self.day, calendars=self.calendars, worker=forbidden)
        self.assertEqual(result["status"], "NOT_DUE")

    @patch("tradepilot.v6_postclose_scheduler_cli.save", return_value=("x.json", "x.csv"))
    def test_due_dynamic_worker_then_pipeline(self, saved):
        calls = []
        def worker(**kwargs):
            calls.append(("scan", kwargs["universe_name"]))
            return 0, "job-123"
        def pipeline(*args, **kwargs):
            calls.append(("pipeline", args[1]))
            return {"status": "ABSTAIN", "candidates": [], "orders_sent": 0}
        result = tick(now=self.day + timedelta(hours=21, minutes=30),
                      calendars=self.calendars, worker=worker, pipeline=pipeline)
        self.assertEqual(calls, [("scan", "Dynamic MX + USA - 250 symbols"),
                                 ("pipeline", "2026-10-20")])
        self.assertEqual(result["orders_sent"], 0)
        saved.assert_called_once()

    def test_static_universe_disallowed(self):
        with self.assertRaises(ValueError):
            tick(now=self.day, universe="Test - 12 symbols", calendars=self.calendars)


if __name__ == "__main__":
    unittest.main()
