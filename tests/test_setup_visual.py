"""Phase 3.4 visual helpers: deterministic and read-only."""
import unittest

import pandas as pd

from tradepilot.setup_visual import chart_candles, hypothetical_outcomes


class VisualSetupTests(unittest.TestCase):
    def setUp(self):
        self.bars = pd.DataFrame({
            "Open": [10.0] * 30, "High": [12.0] * 30,
            "Low": [9.0] * 30, "Close": [11.0] * 30,
        }, index=pd.date_range("2026-01-01", periods=30))

    def test_chart_uses_only_supplied_rows(self):
        result = chart_candles(self.bars, max_bars=20)
        self.assertEqual(len(result), 20)
        self.assertEqual(result.index[-1], self.bars.index[-1])

    def test_chart_does_not_mutate_history(self):
        before = self.bars.copy(deep=True)
        chart_candles(self.bars)
        pd.testing.assert_frame_equal(self.bars, before)

    def test_invalid_ohlc_is_rejected(self):
        bad = self.bars.copy()
        bad.loc[bad.index[-1], "High"] = 1.0
        self.assertTrue(chart_candles(bad).empty)

    def test_missing_history_empty(self):
        self.assertTrue(chart_candles(None).empty)

    def test_invalid_bar_limit(self):
        with self.assertRaises(ValueError):
            chart_candles(self.bars, max_bars=10)

    def test_hypothetical_outcomes(self):
        result = hypothetical_outcomes({
            "quantity_research_only": 10, "entry": 100, "stop": 95,
            "target": 110, "estimated_cash_required": 1000,
            "estimated_risk": 50, "net_target_return_pct_estimate": 10,
            "currency": "MXN", "net_reward_risk_estimate": 2,
        })
        self.assertEqual(result["target_gain"], 100)
        self.assertEqual(result["risk"], 50)

    def test_invalid_risk_data_unavailable(self):
        self.assertFalse(hypothetical_outcomes({"quantity_research_only": 0})["available"])


if __name__ == "__main__":
    unittest.main()
