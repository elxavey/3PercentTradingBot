import unittest
import pandas as pd
from tradepilot.history_recovery import recover_missing_sessions


def sample():
    return pd.DataFrame({"Open":[100.,100.],"High":[101.,101.],
                         "Low":[99.,99.],"Close":[100.,100.],
                         "Volume":[1000.,1000.]},
                        index=pd.to_datetime(["2026-04-21","2026-04-23"]))

def provider(ticker,start,end):
    return pd.DataFrame({"Open":[100.],"High":[102.],"Low":[99.],
                         "Close":[101.],"Volume":[1234.]},
                        index=pd.to_datetime(["2026-04-22"]))


class HistoryRecoveryTests(unittest.TestCase):
    def test_recovers_real_provider_bar(self):
        fixed, log = recover_missing_sessions(sample(),["2026-04-22"],
                                               symbol="ALSEA.MX",fetcher=provider)
        self.assertEqual(len(fixed),3)
        self.assertEqual(log["state"],"RECOVERED")
        self.assertEqual(log["synthetic_bars"],0)
        self.assertEqual(fixed.loc["2026-04-22","Volume"],1234)

    def test_no_data_remains_unresolved(self):
        fixed, log = recover_missing_sessions(
            sample(),["2026-04-22"],symbol="ALSEA.MX",
            fetcher=lambda *a: pd.DataFrame())
        self.assertEqual(len(fixed),2)
        self.assertEqual(log["state"],"PARTIAL_OR_FAILED")

    def test_adjacent_date_is_not_accepted(self):
        fixed, log = recover_missing_sessions(
            sample(),["2026-04-22"],symbol="ALSEA.MX",
            fetcher=lambda *a: sample().iloc[:1])
        self.assertEqual(len(fixed),2)
        self.assertEqual(log["unresolved"],["2026-04-22"])

    def test_bad_ohlc_rejected(self):
        def invalid(*args):
            df = provider(*args)
            df["High"] = 90.
            return df
        fixed, log = recover_missing_sessions(
            sample(),["2026-04-22"],symbol="ALSEA.MX",fetcher=invalid)
        self.assertEqual(len(fixed),2)
        self.assertEqual(log["state"],"PARTIAL_OR_FAILED")

    def test_many_missing_sessions_do_not_auto_repair(self):
        fixed, log = recover_missing_sessions(
            sample(),["2026-04-22"]*6,symbol="ALSEA.MX",fetcher=provider)
        self.assertEqual(len(fixed),2)
        self.assertEqual(log["state"],"NOT_ATTEMPTED")

if __name__ == "__main__":
    unittest.main()
