"""Phase 3.3 adapter tests; no network or Streamlit required."""
import unittest
from datetime import datetime, timezone

import pandas as pd

from tradepilot.setup_view import analyze_watchlist_symbol, completed_history
from tradepilot.trade_setup import RiskPolicy


class SetupViewTests(unittest.TestCase):
    def setUp(self):
        import exchange_calendars as xcals
        self.calendar = xcals.get_calendar("XNYS")
        self.now = datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)
        sessions = self.calendar.sessions_in_range("2026-08-01", "2026-10-08")
        self.dates = [x.date() for x in sessions][-26:]
        self.history = pd.DataFrame({
            "Open": [100.0] * len(self.dates),
            "High": [102.0] * len(self.dates),
            "Low": [98.0] * len(self.dates),
            "Close": [101.0] * len(self.dates),
            "Volume": [1000.0] * len(self.dates),
        }, index=pd.DatetimeIndex(self.dates))

    def test_excludes_unfinished_current_session(self):
        bars, evidence = completed_history(
            self.history, market="US", as_of_utc=self.now, calendar=self.calendar)
        self.assertEqual(bars.index[-1].date().isoformat(), "2026-10-07")
        self.assertEqual(evidence, "LATEST_COMPLETED_SESSION")

    def test_research_never_actionable(self):
        result = analyze_watchlist_symbol(
            symbol="AAPL", market="US", policy=RiskPolicy(),
            as_of_utc=self.now, fetcher=lambda _: self.history,
            calendar=self.calendar)
        self.assertEqual(result["state"], "WAIT")
        self.assertFalse(result["actionable"])
        self.assertEqual(result["last_completed_bar"][:10], "2026-10-07")

    def test_missing_history_wait(self):
        result = analyze_watchlist_symbol(
            symbol="AAPL", market="US", policy=RiskPolicy(),
            as_of_utc=self.now, fetcher=lambda _: None, calendar=self.calendar)
        self.assertEqual(result["state"], "WAIT")
        self.assertFalse(result["actionable"])

    def test_reject_naive_time(self):
        with self.assertRaises(ValueError):
            completed_history(self.history, market="US",
                              as_of_utc=datetime(2026, 10, 8), calendar=self.calendar)

    def test_reject_duplicate_index(self):
        invalid = self.history.copy()
        invalid.index = pd.DatetimeIndex([self.dates[0]] * len(invalid))
        bars, reason = completed_history(
            invalid, market="US", as_of_utc=self.now, calendar=self.calendar)
        self.assertIsNone(bars)
        self.assertEqual(reason, "INVALID_HISTORY_INDEX")


if __name__ == "__main__":
    unittest.main()
