import unittest
from datetime import datetime, timezone
import pandas as pd
from tradepilot.exploratory_backtest import exploratory_backtest
from tradepilot.historical_simulator import SimulationPolicy

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
POLICY = SimulationPolicy(fee_rate_per_side=.0025, slippage_rate_per_side=.001)

class FakeCalendar:
    def sessions_in_range(self, start, end):
        return pd.bdate_range(start, end)
    def is_session(self, date):
        return pd.Timestamp(date).weekday() < 5
    def session_close(self, session):
        return pd.Timestamp(session).tz_localize("UTC") + pd.Timedelta(hours=16)

def sample(n=260):
    idx = pd.bdate_range("2025-06-02", periods=n)
    return pd.DataFrame({"Open": [100.] * n, "High": [101.] * n,
                         "Low": [99.] * n, "Close": [100.] * n,
                         "Volume": [1000.] * n}, index=idx)

def run(h, **kw):
    return exploratory_backtest(h, symbol="TEST", market="US", as_of_utc=NOW,
                                simulation_policy=POLICY, calendar=FakeCalendar(), **kw)

class ExploratoryBacktestTests(unittest.TestCase):
    def test_complete_history(self):
        self.assertEqual(run(sample())["validation"]["state"], "VALIDATED")

    def test_one_missing_day(self):
        h = sample()
        result = run(h.drop(h.index[130]))
        self.assertEqual(result["state"], "RESEARCH_RESULT")
        self.assertEqual(result["validation"]["state"], "PARTIAL_HISTORY")
        self.assertEqual(result["validation"]["segments"], 2)
        self.assertEqual(result["validation"]["missing_sessions_count"], 1)

    def test_timezone_aware_yahoo_style_index(self):
        h = sample()
        h.index = h.index.tz_localize("America/Mexico_City")
        result = run(h.drop(h.index[130]))
        self.assertEqual(result["state"], "RESEARCH_RESULT")
        self.assertEqual(result["validation"]["state"], "PARTIAL_HISTORY")
        self.assertEqual(result["validation"]["segments"], 2)

    def test_two_isolated_missing_days(self):
        h = sample()
        result = run(h.drop(h.index[[70, 200]]))
        self.assertEqual(result["validation"]["state"], "PARTIAL_HISTORY")
        self.assertEqual(result["validation"]["segments"], 3)

    def test_consecutive_missing_days_rejected(self):
        h = sample()
        result = run(h.drop(h.index[[130, 131]]))
        self.assertEqual(result["state"], "REJECT")
        self.assertIn("CONSECUTIVE_MISSING_SESSIONS", result["reasons"])

    def test_three_missing_days_rejected(self):
        h = sample()
        result = run(h.drop(h.index[[30, 90, 150]]))
        self.assertEqual(result["state"], "REJECT")
        self.assertIn("TOO_MANY_MISSING_SESSIONS", result["reasons"])

    def test_invalid_bar_rejected_even_with_gap(self):
        h = sample()
        h.iloc[20, h.columns.get_loc("High")] = 1
        result = run(h.drop(h.index[130]))
        self.assertEqual(result["state"], "REJECT")

    def test_missing_day_never_bridged(self):
        h = sample()
        result = run(h.drop(h.index[130]))
        self.assertEqual(result["backtest"]["metrics"]["closed_trades"], 0)
        self.assertFalse(result["actionable"])

    def test_reject_more_than_two_allowed(self):
        with self.assertRaises(ValueError):
            run(sample(), max_missing=3)

if __name__ == "__main__":
    unittest.main()
