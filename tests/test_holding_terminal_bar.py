"""Phase 4.8 terminal provider bar regression tests."""
import unittest
from datetime import datetime, timezone
import pandas as pd
from tradepilot.holding_sensitivity_cli import exclude_trailing_empty_prices


class TerminalBarTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 1, 0, tzinfo=timezone.utc)
        self.index = pd.DatetimeIndex(["2026-10-07", "2026-10-08"], tz="America/New_York")
        self.clean = pd.DataFrame({"Open": [100., 101.], "High": [102., 103.],
                                   "Low": [99., 100.], "Close": [101., 102.],
                                   "Volume": [1000, 2000]}, index=self.index)

    def test_last_completed_missing_ohlc_excluded(self):
        df = self.clean.copy()
        df.loc[self.index[-1], ["Open", "High", "Low", "Close"]] = float("nan")
        result, excluded = exclude_trailing_empty_prices(df, as_of_utc=self.now, market="US")
        self.assertEqual(len(result), 1)
        self.assertEqual(excluded, ["2026-10-08"])

    def test_interior_missing_bar_never_excluded(self):
        df = self.clean.copy()
        df.loc[self.index[0], ["Open", "High", "Low", "Close"]] = float("nan")
        result, excluded = exclude_trailing_empty_prices(df, as_of_utc=self.now, market="US")
        self.assertEqual(len(result), 2)
        self.assertEqual(excluded, [])

    def test_valid_last_bar_kept(self):
        result, excluded = exclude_trailing_empty_prices(self.clean, as_of_utc=self.now, market="US")
        self.assertEqual(len(result), 2)
        self.assertEqual(excluded, [])

    def test_older_missing_last_bar_kept(self):
        df = self.clean.iloc[:1].copy()
        df.loc[self.index[0], ["Open", "High", "Low", "Close"]] = float("nan")
        result, excluded = exclude_trailing_empty_prices(df, as_of_utc=self.now, market="US")
        self.assertEqual(len(result), 1)
        self.assertEqual(excluded, [])


if __name__ == "__main__":
    unittest.main()
