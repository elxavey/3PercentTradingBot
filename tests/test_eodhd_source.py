import unittest
from unittest.mock import Mock
import pandas as pd

from tradepilot.eodhd_source import eodhd_daily, verified_eodhd_daily, diagnose_eodhd_neighbors


def reference():
    return pd.DataFrame({"Close": [100.0, 102.0]},
                        index=pd.to_datetime(["2026-04-21", "2026-04-23"]))


def fixture(symbol, start, end):
    values = {"2026-04-21": 100., "2026-04-22": 101.,
              "2026-04-23": 102.}
    day = pd.Timestamp(start)
    value = values[start]
    return pd.DataFrame({"Open": [value], "High": [value+1],
                         "Low": [value-1], "Close": [value],
                         "Volume": [1200]}, index=pd.DatetimeIndex([day]))


class EodhdSourceTests(unittest.TestCase):
    def test_no_key_does_not_call_network(self):
        import unittest.mock as mock
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertTrue(eodhd_daily("ALSEA.MX","2026-04-22","2026-04-23").empty)

    def test_json_maps_to_daily_ohlcv(self):
        response = Mock()
        response.json.return_value = [{"date":"2026-04-22","open":100,
                                         "high":102,"low":99,"close":101,
                                         "volume":1234}]
        requester = Mock(return_value=response)
        result = eodhd_daily("ALSEA.MX","2026-04-22","2026-04-23",
                             token="test-token",requester=requester)
        self.assertEqual(len(result),1)
        self.assertEqual(result.iloc[0]["Volume"],1234)
        self.assertEqual(requester.call_args.kwargs["params"]["to"],"2026-04-22")

    def test_verified_neighbors_allow_missing_day(self):
        result = verified_eodhd_daily("ALSEA.MX","2026-04-22","2026-04-23",
                                      reference=reference(),fetcher=fixture)
        self.assertEqual(len(result),1)
        self.assertEqual(result.iloc[0]["Close"],101.)

    def test_adjustment_mismatch_rejects(self):
        def inconsistent(symbol,start,end):
            result = fixture(symbol,start,end)
            result["Close"] *= 1.04
            return result
        result = verified_eodhd_daily("ALSEA.MX","2026-04-22","2026-04-23",
                                      reference=reference(),fetcher=inconsistent)
        self.assertTrue(result.empty)

    def test_diagnostic_neighbors_match(self):
        report = diagnose_eodhd_neighbors("ALSEA.MX","2026-04-22",
                                           reference=reference(),fetcher=fixture)
        self.assertEqual(report["state"],"NEIGHBORS_MATCH_AND_TARGET_PRESENT")

    def test_diagnostic_mismatch_explains_prices(self):
        def shifted(symbol,start,end):
            df = fixture(symbol,start,end)
            df["Close"] *= 1.04
            return df
        report = diagnose_eodhd_neighbors("ALSEA.MX","2026-04-22",
                                           reference=reference(),fetcher=shifted)
        self.assertEqual(report["state"],"ADJUSTMENT_BASIS_MISMATCH")
        self.assertEqual(len(report["observations"]),2)

    def test_diagnostic_missing_neighbor(self):
        def missing(symbol,start,end):
            return pd.DataFrame()
        report = diagnose_eodhd_neighbors("ALSEA.MX","2026-04-22",
                                           reference=reference(),fetcher=missing)
        self.assertEqual(report["state"],"NEIGHBOR_NOT_RETURNED")

    def test_bad_symbol_or_range_rejected(self):
        with self.assertRaises(ValueError):
            eodhd_daily("ALSEA.MX","2026-04-22","2026-04-25",token="test")
        with self.assertRaises(ValueError):
            eodhd_daily("bad/path","2026-04-22","2026-04-23",token="test")

if __name__ == "__main__":
    unittest.main()
