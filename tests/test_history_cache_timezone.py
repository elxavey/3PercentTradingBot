"""Regression coverage for Yahoo CSV cache indices across DST."""
import unittest
import pandas as pd
from data_fetcher import _normalize_cached_history_index


class HistoryCacheTimezoneTests(unittest.TestCase):
    def test_mixed_dst_offsets_are_exchange_local(self):
        raw = pd.DataFrame({"Close": [100, 101]}, index=[
            "2026-03-06 00:00:00-05:00",
            "2026-03-09 00:00:00-04:00",
        ])
        result = _normalize_cached_history_index(raw, "AAPL")
        self.assertIsInstance(result.index, pd.DatetimeIndex)
        self.assertEqual(list(result.index.strftime("%Y-%m-%d")), ["2026-03-06", "2026-03-09"])
        self.assertEqual(str(result.index.tz), "America/New_York")

    def test_naive_dates_stay_same_local_day(self):
        raw = pd.DataFrame({"Close": [100, 101]}, index=["2026-10-07", "2026-10-08"])
        result = _normalize_cached_history_index(raw, "AMZN")
        self.assertEqual(list(result.index.strftime("%Y-%m-%d")), ["2026-10-07", "2026-10-08"])

    def test_mexico_timezone(self):
        raw = pd.DataFrame({"Close": [10]}, index=["2026-10-07 00:00:00-06:00"])
        result = _normalize_cached_history_index(raw, "ALSEA.MX")
        self.assertEqual(str(result.index.tz), "America/Mexico_City")
        self.assertEqual(str(result.index[0].date()), "2026-10-07")

    def test_invalid_date_fails_closed(self):
        with self.assertRaises(ValueError):
            _normalize_cached_history_index(pd.DataFrame({"Close": [1]}, index=["bad"]), "AAPL")

    def test_duplicate_dates_fail_closed(self):
        with self.assertRaises(ValueError):
            _normalize_cached_history_index(pd.DataFrame({"Close": [1, 2]}, index=["2026-10-07", "2026-10-07"]), "AAPL")

    def test_mixed_naive_aware_fails_closed(self):
        with self.assertRaises(ValueError):
            _normalize_cached_history_index(pd.DataFrame({"Close": [1, 2]}, index=["2026-10-07", "2026-10-08 00:00:00-04:00"]), "AAPL")


if __name__ == "__main__":
    unittest.main()
