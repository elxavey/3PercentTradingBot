"""Deterministic tests for Phase 3.5; no network or database."""
import unittest

import pandas as pd

from tradepilot.opportunity_monitor import classify_opportunity, opportunity_history


class OpportunityMonitorTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({
            "Open": [95.0] * 25, "High": [100.0] * 25,
            "Low": [90.0] * 25, "Close": [95.0] * 25,
            "Volume": [1000] * 25,
        }, index=pd.date_range("2026-09-01", periods=25))

    def test_monitoring(self):
        self.assertEqual(classify_opportunity(self.data)["state"], "MONITORING")

    def test_approaching(self):
        data = self.data.copy()
        data.iloc[-1, data.columns.get_loc("Close")] = 98.0
        self.assertEqual(classify_opportunity(data)["state"], "APPROACHING")

    def test_candidate_prior_resistance(self):
        data = self.data.copy()
        data.iloc[-1, data.columns.get_loc("Close")] = 101.0
        data.iloc[-1, data.columns.get_loc("High")] = 102.0
        self.assertEqual(classify_opportunity(data)["state"], "BREAKOUT_CANDIDATE")
        self.assertFalse(classify_opportunity(data)["actionable"])

    def test_exact_resistance_approaching_not_breakout(self):
        data = self.data.copy()
        data.iloc[-1, data.columns.get_loc("Close")] = 100.0
        self.assertEqual(classify_opportunity(data)["state"], "APPROACHING")

    def test_insufficient(self):
        self.assertEqual(classify_opportunity(self.data.iloc[:20])["state"],
                         "INSUFFICIENT_DATA")

    def test_bad_ohlcv_fails_closed(self):
        data = self.data.copy()
        data.iloc[-1, data.columns.get_loc("Low")] = 110.0
        self.assertEqual(classify_opportunity(data)["state"], "INSUFFICIENT_DATA")

    def test_rolling_history_no_lookahead(self):
        data = self.data.copy()
        data.iloc[-1, data.columns.get_loc("Close")] = 101.0
        data.iloc[-1, data.columns.get_loc("High")] = 102.0
        history = opportunity_history(data, max_sessions=4)
        self.assertEqual(len(history), 4)
        self.assertEqual(history[-1]["state"], "BREAKOUT_CANDIDATE")
        self.assertEqual(history[-2]["state"], "MONITORING")

    def test_reject_bad_threshold(self):
        with self.assertRaises(ValueError):
            classify_opportunity(self.data, near_pct=float("nan"))

    def test_reject_bad_history_limit(self):
        with self.assertRaises(ValueError):
            opportunity_history(self.data, max_sessions=0)


if __name__ == "__main__":
    unittest.main()
