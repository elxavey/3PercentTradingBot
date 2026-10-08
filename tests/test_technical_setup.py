"""Phase 3.2 deterministic completed-bar setup tests."""
import unittest
import pandas as pd

from tradepilot.technical_setup import derive_levels, research_breakout
from tradepilot.trade_setup import RiskPolicy


def candles(n=30):
    dates = pd.date_range("2026-08-01", periods=n, freq="B")
    return pd.DataFrame({
        "Open": [100.0] * n, "High": [102.0] * n,
        "Low": [98.0] * n, "Close": [100.0] * n,
        "Volume": [1000] * n,
    }, index=dates)


class TechnicalSetupTests(unittest.TestCase):
    def test_deterministic_structure(self):
        result = derive_levels(candles())
        self.assertEqual(result["state"], "LEVELS_DERIVED")
        self.assertEqual(result["resistance"], 102.0)
        self.assertEqual(result["support"], 98.0)
        self.assertGreater(result["entry_trigger"], 102)
        self.assertLess(result["structural_stop"], 98)
        self.assertGreater(result["target"], result["entry_trigger"])

    def test_ignores_old_bars(self):
        frame = candles()
        frame.iloc[0, frame.columns.get_loc("High")] = 200
        self.assertEqual(derive_levels(frame)["resistance"], 102)

    def test_not_enough_bars(self):
        self.assertEqual(derive_levels(candles(5))["state"], "WAIT")

    def test_missing_history(self):
        self.assertEqual(derive_levels(None)["reasons"], ["MISSING_COMPLETED_HISTORY"])

    def test_missing_column(self):
        self.assertEqual(derive_levels(candles().drop(columns=["Volume"]))["state"], "WAIT")

    def test_invalid_ohlc(self):
        frame = candles()
        frame.loc[frame.index[-1], "High"] = 90
        self.assertEqual(derive_levels(frame)["reasons"], ["INVALID_OHLCV"])

    def test_reject_unordered_bars(self):
        self.assertEqual(derive_levels(candles().iloc[::-1])["state"], "WAIT")

    def test_reject_nan(self):
        frame = candles()
        frame.loc[frame.index[-1], "Close"] = float("nan")
        self.assertEqual(derive_levels(frame)["state"], "WAIT")

    def test_reject_invalid_configuration(self):
        with self.assertRaises(ValueError):
            derive_levels(candles(), stop_lookback=21)
        with self.assertRaises(ValueError):
            derive_levels(candles(), target_r=0)

    def test_risk_integration_never_actionable(self):
        result = research_breakout(symbol="WALMEX.MX", market="MX",
                                   history=candles(), policy=RiskPolicy())
        self.assertEqual(result["state"], "WAIT")
        self.assertFalse(result["actionable"])
        self.assertEqual(result["risk"]["state"], "WAIT")
        self.assertIn("LIVE_QUOTE_NOT_VERIFIED", result["risk"]["reasons"])

    def test_no_future_bar_lookahead(self):
        frame = candles()
        before = derive_levels(frame.iloc[:-1])
        frame.loc[frame.index[-1], "High"] = 150
        after = derive_levels(frame.iloc[:-1])
        self.assertEqual(before, after)

    def test_nonnegative_volume_required(self):
        frame = candles()
        frame.loc[frame.index[-1], "Volume"] = -1
        self.assertEqual(derive_levels(frame)["state"], "WAIT")


if __name__ == "__main__":
    unittest.main()
