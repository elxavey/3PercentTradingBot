"""Phase 4.3: reproducible single-symbol historical backtest research.

Metrics are trade-level, NOT portfolio equity or investable MXN returns.
No FX, taxes, capital sizing, survivorship correction or real orders.
"""
from __future__ import annotations

from dataclasses import asdict
from math import isfinite
import pandas as pd

from tradepilot.breakout_confirmation import ConfirmationPolicy
from tradepilot.historical_replay import replay_signals
from tradepilot.historical_simulator import SimulationPolicy, simulate_trades


def performance_metrics(trades: list[dict]) -> dict:
    """Closed-trade statistics; hypothetical sequential full reinvestment only."""
    if not isinstance(trades, list):
        raise TypeError("trades must be list")
    returns = []
    durations = []
    for trade in trades:
        if not isinstance(trade, dict) or not trade.get("simulated"):
            raise ValueError("only simulated closed trades accepted")
        value = trade.get("net_return_pct")
        age = trade.get("holding_sessions")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not isfinite(value) or value <= -100
                or isinstance(age, bool) or not isinstance(age, int) or age < 1):
            raise ValueError("invalid closed trade")
        returns.append(float(value))
        durations.append(age)
    n = len(returns)
    if not n:
        return {"closed_trades": 0, "wins": 0, "losses": 0, "breakeven": 0,
                "win_rate_pct": None, "average_net_return_pct": None,
                "average_win_pct": None, "average_loss_pct": None,
                "average_holding_sessions": None, "compounded_net_return_pct": None,
                "max_closed_trade_drawdown_pct": None, "profit_factor": None}
    wins = [v for v in returns if v > 0]
    losses = [v for v in returns if v < 0]
    equity, peak, max_dd = 1.0, 1.0, 0.0
    for value in returns:
        equity *= 1 + value / 100
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
    gain = sum(wins)
    loss = -sum(losses)
    return {
        "closed_trades": n, "wins": len(wins), "losses": len(losses),
        "breakeven": n - len(wins) - len(losses),
        "win_rate_pct": round(len(wins) / n * 100, 4),
        "average_net_return_pct": round(sum(returns) / n, 4),
        "average_win_pct": round(sum(wins) / len(wins), 4) if wins else None,
        "average_loss_pct": round(sum(losses) / len(losses), 4) if losses else None,
        "average_holding_sessions": round(sum(durations) / n, 4),
        "compounded_net_return_pct": round((equity - 1) * 100, 4),
        "max_closed_trade_drawdown_pct": round(max_dd, 4),
        "profit_factor": round(gain / loss, 4) if loss > 0 else None,
    }


def run_backtest(history: pd.DataFrame, *, symbol: str, market: str,
                 confirmation_policy: ConfirmationPolicy | None = None,
                 simulation_policy: SimulationPolicy | None = None) -> dict:
    """Use the same point-in-time replay and next-open simulation functions."""
    if not isinstance(symbol, str) or not symbol.strip() or market not in ("MX", "US"):
        raise ValueError("symbol and market required")
    if not isinstance(history, pd.DataFrame) or not isinstance(history.index, pd.DatetimeIndex):
        raise ValueError("DatetimeIndex OHLCV required")
    # Do not mutate caller's data. Caller must verify completed exchange sessions.
    replay = replay_signals(history, symbol=symbol, market=market,
                            policy=confirmation_policy)
    simulated = simulate_trades(history, replay, policy=simulation_policy)
    return {
        "symbol": symbol.strip().upper(), "market": market,
        "currency": "MXN" if market == "MX" else "USD",
        "first_session": history.index[0].date().isoformat() if len(history) else None,
        "last_session": history.index[-1].date().isoformat() if len(history) else None,
        "historical_sessions": len(history),
        "evaluated_sessions": replay["evaluated_sessions"],
        "confirmed_signal_sessions": sum(
            e["confirmation"] == "HISTORICAL_FILTERS_PASSED" for e in replay["events"]),
        "simulation_policy": asdict(simulation_policy or SimulationPolicy()),
        "confirmation_policy": asdict(confirmation_policy or ConfirmationPolicy()),
        "metrics": performance_metrics(simulated["trades"]),
        "trades": simulated["trades"],
        "open_at_end_excluded": simulated["open_at_end_excluded"],
        "research_only": True, "actionable": False,
        "limitations": [
            "HISTORY_COMPLETENESS_AND_EXCHANGE_SESSIONS_NOT_INDEPENDENTLY_VERIFIED",
            "HISTORICAL_UNIVERSE_AND_DELISTINGS_NOT_VERIFIED",
            "NO_OUT_OF_SAMPLE_VALIDATION",
            "NO_PORTFOLIO_POSITION_SIZING_OR_CASH_CONSTRAINTS",
            "COMPOUNDING_ASSUMES_SEQUENTIAL_FULL_REINVESTMENT_NOT_REAL_PORTFOLIO",
            *simulated["limitations"],
        ],
    }
