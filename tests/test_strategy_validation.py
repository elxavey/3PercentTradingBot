"""Offline deterministic validation of backtest execution assumptions."""
import unittest
import pandas as pd
from tradepilot.strategy_validation_cli import simulate
from tradepilot.universe_quality_cli import audit


def bars(items):
    return pd.DataFrame(items, columns=["Open","High","Low","Close"])


class StrategyValidationTests(unittest.TestCase):
    def test_no_trigger(self):
        self.assertEqual(simulate(bars([(98,99,97,98)]), 100,95)["outcome"],"NOT_TRIGGERED")

    def test_gap_entry_not_trigger_fill(self):
        result = simulate(bars([(105,109,104,108)]),100,90)
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

    def test_mexico_coverage(self):
        result = audit({"requested":2,"results":[{"symbol":"ALSEA.MX","state":"MONITORING"},
                                                       {"symbol":"PG","state":"REJECT","reason":"LOW_VOLUME"}]})
        self.assertEqual(result["mexico_share_pct"],50)
        self.assertFalse(result["issuer_mapping_verified"])


if __name__=="__main__":
    unittest.main()
