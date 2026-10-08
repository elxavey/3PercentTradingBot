"""Phase 4.2: deterministic long-only historical trade execution research.

Signals are emitted after a completed session; earliest entry is NEXT open.
No live broker orders, database writes, FX assumptions or portfolio sizing.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import pandas as pd


@dataclass(frozen=True)
class SimulationPolicy:
    target_gross_pct: float = 3.6
    stop_pct: float = 1.8
    max_holding_sessions: int = 5
    fee_rate_per_side: float = 0.0
    slippage_rate_per_side: float = 0.0

    def __post_init__(self):
        for name in ("target_gross_pct", "stop_pct", "fee_rate_per_side", "slippage_rate_per_side"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v):
                raise ValueError(f"invalid {name}")
        if not 0 < self.target_gross_pct <= 100 or not 0 < self.stop_pct < 100:
            raise ValueError("invalid target or stop")
        if (not isinstance(self.max_holding_sessions, int) or isinstance(self.max_holding_sessions, bool)
                or not 1 <= self.max_holding_sessions <= 30):
            raise ValueError("invalid holding sessions")
        if self.fee_rate_per_side < 0 or self.slippage_rate_per_side < 0 or self.fee_rate_per_side + self.slippage_rate_per_side >= 1:
            raise ValueError("invalid transaction costs")


def simulate_trades(history: pd.DataFrame, replay: dict, *,
                    policy: SimulationPolicy | None = None) -> dict:
    """Execute completed-bar historical confirmation events conservatively.

    Assumes a market-on-next-open long entry and fixed entry-relative stop
    and target. Gap-through stop fills at worse open; gap-through target fills
    at target (no favorable price improvement). Same-bar collision uses stop.
    An incomplete final trade is excluded, not marked as closed.
    """
    p = policy or SimulationPolicy()
    if not isinstance(p, SimulationPolicy):
        raise TypeError("policy must be SimulationPolicy")
    if not isinstance(history, pd.DataFrame) or not isinstance(history.index, pd.DatetimeIndex):
        raise ValueError("DatetimeIndex OHLCV required")
    if history.index.hasnans or not history.index.is_unique or not history.index.is_monotonic_increasing:
        raise ValueError("invalid historical index")
    cols = ("Open", "High", "Low", "Close", "Volume")
    if any(col not in history for col in cols):
        raise ValueError("missing OHLCV")
    from tradepilot.technical_setup import derive_levels
    if not history.empty and derive_levels(history, lookback=2, stop_lookback=2)["state"] != "LEVELS_DERIVED":
        raise ValueError("invalid historical OHLCV")
    if not isinstance(replay, dict) or not isinstance(replay.get("events"), list):
        raise ValueError("valid historical replay required")
    events = replay["events"]
    by_session = {}
    for e in events:
        if not isinstance(e, dict) or e.get("confirmation") != "HISTORICAL_FILTERS_PASSED":
            continue
        key = e.get("session")
        if key in by_session:
            raise ValueError("duplicate confirmed session")
        by_session[key] = e
    trades = []
    pending = None
    position = None
    for i, (stamp, bar) in enumerate(history.iterrows()):
        day = stamp.date().isoformat()
        op, hi, lo, cl = (float(bar[k]) for k in ("Open", "High", "Low", "Close"))
        if pending is not None:
            entry = op * (1 + p.slippage_rate_per_side)
            position = {"signal_session": pending, "entry_session": day,
                        "entry_index": i, "entry_price": entry,
                        "stop": entry * (1 - p.stop_pct / 100),
                        "target": entry * (1 + p.target_gross_pct / 100)}
            pending = None
        if position is not None:
            stop, target = position["stop"], position["target"]
            age = i - position["entry_index"] + 1
            reason = None
            if op <= stop:
                raw_exit, reason = op, "STOP_GAP"
            elif op >= target:
                raw_exit, reason = target, "TARGET_GAP_CAPPED"
            elif lo <= stop:
                raw_exit, reason = stop, "STOP" if hi < target else "STOP_FIRST_AMBIGUOUS"
            elif hi >= target:
                raw_exit, reason = target, "TARGET"
            elif age >= p.max_holding_sessions:
                raw_exit, reason = cl, "TIME_EXIT"
            if reason:
                exit_price = raw_exit * (1 - p.slippage_rate_per_side)
                gross_pct = (exit_price / (position["entry_price"] / (1 + p.slippage_rate_per_side)) - 1) * 100
                net_pct = ((exit_price * (1 - p.fee_rate_per_side)) /
                           (position["entry_price"] * (1 + p.fee_rate_per_side)) - 1) * 100
                trades.append({**position, "exit_session": day, "exit_price": exit_price,
                               "holding_sessions": age, "exit_reason": reason,
                               "gross_return_pct_after_slippage": gross_pct,
                               "net_return_pct": net_pct, "simulated": True})
                position = None
        # Never use today's signal for today's entry; do not overlap trades.
        if position is None and pending is None and i + 1 < len(history) and day in by_session:
            pending = day
    return {"trades": trades, "closed_trades": len(trades),
            "open_at_end_excluded": position is not None or pending is not None,
            "research_only": True,
            "limitations": ["NO_FX_OR_TAX_MODEL", "NO_SPREAD_OR_LIQUIDITY_MODEL",
                            "NO_POINT_IN_TIME_UNIVERSE_VERIFICATION",
                            "DAILY_BAR_INTRABAR_ORDER_UNKNOWN"]}
