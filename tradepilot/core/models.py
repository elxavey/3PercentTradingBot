"""Immutable, timezone-safe market data contracts.

Prices and bars are observations, not executable quotes or buy signals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite


class Market(str, Enum):
    MX = "MX"
    US = "US"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


def require_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    market: Market
    currency: str
    interval: str
    bar_end_utc: datetime
    fetched_at_utc: datetime
    source: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted: bool = False

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.interval.strip() or not self.source.strip():
            raise ValueError("symbol, interval and source are required")
        if self.market not in (Market.MX, Market.US):
            raise ValueError("market must be MX or US")
        expected = "MXN" if self.market == Market.MX else "USD"
        if self.currency != expected:
            raise ValueError(f"{self.market.value} bars must use {expected}")
        end = require_utc(self.bar_end_utc, "bar_end_utc")
        fetched = require_utc(self.fetched_at_utc, "fetched_at_utc")
        object.__setattr__(self, "bar_end_utc", end)
        object.__setattr__(self, "fetched_at_utc", fetched)
        if fetched < end:
            raise ValueError("fetched_at_utc cannot precede bar_end_utc")
        for name in ("open", "high", "low", "close", "volume"):
            value = getattr(self, name)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if min(self.open, self.close) <= 0 or self.low <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC prices are inconsistent")


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    market: Market
    currency: str
    price: float
    observed_at_utc: datetime
    fetched_at_utc: datetime
    source: str

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.source.strip():
            raise ValueError("symbol and source are required")
        if self.market not in (Market.MX, Market.US):
            raise ValueError("market must be MX or US")
        expected = "MXN" if self.market == Market.MX else "USD"
        if self.currency != expected:
            raise ValueError(f"{self.market.value} quotes must use {expected}")
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be finite and positive")
        observed = require_utc(self.observed_at_utc, "observed_at_utc")
        fetched = require_utc(self.fetched_at_utc, "fetched_at_utc")
        object.__setattr__(self, "observed_at_utc", observed)
        object.__setattr__(self, "fetched_at_utc", fetched)
        if fetched < observed:
            raise ValueError("fetched_at_utc cannot precede observed_at_utc")


@dataclass(frozen=True)
class FreshnessAssessment:
    status: FreshnessStatus
    age_seconds: float | None
    reason: str

    @property
    def usable_for_live_signal(self) -> bool:
        return self.status is FreshnessStatus.FRESH
