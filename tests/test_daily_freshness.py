"""Daily market-history session freshness tests with a real exchange calendar."""
import unittest
from datetime import datetime, timezone
import pandas as pd
from tradepilot.daily_freshness import assess_daily_history


class DailyFreshnessTests(unittest.TestCase):
    def test_last_completed_us_session_fresh(self):
        history = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2026-10-07"]))
        result = assess_daily_history(
            history, market="US", as_of_utc=datetime(2026, 10, 8, 3, tzinfo=timezone.utc)
        )
        self.assertEqual(result["status"], "FRESH")
        self.assertEqual(result["expected_completed_session"], "2026-10-07")

    def test_older_history_stale(self):
        history = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2026-10-05"]))
        result = assess_daily_history(
            history, market="US", as_of_utc=datetime(2026, 10, 8, 3, tzinfo=timezone.utc)
        )
        self.assertEqual(result["status"], "STALE")

    def test_current_unfinished_session_not_fresh(self):
        history = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2026-10-08"]))
        result = assess_daily_history(
            history, market="US", as_of_utc=datetime(2026, 10, 8, 15, tzinfo=timezone.utc)
        )
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["reason"], "HISTORY_DATE_AFTER_LAST_COMPLETED_SESSION")

    def test_missing_history_unknown(self):
        result = assess_daily_history(
            None, market="MX", as_of_utc=datetime(2026, 10, 8, 3, tzinfo=timezone.utc)
        )
        self.assertEqual(result["status"], "UNKNOWN")

    def test_reject_naive_clock(self):
        history = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2026-10-07"]))
        with self.assertRaises(ValueError):
            assess_daily_history(history, market="US", as_of_utc=datetime(2026, 10, 8, 3))


if __name__ == "__main__":
    unittest.main()
