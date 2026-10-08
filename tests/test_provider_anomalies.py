"""Regression tests for safe provider anomalies in historical research."""
import unittest
from datetime import datetime, timezone
import pandas as pd
from tradepilot.setup_view import completed_history
from tradepilot.technical_setup import derive_levels


class ProviderAnomalyTests(unittest.TestCase):
    def test_float_dust_accepted_without_mutation(self):
        dates = pd.date_range("2026-08-01", periods=25)
        data = pd.DataFrame({"Open": [100.] * 25, "High": [102.] * 25,
                             "Low": [98.] * 25, "Close": [101.] * 25,
                             "Volume": [1000.] * 25}, index=dates)
        data.iloc[-1, data.columns.get_loc("Close")] = 102. + 4.3e-14
        before = data.copy(deep=True)
        self.assertEqual(derive_levels(data)["state"], "LEVELS_DERIVED")
        pd.testing.assert_frame_equal(data, before)

    def test_material_price_violation_rejected(self):
        dates = pd.date_range("2026-08-01", periods=25)
        data = pd.DataFrame({"Open": [100.] * 25, "High": [102.] * 25,
                             "Low": [98.] * 25, "Close": [101.] * 25,
                             "Volume": [1000.] * 25}, index=dates)
        data.iloc[-1, data.columns.get_loc("Close")] = 102.01
        self.assertEqual(derive_levels(data)["state"], "WAIT")

    def test_old_empty_placeholder_excluded(self):
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS")
        sessions = cal.sessions_in_range("2026-06-01", "2026-10-07")
        dates = pd.DatetimeIndex([s.date() for s in sessions])
        data = pd.DataFrame({"Open": 100., "High": 102., "Low": 98.,
                             "Close": 101., "Volume": 1000.}, index=dates)
        data.iloc[5, data.columns.get_loc("Open")] = float("nan")
        for col in ("High", "Low", "Close"):
            data.iloc[5, data.columns.get_loc(col)] = float("nan")
        data.iloc[5, data.columns.get_loc("Volume")] = 0
        cleaned, evidence = completed_history(data, market="US",
            as_of_utc=datetime(2026, 10, 8, 16, tzinfo=timezone.utc), calendar=cal)
        self.assertEqual(evidence, "LATEST_COMPLETED_SESSION")
        self.assertEqual(len(cleaned), len(data) - 1)
        self.assertTrue(data.iloc[5]["Close"] != data.iloc[5]["Close"])

    def test_recent_empty_placeholder_rejected(self):
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS")
        sessions = cal.sessions_in_range("2026-08-01", "2026-10-07")
        dates = pd.DatetimeIndex([s.date() for s in sessions])
        data = pd.DataFrame({"Open": 100., "High": 102., "Low": 98.,
                             "Close": 101., "Volume": 1000.}, index=dates)
        data.loc[dates[-5], ["Open", "High", "Low", "Close"]] = float("nan")
        data.loc[dates[-5], "Volume"] = 0
        cleaned, evidence = completed_history(data, market="US",
            as_of_utc=datetime(2026, 10, 8, 16, tzinfo=timezone.utc), calendar=cal)
        self.assertIsNone(cleaned)
        self.assertEqual(evidence, "RECENT_EMPTY_PROVIDER_BAR")


if __name__ == "__main__":
    unittest.main()
