"""Unit tests for immutable models, provider interface and freshness rules."""
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from math import nan
from typing import Sequence

from tradepilot.core.market_data import MarketDataProvider, SessionState, assess_freshness
from tradepilot.core.models import (
    FreshnessStatus, Market, MarketBar, MarketQuote,
)

T0 = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)


def quote(*, observed=T0, fetched=T0, market=Market.US, currency="USD"):
    return MarketQuote("AAPL", market, currency, 100.0, observed, fetched, "test")


def bar(*, end=T0, fetched=T0):
    return MarketBar("AAPL", Market.US, "USD", "5m", end, fetched,
                     "test", 100.0, 102.0, 99.0, 101.0, 1000.0)


def check(obs, now=T0 + timedelta(minutes=1), session=SessionState.OPEN,
          max_age=timedelta(minutes=5)):
    return assess_freshness(obs, now_utc=now, max_age=max_age, session_state=session)


class MarketModelsTests(unittest.TestCase):
    def test_quote_and_bar_are_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            quote().price = 5
        with self.assertRaises(FrozenInstanceError):
            bar().close = 5

    def test_reject_naive_datetime(self):
        with self.assertRaises(ValueError):
            quote(observed=datetime(2026, 10, 8, 15, 0))
        with self.assertRaises(ValueError):
            bar(end=datetime(2026, 10, 8, 15, 0))

    def test_convert_timezone_to_utc(self):
        offset = timezone(timedelta(hours=-4))
        q = quote(observed=datetime(2026, 10, 8, 11, 0, tzinfo=offset))
        self.assertEqual(q.observed_at_utc, T0)

    def test_reject_invalid_market_currency(self):
        with self.assertRaises(ValueError):
            quote(market=Market.MX, currency="USD")

    def test_reject_invalid_prices_and_ohlc(self):
        with self.assertRaises(ValueError):
            MarketQuote("AAPL", Market.US, "USD", nan, T0, T0, "test")
        with self.assertRaises(ValueError):
            MarketBar("AAPL", Market.US, "USD", "5m", T0, T0,
                      "test", 100, 101, 99, 102, 1000)

    def test_reject_fetch_before_observation(self):
        with self.assertRaises(ValueError):
            quote(observed=T0, fetched=T0 - timedelta(seconds=1))


class FreshnessTests(unittest.TestCase):
    def test_fresh_quote(self):
        result = check(quote())
        self.assertEqual(result.status, FreshnessStatus.FRESH)
        self.assertTrue(result.usable_for_live_signal)
        self.assertEqual(result.age_seconds, 60)

    def test_fresh_completed_bar(self):
        self.assertEqual(check(bar()).status, FreshnessStatus.FRESH)

    def test_stale_quote(self):
        result = check(quote(), now=T0 + timedelta(minutes=6))
        self.assertEqual(result.status, FreshnessStatus.STALE)
        self.assertFalse(result.usable_for_live_signal)

    def test_unknown_when_missing(self):
        self.assertEqual(check(None).status, FreshnessStatus.UNKNOWN)

    def test_unknown_session_fails_closed(self):
        self.assertEqual(check(quote(), session=SessionState.UNKNOWN).status,
                         FreshnessStatus.UNKNOWN)

    def test_closed_market_is_not_live(self):
        self.assertEqual(check(quote(), session=SessionState.CLOSED).status,
                         FreshnessStatus.STALE)

    def test_future_observation_fails_closed(self):
        result = check(quote(), now=T0 - timedelta(seconds=1))
        self.assertEqual(result.status, FreshnessStatus.UNKNOWN)

    def test_fetch_in_future_fails_closed(self):
        result = check(quote(fetched=T0 + timedelta(minutes=2)))
        self.assertEqual(result.reason, "FETCHED_IN_FUTURE")

    def test_age_boundary(self):
        result = check(quote(), now=T0 + timedelta(minutes=5))
        self.assertEqual(result.status, FreshnessStatus.FRESH)

    def test_reject_nonpositive_age_limit(self):
        with self.assertRaises(ValueError):
            check(quote(), max_age=timedelta(0))

    def test_provider_protocol_with_fake(self):
        class FakeProvider:
            def get_daily_history(self, symbol: str, *, lookback_days: int) -> Sequence[MarketBar]:
                return [bar()]
            def get_intraday_bars(self, symbol: str, *, interval: str, limit: int) -> Sequence[MarketBar]:
                return [bar()]
            def get_quote(self, symbol: str) -> MarketQuote | None:
                return quote()
        provider = FakeProvider()
        self.assertIsInstance(provider, MarketDataProvider)
        self.assertEqual(provider.get_quote("AAPL").price, 100)


if __name__ == "__main__":
    unittest.main()
