"""Completed-session freshness for daily research signals; never fills missing bars."""
from __future__ import annotations
from datetime import datetime
import pandas as pd
import exchange_calendars as xcals


def assess_daily_sessions(history, *, market: str, as_of_utc: datetime, max_lag_sessions: int = 0):
    if market not in ("MX", "US"):
        raise ValueError("invalid market")
    if as_of_utc.utcoffset() is None:
        raise ValueError("as_of_utc must be aware")
    if not isinstance(history, pd.DataFrame) or history.empty or not isinstance(history.index, pd.DatetimeIndex):
        return {"state": "REJECT", "reason": "INVALID_INDEX"}
    if not history.index.is_unique or not history.index.is_monotonic_increasing:
        return {"state": "REJECT", "reason": "INVALID_INDEX"}
    cal = xcals.get_calendar("XMEX" if market == "MX" else "XNYS")
    now = pd.Timestamp(as_of_utc)
    sessions = cal.sessions_in_range((now - pd.Timedelta(days=45)).date(), now.date())
    completed = [s for s in sessions if cal.session_close(s) <= now]
    if not completed:
        return {"state": "REJECT", "reason": "NO_COMPLETED_SESSION"}
    last = pd.Timestamp(history.index[-1]).date()
    dates = [s.date() for s in completed]
    if last not in dates:
        return {"state": "REJECT", "reason": "STALE_OR_NONSESSION_BAR", "last_bar": last.isoformat(),
                "expected_last_session": dates[-1].isoformat()}
    lag = len(dates) - 1 - dates.index(last)
    start = pd.Timestamp(history.index[0]).date()
    expected = {s.date() for s in cal.sessions_in_range(start, last)}
    actual = {s.date() for s in history.index}
    missing = sorted(expected - actual)
    # Breakout signals depend on the most recent 50 completed sessions.
    # Older gaps remain disclosed, but cannot invalidate a current signal.
    recent_start = pd.Timestamp(history.index[-50]).date() if len(history) >= 50 else start
    recent_missing = [day for day in missing if day >= recent_start]
    if recent_missing:
        return {"state": "REJECT", "reason": "MISSING_RECENT_EXCHANGE_SESSIONS",
                "last_bar": last.isoformat(), "expected_last_session": dates[-1].isoformat(),
                "missing_sessions": [x.isoformat() for x in recent_missing[:20]],
                "missing_sessions_count": len(recent_missing),
                "historical_missing_sessions": [x.isoformat() for x in missing[:20]]}
    return {"state": "CURRENT" if lag <= max_lag_sessions else "STALE",
            "historical_missing_sessions": [x.isoformat() for x in missing[:20]],
            "historical_missing_sessions_count": len(missing),
            "last_bar": last.isoformat(), "expected_last_session": dates[-1].isoformat(),
            "lag_sessions": lag}
