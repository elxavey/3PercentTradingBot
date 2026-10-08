"""Phase 3.2: deterministic completed-daily-bar breakout research levels.

Uses only bars provided to the function; never fetches market data, writes
state or treats daily-session freshness as a verified intraday quote.
"""
from __future__ import annotations

from math import isfinite
import pandas as pd

from tradepilot.trade_setup import RiskPolicy, evaluate_setup


def derive_levels(history: pd.DataFrame, *, lookback: int = 20,
                  stop_lookback: int = 10, breakout_buffer: float = 0.001,
                  stop_buffer: float = 0.001, target_r: float = 2.0) -> dict:
    """Plan for a *future* breakout, using completed historical candles only.

    All supplied rows must be confirmed completed. Last candle is included
    in structure calculation; no assumption of an actual breakout/fill.
    """
    if not isinstance(lookback, int) or not isinstance(stop_lookback, int):
        raise ValueError("lookback lengths must be integers")
    if lookback < 2 or stop_lookback < 2 or stop_lookback > lookback:
        raise ValueError("invalid lookback lengths")
    if not all(isinstance(x, (int, float)) and isfinite(x) for x in
               (breakout_buffer, stop_buffer, target_r)):
        raise ValueError("buffers and target_r must be finite")
    if breakout_buffer < 0 or not 0 <= stop_buffer < 1 or target_r <= 0:
        raise ValueError("invalid breakout/stop buffers or target multiple")
    if not isinstance(history, pd.DataFrame) or history.empty:
        return {"state": "WAIT", "reasons": ["MISSING_COMPLETED_HISTORY"]}
    columns = ("Open", "High", "Low", "Close", "Volume")
    if any(column not in history.columns for column in columns):
        return {"state": "WAIT", "reasons": ["MISSING_OHLCV_COLUMNS"]}
    if len(history) < lookback:
        return {"state": "WAIT", "reasons": ["INSUFFICIENT_COMPLETED_BARS"]}
    data = history.loc[:, columns].copy()
    try:
        data = data.apply(pd.to_numeric, errors="raise")
    except (ValueError, TypeError):
        return {"state": "WAIT", "reasons": ["INVALID_OHLCV"]}
    values = data.to_numpy(dtype=float)
    if not pd.Index(data.index).is_monotonic_increasing or not data.index.is_unique:
        return {"state": "WAIT", "reasons": ["UNORDERED_OR_DUPLICATE_BARS"]}
    if not pd.notna(values).all() or not all(isfinite(x) for row in values for x in row):
        return {"state": "WAIT", "reasons": ["INVALID_OHLCV"]}
    # Float-adjusted Yahoo OHLC values may differ at machine precision.
    # Relative tolerance 1e-12; do not round or mutate source prices.
    tolerance = data[["Open", "High", "Low", "Close"]].abs().max(axis=1) * 1e-12
    if ((data[["Open", "High", "Low", "Close"]] <= 0).any().any()
            or (data["Volume"] < 0).any()
            or (data["High"] + tolerance < data[["Open", "Low", "Close"]].max(axis=1)).any()
            or (data["Low"] - tolerance > data[["Open", "High", "Close"]].min(axis=1)).any()):
        return {"state": "WAIT", "reasons": ["INVALID_OHLCV"]}
    recent = data.tail(lookback)
    resistance = float(recent["High"].max())
    support = float(recent["Low"].min())
    structural_stop = float(recent["Low"].tail(stop_lookback).min())
    entry = resistance * (1 + breakout_buffer)
    stop = structural_stop * (1 - stop_buffer)
    if not 0 < stop < entry:
        return {"state": "WAIT", "reasons": ["INVALID_STRUCTURAL_LEVELS"]}
    target = entry + target_r * (entry - stop)
    return {
        "state": "LEVELS_DERIVED", "reasons": ["FUTURE_BREAKOUT_NOT_CONFIRMED"],
        "support": support, "resistance": resistance,
        "entry_trigger": entry, "structural_stop": stop, "target": target,
        "lookback_bars": lookback, "stop_lookback_bars": stop_lookback,
        "last_completed_bar": str(data.index[-1]),
        "method": "COMPLETED_BAR_RESISTANCE_BREAKOUT_V1",
    }


def research_breakout(*, symbol: str, market: str, history: pd.DataFrame,
                      policy: RiskPolicy, **level_kwargs) -> dict:
    """Link structural levels to Phase 3.1 without asserting a live trigger."""
    levels = derive_levels(history, **level_kwargs)
    if levels["state"] != "LEVELS_DERIVED":
        return {**levels, "symbol": symbol, "market": market, "actionable": False}
    risk = evaluate_setup(
        symbol=symbol, market=market, entry=levels["entry_trigger"],
        stop=levels["structural_stop"], target=levels["target"],
        policy=policy, quote_freshness="UNKNOWN",
        quote_timestamp_verified=False, instrument_verified=False,
        currency_conversion_verified=False,
    )
    return {**levels, "risk": risk, "state": "WAIT",
            "reasons": ["FUTURE_BREAKOUT_NOT_CONFIRMED",
                        "LIVE_QUOTE_NOT_VERIFIED"], "actionable": False}
