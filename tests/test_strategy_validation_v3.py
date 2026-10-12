"""Offline tests for v3 forward-entry integrity and descriptive holdout."""
import unittest
import pandas as pd
from tradepilot.breakout_trade_plan import build_trade_plan
from tradepilot.strategy_validation_cli import run_backtest, simulate
from tradepilot.bmv_crosscheck_cli import review_candidates


class StrategyV3Tests(unittest.TestCase):
    def test_forward_entry_above_completed_close(self):
        row = {"reference_close": 105, "breakout_trigger": 100, "structural_stop_reference": 98}
        plan = build_trade_plan(row, forward_entry_floor_pct=0.1)
        self.assertEqual(plan["technical_trigger_reference"], 100)
        self.assertGreater(plan["entry_reference"], 105)
        self.assertTrue(plan["entry_above_completed_close"])

    def test_trigger_above_close_is_preserved(self):
        row = {"reference_close": 100, "breakout_trigger": 103, "structural_stop_reference": 95}
        plan = build_trade_plan(row, forward_entry_floor_pct=0.1)
        self.assertEqual(plan["entry_reference"], 103)

    def test_invalid_floor_is_rejected(self):
        row = {"reference_close": 100, "breakout_trigger": 103, "structural_stop_reference": 95}
        self.assertEqual(build_trade_plan(row, forward_entry_floor_pct=-1)["plan_state"], "UNAVAILABLE")

    def test_descriptive_split_with_no_signals(self):
        dates = pd.bdate_range("2026-01-01", periods=120)
        data = pd.DataFrame({"Open": [100.0]*120, "High": [101.0]*120,
                             "Low": [99.0]*120, "Close": [100.0]*120,
                             "Volume": [1000000]*120}, index=dates)
        result = run_backtest(["PG"], lookback=40, holding=5, stride=10,
                              fetcher=lambda symbol, period: data)
        self.assertIn("chronological_split", result)
        self.assertIn("signal_events", result)
        self.assertIn("NOT_TRUE_OUT_OF_SAMPLE", result["chronological_split"]["warning"])

    def test_bmv_never_auto_verifies(self):
        rows = [{"symbol": "TEST.MX", "quote_type": "EQUITY",
                 "mapping_status": "SERIES_AND_ISSUER_REVIEW", "history_status": "ENOUGH_BARS"}]
        result = review_candidates(rows, {"results": []})
        self.assertFalse(result["mapping_verified"])
        self.assertIn("NOT_IN_RADAR", result["candidates"][0]["research_observations"])

    def test_simulation_no_trigger(self):
        data = pd.DataFrame([{"Open": 99, "High": 99.5, "Low": 98, "Close": 99}])
        self.assertEqual(simulate(data, 100, 95)["outcome"], "NOT_TRIGGERED")


if __name__ == "__main__":
    unittest.main()
