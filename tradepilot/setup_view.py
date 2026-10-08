"""Read-only Phase 3.3 adapter: confirmed completed daily sessions only."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from data_fetcher import get_price_history
from tradepilot.technical_setup import research_breakout
from tradepilot.trade_setup import RiskPolicy
from tradepilot.setup_visual import chart_candles


def completed_history(history: pd.DataFrame | None, *, market: str,
                      as_of_utc: datetime, calendar=None) -> tuple[pd.DataFrame | None, str]:
    """Drop current/incomplete sessions, fail closed on unverifiable dates."""
    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() is None:
        raise ValueError("as_of_utc must be timezone-aware")
    if market not in ("MX", "US"):
        return None, "UNKNOWN_MARKET"
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return None, "NO_HISTORY"
    try:
        import exchange_calendars as xcals
        cal = calendar or xcals.get_calendar("XMEX" if market == "MX" else "XNYS")
        now = pd.Timestamp(as_of_utc.astimezone(timezone.utc))
        sessions = cal.sessions_in_range((now - pd.Timedelta(days=30)).date(), now.date())
        completed = [s for s in sessions if cal.session_close(s) <= now]
        if not completed:
            return None, "NO_COMPLETED_SESSION"
        cutoff = completed[-1].date()
        dates = pd.to_datetime(history.index, errors="raise")
        if dates.isna().any() or not dates.is_monotonic_increasing or not dates.is_unique:
            return None, "INVALID_HISTORY_INDEX"
        # Date-only Yahoo daily bars are not intraday quotes. Exclude current
        # exchange session until its calendar close; never use future candles.
        mask = [stamp.date() <= cutoff for stamp in dates]
        filtered = history.loc[mask].copy()
        if filtered.empty:
            return None, "NO_COMPLETED_BARS"
        if any(not cal.is_session(stamp.date()) for stamp in dates[mask]):
            return None, "NON_SESSION_HISTORY_DATE"
        return filtered, ("LATEST_COMPLETED_SESSION" if dates[mask][-1].date() == cutoff
                          else "OLDER_COMPLETED_SESSION")
    except (ValueError, TypeError, KeyError, OverflowError, ImportError) as exc:
        return None, f"UNVERIFIABLE_HISTORY:{type(exc).__name__}"


def analyze_watchlist_symbol(*, symbol: str, market: str,
                             policy: RiskPolicy, as_of_utc: datetime,
                             fetcher=get_price_history, calendar=None) -> dict:
    """Research-only: fetch cached/Yahoo daily bars on explicit UI request."""
    if market not in ("MX", "US") or not symbol:
        raise ValueError("symbol and market required")
    history = fetcher(symbol)
    completed, evidence = completed_history(
        history, market=market, as_of_utc=as_of_utc, calendar=calendar
    )
    if completed is None:
        return {"symbol": symbol, "market": market, "state": "WAIT",
                "actionable": False, "reasons": [evidence], "history_evidence": evidence}
    result = research_breakout(symbol=symbol, market=market,
                               history=completed, policy=policy)
    return {**result, "history_evidence": evidence, "completed_bars": len(completed),
            "chart_history": chart_candles(completed)}
