"""Offline unit tests for trade-plan math and market report tier selection."""
import unittest
from datetime import datetime, timezone
from tradepilot.breakout_trade_plan import build_trade_plan
from tradepilot.morning_report import run_market_report


class TradePlanTests(unittest.TestCase):
    def test_cost_aware_net_target_and_risk(self):
        p = build_trade_plan({"reference_close": 98, "breakout_trigger": 100,
                              "structural_stop_reference": 97})
        self.assertEqual(p["plan_state"], "ILLUSTRATIVE_UNTRIGGERED")
        self.assertGreater(p["target_exit_reference"], 103)
        self.assertGreater(p["reward_risk_net"], 0)
        self.assertFalse(p["actionable"])

    def test_invalid_levels_fail_closed(self):
        p = build_trade_plan({"reference_close": 98, "breakout_trigger": 100,
                              "structural_stop_reference": 101})
        self.assertEqual(p["plan_state"], "UNAVAILABLE")

    def test_missing_levels_fail_closed(self):
        self.assertEqual(build_trade_plan({})["plan_state"], "UNAVAILABLE")


class MarketReportTests(unittest.TestCase):
    def test_market_partition_and_limits(self):
        import pandas as pd
        import exchange_calendars as xcals
        now = datetime(2026, 10, 9, 3, 44, tzinfo=timezone.utc)
        def fetch(symbol, period):
            market = "XMEX" if symbol.endswith(".MX") else "XNYS"
            cal = xcals.get_calendar(market)
            dates = cal.sessions_in_range("2026-08-01", "2026-10-08")[-45:].tz_localize(None)
            return pd.DataFrame({"Open": [95.0]*len(dates), "High": [100.0]*len(dates),
                                 "Low": [90.0]*len(dates), "Close": [98.0]*len(dates),
                                 "Volume": [200000]*len(dates)}, index=dates)
        report = run_market_report(["AAA.MX", "BBB.MX", "CCC", "DDD"],
                                   fetcher=fetch, as_of_utc=now, watch_limit=1)
        self.assertEqual(report["requested"], 4)
        self.assertEqual(report["markets"]["MX"]["reviewed"], 2)
        self.assertEqual(report["markets"]["US"]["reviewed"], 2)
        self.assertLessEqual(len(report["markets"]["MX"]["watch"]), 1)
        self.assertLessEqual(len(report["markets"]["US"]["watch"]), 1)
        self.assertFalse(report["actionable"])

    def test_limits_rejected(self):
        with self.assertRaises(ValueError):
            run_market_report([], primary_limit=11)


if __name__ == "__main__":
    unittest.main()
