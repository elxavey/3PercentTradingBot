"""Phase 4.4: fail-closed validation of completed daily bars for research.

Never interpolate missing sessions or silently repair malformed OHLCV.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

import pandas as pd

from tradepilot.setup_view import completed_history
from tradepilot.technical_setup import derive_levels
from tradepilot.backtest_runner import run_backtest
from tradepilot.historical_simulator import SimulationPolicy


def validate_history(history, *, market: str, as_of_utc: datetime,
                     min_sessions: int = 100, calendar=None) -> dict:
    if market not in ("MX", "US"):
        raise ValueError("market must be MX or US")
    if not isinstance(min_sessions, int) or isinstance(min_sessions, bool) or min_sessions < 25:
        raise ValueError("min_sessions must be >= 25")
    completed, evidence = completed_history(
        history, market=market, as_of_utc=as_of_utc, calendar=calendar)
    base = {"state": "REJECT", "reasons": [], "history": None,
            "completed_sessions": 0, "missing_sessions": []}
    if completed is None:
        return {**base, "reasons": [evidence]}
    if len(completed) < min_sessions:
        return {**base, "reasons": ["INSUFFICIENT_HISTORY"],
                "completed_sessions": len(completed)}
    # Strict validation of every bar, not merely the most recent window.
    levels = derive_levels(completed, lookback=len(completed),
                           stop_lookback=2)
    if levels["state"] != "LEVELS_DERIVED":
        return {**base, "reasons": levels["reasons"],
                "completed_sessions": len(completed)}
    import exchange_calendars as xcals
    cal = calendar or xcals.get_calendar("XMEX" if market == "MX" else "XNYS")
    first, last = completed.index[0].date(), completed.index[-1].date()
    expected = {s.date() for s in cal.sessions_in_range(first, last)}
    actual = {s.date() for s in completed.index}
    missing = sorted(expected - actual)
    if missing:
        return {**base, "reasons": ["MISSING_EXCHANGE_SESSIONS"],
                "completed_sessions": len(completed),
                "missing_sessions": [d.isoformat() for d in missing[:20]],
                "missing_sessions_count": len(missing)}
    return {"state": "VALIDATED", "reasons": [],
            "history": completed, "completed_sessions": len(completed),
            "first_session": first.isoformat(), "last_session": last.isoformat(),
            "missing_sessions": [], "history_evidence": evidence}


def validated_backtest(history, *, symbol: str, market: str,
                       as_of_utc: datetime,
                       simulation_policy: SimulationPolicy,
                       min_sessions: int = 100, calendar=None) -> dict:
    if not isinstance(simulation_policy, SimulationPolicy):
        raise TypeError("explicit simulation policy required")
    # Prevent accidental zero-cost profitability claims.
    if simulation_policy.fee_rate_per_side <= 0 or simulation_policy.slippage_rate_per_side <= 0:
        raise ValueError("explicit positive fees and slippage required")
    validation = validate_history(history, market=market, as_of_utc=as_of_utc,
                                  min_sessions=min_sessions, calendar=calendar)
    if validation["state"] != "VALIDATED":
        return {"state": "REJECT", "reasons": validation["reasons"],
                "validation": {k:v for k,v in validation.items() if k != "history"},
                "actionable": False}
    result = run_backtest(validation["history"], symbol=symbol, market=market,
                          simulation_policy=simulation_policy)
    return {"state": "RESEARCH_RESULT", "actionable": False,
            "validation": {k:v for k,v in validation.items() if k != "history"},
            "backtest": result}
