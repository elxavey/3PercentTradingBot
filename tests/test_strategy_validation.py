"""Offline deterministic validation of backtest execution assumptions."""
import unittest
import pandas as pd
from tradepilot.strategy_validation_cli import simulate
from tradepilot.universe_quality_cli import audit
from tradepilot.strategy_batch_cli import select_symbols
from tradepilot.strategy_validation_cli import run_backtest


def bars(items):
    return pd.DataFrame(items, columns=["Open","High","Low","Close"])


class StrategyValidationTests(unittest.TestCase):
    def test_no_trigger(self):
        self.assertEqual(simulate(bars([(98,99,97,98)]), 100,95)["outcome"],"NOT_TRIGGERED")

    def test_gap_entry_not_trigger_fill(self):
        result = simulate(bars([(105,107,104,106)]),100,90)
        self.assertEqual(result["outcome"],"TIMEOUT")
        self.assertGreater(result["entry"],105)

    def test_stop_first_on_ambiguous_entry_bar(self):
        result = simulate(bars([(99,110,90,105)]),100,95)
        self.assertEqual(result["outcome"],"STOP")
        self.assertTrue(result["ambiguous_entry_bar"])

    def test_target(self):
        result = simulate(bars([(101,108,100,107)]),100,95)
        self.assertEqual(result["outcome"],"TARGET")
        self.assertAlmostEqual(result["net_pct"],3,delta=0.01)

    def test_invalid_stop(self):
        self.assertEqual(simulate(bars([(100,110,90,100)]),100,101)["outcome"],"INVALID_PLAN")

    def test_empty_future(self):
        self.assertEqual(simulate(bars([]), 100, 95)["outcome"], "NO_FUTURE_BARS")

    def test_batch_market_limits(self):
        report = {"results": [
            {"symbol": "ALSEA.MX", "state": "APPROACHING", "quality_score": 60},
            {"symbol": "WALMEX.MX", "state": "MONITORING", "quality_score": 80},
            {"symbol": "PG", "state": "CONFIRMED_RESEARCH", "quality_score": 90},
            {"symbol": "UTZ", "state": "REJECT", "reason": "LOW_OR_INVALID_TURNOVER"}]}
        result = select_symbols(report, mx_limit=1, us_limit=2)
        self.assertEqual(result["symbols"], ["ALSEA.MX", "PG"])
        self.assertEqual(result["coverage"]["US"]["eligible"], 1)

    def test_backtest_reject_diagnostics(self):
        dates = pd.bdate_range("2026-01-01", periods=120)
        df = pd.DataFrame({"Open": [100.0]*120, "High": [101.0]*120,
                           "Low": [99.0]*120, "Close": [100.0]*120,
                           "Volume": [1000000]*120}, index=dates)
        result = run_backtest(["PG"], lookback=40, holding=5, stride=10,
                              fetcher=lambda symbol, period: df)
        self.assertIn("signal_states", result["diagnostics"])
        self.assertGreater(result["diagnostics"]["evaluated_bars"], 0)

    def test_mexico_coverage(self):
        result = audit({"requested":2,"results":[{"symbol":"ALSEA.MX","state":"MONITORING"},
                                                       {"symbol":"PG","state":"REJECT","reason":"LOW_VOLUME"}]})
        self.assertEqual(result["mexico_share_pct"],50)
        self.assertFalse(result["issuer_mapping_verified"])


if __name__=="__main__":
    unittest.main()
