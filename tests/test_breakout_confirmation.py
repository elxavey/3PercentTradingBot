"""Phase 3.6 historical confirmation tests; no network."""
import unittest

import pandas as pd

from tradepilot.breakout_confirmation import ConfirmationPolicy, confirm_breakout


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        closes = [90 + i * 0.2 for i in range(30)]
        self.data = pd.DataFrame({
            "Open": closes,
            "High": [x + 1 for x in closes],
            "Low": [x - 1 for x in closes],
            "Close": closes,
            "Volume": [1000] * 30,
        }, index=pd.date_range("2026-08-01", periods=30))

    def breakout(self):
        df = self.data.copy()
        # Prior resistance is below 96.6. Both completed closes above it.
        for i, close in [(-2, 100.0), (-1, 101.0)]:
            df.iloc[i, df.columns.get_loc("Open")] = close - 1
            df.iloc[i, df.columns.get_loc("Close")] = close
            df.iloc[i, df.columns.get_loc("High")] = close + 1
            df.iloc[i, df.columns.get_loc("Low")] = close - 2
            df.iloc[i, df.columns.get_loc("Volume")] = 1500
        return df

    def test_passed_filters_not_actionable(self):
        result = confirm_breakout(self.breakout())
        self.assertEqual(result["state"], "HISTORICAL_FILTERS_PASSED")
        self.assertFalse(result["actionable"])
        self.assertEqual(result["confirmed_closes"], 2)

    def test_low_volume_fails(self):
        df = self.breakout()
        df.iloc[-1, df.columns.get_loc("Volume")] = 100
        self.assertIn("VOLUME_NOT_CONFIRMED", confirm_breakout(df)["reasons"])

    def test_one_close_fails_persistence(self):
        df = self.breakout()
        df.iloc[-2, df.columns.get_loc("Close")] = 95
        self.assertIn("PERSISTENCE_NOT_CONFIRMED", confirm_breakout(df)["reasons"])

    def test_flat_trend_fails(self):
        df = self.breakout()
        df.loc[df.index[:-2], "Close"] = 95
        self.assertIn("TREND_NOT_CONFIRMED", confirm_breakout(df)["reasons"])

    def test_insufficient_data(self):
        self.assertEqual(confirm_breakout(self.data.iloc[:20])["state"],
                         "INSUFFICIENT_DATA")

    def test_invalid_history(self):
        df = self.breakout()
        df.iloc[-1, df.columns.get_loc("High")] = 1
        self.assertEqual(confirm_breakout(df)["state"], "INSUFFICIENT_DATA")

    def test_zero_baseline_volume(self):
        df = self.breakout()
        df.loc[df.index[:-2], "Volume"] = 0
        self.assertIn("ZERO_BASELINE_VOLUME", confirm_breakout(df)["reasons"])

    def test_no_future_lookahead(self):
        df = self.breakout()
        before = confirm_breakout(df)
        extra = df.iloc[-1:].copy()
        extra.index = [df.index[-1] + pd.Timedelta(days=1)]
        extra["Close"] = 50
        extra["Low"] = 49
        extra["Open"] = 50
        extra["High"] = 51
        result = confirm_breakout(pd.concat([df, extra]).iloc[:-1])
        self.assertEqual(before, result)

    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            ConfirmationPolicy(persistence_sessions=1)

    def test_policy_type(self):
        with self.assertRaises(TypeError):
            confirm_breakout(self.data, policy="invalid")


if __name__ == "__main__":
    unittest.main()
