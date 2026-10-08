"""Phase 3.4 pure, read-only visual and risk presentation helpers."""
from __future__ import annotations

from math import isfinite

import pandas as pd


def chart_candles(history: pd.DataFrame | None, *, max_bars: int = 90) -> pd.DataFrame:
    """Only visualize history already screened as completed by setup_view."""
    if not isinstance(max_bars, int) or not 20 <= max_bars <= 250:
        raise ValueError("max_bars must be between 20 and 250")
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame()
    required = ("Open", "High", "Low", "Close")
    if any(col not in history.columns for col in required):
        return pd.DataFrame()
    data = history.tail(max_bars).loc[:, required].copy()
    if not data.index.is_monotonic_increasing or not data.index.is_unique:
        return pd.DataFrame()
    try:
        data = data.apply(pd.to_numeric, errors="raise")
        values = data.to_numpy(dtype=float)
    except (ValueError, TypeError, OverflowError):
        return pd.DataFrame()
    if not all(isfinite(x) for row in values for x in row):
        return pd.DataFrame()
    if ((data <= 0).any().any()
            or (data["High"] < data[["Open", "Low", "Close"]].max(axis=1)).any()
            or (data["Low"] > data[["Open", "High", "Close"]].min(axis=1)).any()):
        return pd.DataFrame()
    return data


def hypothetical_outcomes(risk: dict) -> dict:
    """Derive total research outcomes from the exact cost-adjusted risk policy."""
    qty = risk.get("quantity_research_only", 0)
    required = ("entry", "stop", "target", "estimated_cash_required",
                "estimated_risk", "net_target_return_pct_estimate")
    if not isinstance(qty, int) or qty < 0 or any(
        not isinstance(risk.get(key), (int, float))
        or not isfinite(risk[key]) for key in required
    ):
        return {"available": False}
    cash = float(risk["estimated_cash_required"])
    # Target gain is derived from cost-adjusted net return on estimated cash.
    gain = cash * float(risk["net_target_return_pct_estimate"]) / 100
    return {"available": True, "quantity": qty, "cash_required": round(cash, 2),
            "risk": round(float(risk["estimated_risk"]), 2),
            "target_gain": round(gain, 2), "currency": risk.get("currency", "UNKNOWN"),
            "net_rr": risk.get("net_reward_risk_estimate")}
