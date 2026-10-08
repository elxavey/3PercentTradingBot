import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import pandas as pd
from tradepilot.backtest_validation import validate_history, validated_backtest
from tradepilot.historical_simulator import SimulationPolicy

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)

class FakeCalendar:
    def sessions_in_range(self, start, end):
        return pd.bdate_range(start, end)
    def is_session(self, date):
        return pd.Timestamp(date).weekday() < 5
    def session_close(self, session):
        return pd.Timestamp(session).tz_localize("UTC") + pd.Timedelta(hours=16)

def sample(n=110):
    idx = pd.bdate_range("2026-01-05", periods=n)
    return pd.DataFrame({"Open":[100.]*n, "High":[101.]*n,
                         "Low":[99.]*n, "Close":[100.]*n,
                         "Volume":[1000.]*n}, index=idx)

class BacktestValidationTests(unittest.TestCase):
    def test_valid_complete_history(self):
        result = validate_history(sample(), market="US", as_of_utc=NOW,
                                  calendar=FakeCalendar())
        self.assertEqual(result["state"],"VALIDATED")
        self.assertEqual(result["completed_sessions"],110)

    def test_missing_exchange_session_rejected(self):
        h = sample().drop(sample().index[45])
        result = validate_history(h, market="US", as_of_utc=NOW,
                                  calendar=FakeCalendar())
        self.assertEqual(result["state"],"REJECT")
        self.assertIn("MISSING_EXCHANGE_SESSIONS",result["reasons"])

    def test_invalid_old_bar_rejected(self):
        h = sample()
        h.iloc[4,h.columns.get_loc("High")] = 1
        result = validate_history(h, market="US", as_of_utc=NOW,
                                  calendar=FakeCalendar())
        self.assertEqual(result["state"],"REJECT")

    def test_short_history_rejected(self):
        result = validate_history(sample(50), market="US", as_of_utc=NOW,
                                  calendar=FakeCalendar())
        self.assertIn("INSUFFICIENT_HISTORY",result["reasons"])

    def test_explicit_costs_required(self):
        with self.assertRaises(ValueError):
            validated_backtest(sample(),symbol="TEST",market="US",
                               as_of_utc=NOW,calendar=FakeCalendar(),
                               simulation_policy=SimulationPolicy())

    def test_validated_runner_integrates(self):
        result = validated_backtest(
            sample(),symbol="TEST",market="US",as_of_utc=NOW,
            calendar=FakeCalendar(),
            simulation_policy=SimulationPolicy(fee_rate_per_side=.0025,
                                               slippage_rate_per_side=.001))
        self.assertEqual(result["state"],"RESEARCH_RESULT")
        self.assertEqual(result["backtest"]["metrics"]["closed_trades"],0)
        self.assertFalse(result["actionable"])

if __name__ == "__main__":
    unittest.main()
