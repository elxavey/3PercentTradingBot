"""Exploratory backtests: never bridge missing exchange sessions with trades/signals."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import pandas as pd

from tradepilot.backtest_validation import validate_history
from tradepilot.backtest_runner import run_backtest, performance_metrics
from tradepilot.historical_simulator import SimulationPolicy


def exploratory_backtest(history, *, symbol: str, market: str,
                         as_of_utc: datetime, simulation_policy: SimulationPolicy,
                         min_sessions: int = 100, max_missing: int = 2,
                         calendar=None) -> dict:
    """Run independently on uninterrupted exchange-session segments.

    No signal, position, holding period, or lookback can cross a missing day.
    Segments shorter than the strategy's warmup simply contribute no trades.
    """
    if not isinstance(max_missing, int) or isinstance(max_missing, bool) or not 0 <= max_missing <= 2:
        raise ValueError("max_missing must be between 0 and 2")
    if not isinstance(simulation_policy, SimulationPolicy):
        raise TypeError("explicit simulation policy required")
    if simulation_policy.fee_rate_per_side <= 0 or simulation_policy.slippage_rate_per_side <= 0:
        raise ValueError("explicit positive fees and slippage required")
    check = validate_history(history, market=market, as_of_utc=as_of_utc,
                             min_sessions=min_sessions, calendar=calendar)
    meta = {k: v for k, v in check.items() if k != "history"}
    if check["state"] == "VALIDATED":
        result = run_backtest(check["history"], symbol=symbol, market=market,
                              simulation_policy=simulation_policy)
        return {"state": "RESEARCH_RESULT", "validation": meta,
                "backtest": result, "excluded_segments": 0, "actionable": False}
    if check["reasons"] != ["MISSING_EXCHANGE_SESSIONS"]:
        return {"state": "REJECT", "reasons": check["reasons"],
                "validation": meta, "actionable": False}
    missing = check["missing_sessions"]
    if check["missing_sessions_count"] > max_missing:
        return {"state": "REJECT", "reasons": ["TOO_MANY_MISSING_SESSIONS"],
                "validation": meta, "actionable": False}
    import exchange_calendars as xcals
    cal = calendar or xcals.get_calendar("XMEX" if market == "MX" else "XNYS")
    from tradepilot.setup_view import completed_history
    completed, _ = completed_history(history, market=market, as_of_utc=as_of_utc, calendar=cal)
    expected = [s.date() for s in cal.sessions_in_range(completed.index[0].date(),
                                                        completed.index[-1].date())]
    missing_set = {pd.Timestamp(d).date() for d in missing}
    if any(expected[i] in missing_set and expected[i + 1] in missing_set
           for i in range(len(expected) - 1)):
        return {"state": "REJECT", "reasons": ["CONSECUTIVE_MISSING_SESSIONS"],
                "validation": meta, "actionable": False}
    boundaries = []
    chunk = []
    for day in expected:
        if day in missing_set:
            if chunk:
                boundaries.append(chunk)
                chunk = []
        else:
            chunk.append(day)
    if chunk:
        boundaries.append(chunk)
    all_trades, signals, excluded, evaluated = [], 0, 0, 0
    limitations = []
    for days in boundaries:
        segment = completed.loc[[pd.Timestamp(d) for d in days]]
        # Replay needs its full warmup; segments without it cannot generate signals.
        if len(segment) < 100:
            excluded += 1
            continue
        result = run_backtest(segment, symbol=symbol, market=market,
                              simulation_policy=simulation_policy)
        all_trades.extend(result["trades"])
        signals += result["confirmed_signal_sessions"]
        evaluated += result["evaluated_sessions"]
        limitations = result["limitations"]
    report = {"symbol": symbol.upper(), "market": market,
              "currency": "MXN" if market == "MX" else "USD",
              "historical_sessions": len(completed),
              "confirmed_signal_sessions": signals, "evaluated_sessions": evaluated,
              "metrics": performance_metrics(all_trades), "trades": all_trades,
              "simulation_policy": asdict(simulation_policy),
              "limitations": list(dict.fromkeys([*limitations,
                  "PARTIAL_HISTORY_SEGMENTED_RESEARCH_ONLY",
                  "TRADES_AND_SIGNALS_NEAR_MISSING_SESSIONS_EXCLUDED"])),
              "research_only": True}
    return {"state": "RESEARCH_RESULT", "validation": {
                **meta, "state": "PARTIAL_HISTORY", "reasons": [],
                "missing_sessions": missing, "segments": len(boundaries),
                "excluded_short_segments": excluded},
            "backtest": report, "excluded_segments": excluded, "actionable": False}
