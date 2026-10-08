"""Phase 3.5: deterministic, research-only opportunity monitoring.

Historical observations are reconstructed from completed candles on demand.
No live quotes, SQLite writes, scheduler changes or trade execution.
"""
from __future__ import annotations

from math import isfinite

import pandas as pd

from tradepilot.technical_setup import derive_levels


STATES = ("APPROACHING", "BREAKOUT_CANDIDATE", "MONITORING", "INSUFFICIENT_DATA")


def classify_opportunity(history: pd.DataFrame | None, *, near_pct: float = 3.0,
                         lookback: int = 20, stop_lookback: int = 10) -> dict:
    """Compare last completed close against PRIOR completed bars' resistance.

    Current bar is excluded from the resistance calculation to prevent
    self-referential thresholds. A candidate is NOT a confirmed breakout.
    """
    if not isinstance(near_pct, (int, float)) or not isfinite(near_pct) or not 0 < near_pct <= 20:
        raise ValueError("near_pct must be finite and between 0 and 20")
    if not isinstance(lookback, int) or lookback < 2:
        raise ValueError("lookback must be >= 2")
    if not isinstance(stop_lookback, int) or not 2 <= stop_lookback <= lookback:
        raise ValueError("stop_lookback must be 2..lookback")
    empty = {"state": "INSUFFICIENT_DATA", "distance_pct": None,
             "close": None, "resistance": None, "session": None,
             "reason": "INSUFFICIENT_COMPLETED_HISTORY", "actionable": False}
    if history is None or not isinstance(history, pd.DataFrame) or len(history) < lookback + 1:
        return empty
    prior = derive_levels(history.iloc[:-1], lookback=lookback,
                          stop_lookback=stop_lookback)
    if prior.get("state") != "LEVELS_DERIVED":
        return {**empty, "reason": ",".join(prior.get("reasons", ["INVALID_HISTORY"]))}
    # Validate the complete slice, including latest OHLCV, not just close.
    check = derive_levels(history, lookback=lookback, stop_lookback=stop_lookback)
    if check.get("state") != "LEVELS_DERIVED":
        return {**empty, "reason": ",".join(check.get("reasons", ["INVALID_HISTORY"]))}
    close = float(history["Close"].iloc[-1])
    resistance = float(prior["resistance"])
    distance = (resistance - close) / resistance * 100
    if close > resistance:
        state = "BREAKOUT_CANDIDATE"
    elif distance <= near_pct:
        state = "APPROACHING"
    else:
        state = "MONITORING"
    return {"state": state, "distance_pct": round(distance, 3),
            "close": close, "resistance": resistance,
            "session": str(history.index[-1])[:10],
            "reason": "COMPLETED_BAR_RESEARCH_ONLY", "actionable": False}


def opportunity_history(history: pd.DataFrame | None, *, near_pct: float = 3.0,
                        lookback: int = 20, stop_lookback: int = 10,
                        max_sessions: int = 15) -> list[dict]:
    """Rolling point-in-time observations; excludes all later candles at each step."""
    if not isinstance(max_sessions, int) or not 1 <= max_sessions <= 100:
        raise ValueError("max_sessions must be 1..100")
    if history is None or not isinstance(history, pd.DataFrame):
        return []
    start = max(lookback + 1, len(history) - max_sessions + 1)
    return [
        classify_opportunity(history.iloc[:end], near_pct=near_pct,
                             lookback=lookback, stop_lookback=stop_lookback)
        for end in range(start, len(history) + 1)
    ]
