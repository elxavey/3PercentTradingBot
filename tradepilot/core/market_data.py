"""Provider contract and conservative, exchange-aware freshness assessment.

Freshness requires a known exchange session state supplied by a calendar service.
No exchange calendars or intraday feeds are assumed to exist yet.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol, Sequence, runtime_checkable

from .models import (
    FreshnessAssessment, FreshnessStatus, MarketBar, MarketQuote, require_utc,
)


class SessionState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


@runtime_checkable
class MarketDataProvider(Protocol):
    """Interface only: no network calls, provider claims or order execution."""

    def get_daily_history(self, symbol: str, *, lookback_days: int) -> Sequence[MarketBar]:
        ...

    def get_intraday_bars(self, symbol: str, *, interval: str, limit: int) -> Sequence[MarketBar]:
        ...

    def get_quote(self, symbol: str) -> MarketQuote | None:
        ...


def assess_freshness(
    observation: MarketBar | MarketQuote | None,
    *,
    now_utc: datetime,
    max_age: timedelta,
    session_state: SessionState,
) -> FreshnessAssessment:
    """Fail closed when quote/bar time, market session or provider is unknown.

    A closed market cannot produce a *live* signal, even with recent data.
    For a completed bar, age is measured from bar_end_utc, not fetch time.
    """
    now = require_utc(now_utc, "now_utc")
    if observation is None:
        return FreshnessAssessment(FreshnessStatus.UNKNOWN, None, "NO_OBSERVATION")
    if max_age <= timedelta(0):
        raise ValueError("max_age must be positive")
    if session_state is SessionState.UNKNOWN:
        return FreshnessAssessment(FreshnessStatus.UNKNOWN, None, "SESSION_UNKNOWN")
    if session_state is SessionState.CLOSED:
        return FreshnessAssessment(FreshnessStatus.STALE, None, "MARKET_CLOSED")
    if session_state is not SessionState.OPEN:
        return FreshnessAssessment(FreshnessStatus.UNKNOWN, None, "SESSION_INVALID")

    observed_at = (
        observation.bar_end_utc if isinstance(observation, MarketBar)
        else observation.observed_at_utc
    )
    observed_at = require_utc(observed_at, "observation timestamp")
    fetched_at = require_utc(observation.fetched_at_utc, "fetched_at_utc")
    if fetched_at > now:
        return FreshnessAssessment(FreshnessStatus.UNKNOWN, None, "FETCHED_IN_FUTURE")
    age = (now - observed_at).total_seconds()
    if age < 0:
        return FreshnessAssessment(FreshnessStatus.UNKNOWN, None, "OBSERVED_IN_FUTURE")
    if age > max_age.total_seconds():
        return FreshnessAssessment(FreshnessStatus.STALE, age, "AGE_EXCEEDED")
    return FreshnessAssessment(FreshnessStatus.FRESH, age, "WITHIN_AGE_LIMIT")
