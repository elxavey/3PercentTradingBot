"""Offline tests for research-only breakout shortlist."""
import unittest
from datetime import datetime, timezone
import pandas as pd
from config import BREAKOUT_TEST_SYMBOLS, UNIVERSES
from tradepilot.breakout_shortlist_cli import analyze_symbol, shortlist


def bars(last_close=98):
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    dates = cal.sessions_in_range("2026-08-20", "2026-10-08")[-30:].tz_localize(None)
    close = [95.0] * 29 + [last_close]
    high = [100.0] * 29 + [max(100.0, last_close)]
    return pd.DataFrame({"Open": [95.0] * 30, "High": high,
                         "Low": [90.0] * 30, "Close": close,
                         "Volume": [200_000] * 30}, index=dates)


class BreakoutShortlistTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 3, 44, tzinfo=timezone.utc)

    def test_universe_excludes_crypto_and_futures(self):
        self.assertEqual(UNIVERSES["Breakout test - user equities"], BREAKOUT_TEST_SYMBOLS)
        self.assertEqual(len(BREAKOUT_TEST_SYMBOLS), len(set(BREAKOUT_TEST_SYMBOLS)))
        for name in ("BTCUSD", "SHIBUSDT", "SI1!", "NATGAS", "NATURALG"):
            self.assertNotIn(name, BREAKOUT_TEST_SYMBOLS)

    def test_approaching_has_trigger_and_no_action(self):
        r = analyze_symbol("TEST", bars(), as_of_utc=self.now)
        self.assertEqual(r["state"], "APPROACHING")
        self.assertEqual(r["session_quality"]["state"], "CURRENT")
        self.assertAlmostEqual(r["breakout_trigger"], 100.1)
        self.assertFalse(r["actionable"])

    def test_no_forced_top_ten(self):
        report = shortlist(["TEST", "FAR"], fetcher=lambda s, period: bars(98 if s == "TEST" else 91),
                           as_of_utc=self.now)
        self.assertEqual([r["symbol"] for r in report["top"]], ["TEST"])
        self.assertFalse(report["actionable"])

    def test_current_utc_date_excluded(self):
        data = bars()
        data.loc[pd.Timestamp("2026-10-09")] = [95, 200, 90, 199, 200000]
        r = analyze_symbol("TEST", data, as_of_utc=self.now)
        self.assertEqual(r["state"], "APPROACHING")

    def test_completed_terminal_empty_bar_is_excluded(self):
        data = bars()
        data.loc[pd.Timestamp("2026-10-08")] = [float("nan")] * 4 + [200000]
        now = datetime(2026, 10, 9, 3, 44, tzinfo=timezone.utc)
        r = analyze_symbol("TEST", data, as_of_utc=now)
        self.assertEqual(r["state"], "APPROACHING")
        self.assertEqual(r["excluded_terminal_bars"], ["2026-10-08"])

    def test_interior_empty_bar_is_rejected(self):
        data = bars()
        data.iloc[-3, data.columns.get_loc("Close")] = float("nan")
        r = analyze_symbol("TEST", data, as_of_utc=self.now)
        self.assertEqual(r["state"], "REJECT")
        self.assertEqual(r["reason"], "INVALID_OHLCV")

    def test_stale_completed_session_excluded_from_top(self):
        old = bars().iloc[:-1]
        report = shortlist(["OLD"], fetcher=lambda s, period: old, as_of_utc=self.now)
        self.assertEqual(report["top"], [])
        self.assertEqual(report["results"][0]["session_quality"]["state"], "STALE")

    def test_volume_confirmation_not_automatic(self):
        r = analyze_symbol("TEST", bars(101), as_of_utc=self.now)
        self.assertEqual(r["state"], "BREAKOUT_PENDING_CONFIRMATION")
        self.assertFalse(r["confirmation_checks"]["relative_volume_at_least_1_5"])
        self.assertFalse(r["actionable"])

    def test_old_gap_disclosed_but_current_signal_allowed(self):
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS")
        dates = cal.sessions_in_range("2026-04-01", "2026-10-08").tz_localize(None)
        history = pd.DataFrame({"Open": 95.0, "High": 100.0, "Low": 90.0,
                                "Close": 98.0, "Volume": 200000}, index=dates)
        missing = dates[5]
        history = history.drop(missing)
        r = analyze_symbol("TEST", history, as_of_utc=self.now)
        self.assertEqual(r["session_quality"]["state"], "CURRENT")
        self.assertIn(missing.date().isoformat(),
                      r["session_quality"]["historical_missing_sessions"])

    def test_recent_gap_rejected(self):
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS")
        dates = cal.sessions_in_range("2026-04-01", "2026-10-08").tz_localize(None)
        history = pd.DataFrame({"Open": 95.0, "High": 100.0, "Low": 90.0,
                                "Close": 98.0, "Volume": 200000}, index=dates)
        history = history.drop(dates[-5])
        r = analyze_symbol("TEST", history, as_of_utc=self.now)
        self.assertEqual(r["state"], "REJECT")
        self.assertEqual(r["reason"], "MISSING_RECENT_EXCHANGE_SESSIONS")

    def test_low_liquidity_rejected(self):
        r = analyze_symbol("TEST", bars(), min_turnover=100_000_000,
                           as_of_utc=self.now)
        self.assertEqual(r["reason"], "LOW_OR_INVALID_TURNOVER")


if __name__ == "__main__":
    unittest.main()
