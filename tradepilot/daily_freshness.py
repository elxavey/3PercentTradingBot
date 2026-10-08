"""Conservative daily-history freshness evidence for incremental research.

A daily Yahoo history index is a session *date*, not a verified quote
timestamp. FRESH means the latest completed exchange session is represented;
it never means a live/intraday quote is fresh.
"""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd


def assess_daily_history(history, *, market: str, as_of_utc: datetime, calendar=None) -> dict:
    unknown = {"status": "UNKNOWN", "reason": "NO_VERIFIED_SESSION_DATE",
               "latest_bar_session": None, "expected_completed_session": None}
    if history is None or getattr(history, "empty", True):
        return {**unknown, "reason": "NO_HISTORY"}
    if as_of_utc.tzinfo is None or as_of_utc.utcoffset() is None:
        raise ValueError("as_of_utc must be timezone-aware")
    if market not in ("MX", "US"):
        return {**unknown, "reason": "UNKNOWN_MARKET"}
    try:
        import exchange_calendars as xcals
        cal = calendar or xcals.get_calendar("XMEX" if market == "MX" else "XNYS")
        last = pd.Timestamp(history.index[-1])
        # A daily history date is not a verified bar-close timestamp.
        session_date = last.date()
        now = pd.Timestamp(as_of_utc.astimezone(timezone.utc))
        # Look back at most 14 calendar days to find the last completed session.
        start = (now - pd.Timedelta(days=14)).date()
        sessions = cal.sessions_in_range(start, now.date())
        completed = [s for s in sessions if cal.session_close(s) <= now]
        if not completed:
            return {**unknown, "reason": "NO_COMPLETED_SESSION_IN_WINDOW"}
        expected = completed[-1].date()
        if session_date > expected:
            return {**unknown, "reason": "HISTORY_DATE_AFTER_LAST_COMPLETED_SESSION",
                    "latest_bar_session": session_date.isoformat(),
                    "expected_completed_session": expected.isoformat()}
        if not cal.is_session(session_date):
            return {**unknown, "reason": "HISTORY_DATE_NOT_EXCHANGE_SESSION",
                    "latest_bar_session": session_date.isoformat(),
                    "expected_completed_session": expected.isoformat()}
        return {
            "status": "FRESH" if session_date == expected else "STALE",
            "reason": "LATEST_COMPLETED_DAILY_SESSION" if session_date == expected
                      else "OLDER_THAN_LAST_COMPLETED_DAILY_SESSION",
            "latest_bar_session": session_date.isoformat(),
            "expected_completed_session": expected.isoformat(),
        }
    except (ValueError, TypeError, KeyError, OverflowError, ImportError) as exc:
        return {**unknown, "reason": f"UNVERIFIABLE_SESSION_DATE:{type(exc).__name__}"}
