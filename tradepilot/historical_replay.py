"""Phase 4.1: historical signal replay; research only."""
import pandas as pd
from tradepilot.breakout_confirmation import ConfirmationPolicy, confirm_breakout
from tradepilot.opportunity_monitor import classify_opportunity

def replay_signals(history, *, symbol, market, policy=None, near_pct=3.0):
    if market not in ("MX", "US") or not symbol:
        raise ValueError("invalid symbol or market")
    if not isinstance(history, pd.DataFrame):
        raise TypeError("history must be DataFrame")
    if not isinstance(history.index, pd.DatetimeIndex) or not history.index.is_monotonic_increasing or not history.index.is_unique or history.index.hasnans:
        raise ValueError("invalid historical index")
    if not all(x in history.columns for x in ("Open", "High", "Low", "Close", "Volume")):
        raise ValueError("missing OHLCV")
    p = policy or ConfirmationPolicy()
    warmup = max(p.resistance_lookback, p.volume_lookback, p.trend_lookback) + p.persistence_sessions
    events = []
    for end in range(warmup, len(history) + 1):
        prefix = history.iloc[:end]
        state = classify_opportunity(prefix, near_pct=near_pct)
        confirmation = confirm_breakout(prefix, policy=p)
        events.append({"session": prefix.index[-1].date().isoformat(),
                       "symbol": symbol, "market": market, "bars_available": end,
                       "state": state["state"], "distance_pct": state["distance_pct"],
                       "confirmation": confirmation["state"],
                       "reasons": confirmation["reasons"], "actionable": False})
    return {"events": events, "evaluated_sessions": len(events),
            "warmup_sessions": warmup, "research_only": True}
