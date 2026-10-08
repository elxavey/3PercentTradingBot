"""Phase 3.6: conservative completed-session breakout evidence (research only).

No live prices, orders, DB writes, scheduler changes or forward-looking bars.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd

from tradepilot.technical_setup import derive_levels


@dataclass(frozen=True)
class ConfirmationPolicy:
    resistance_lookback: int = 20
    volume_lookback: int = 20
    trend_lookback: int = 20
    persistence_sessions: int = 2
    minimum_volume_ratio: float = 1.2
    minimum_breakout_pct: float = 0.1

    def __post_init__(self):
        if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 2 for x in
                   (self.resistance_lookback, self.volume_lookback,
                    self.trend_lookback, self.persistence_sessions)):
            raise ValueError("lookbacks and persistence must be integers >= 2")
        if self.persistence_sessions > self.resistance_lookback:
            raise ValueError("persistence exceeds resistance lookback")
        if (not isinstance(self.minimum_volume_ratio, (int, float))
                or not isfinite(self.minimum_volume_ratio)
                or self.minimum_volume_ratio <= 0):
            raise ValueError("invalid volume ratio")
        if (not isinstance(self.minimum_breakout_pct, (int, float))
                or not isfinite(self.minimum_breakout_pct)
                or not 0 <= self.minimum_breakout_pct <= 20):
            raise ValueError("invalid breakout percentage")


def confirm_breakout(history: pd.DataFrame | None,
                     *, policy: ConfirmationPolicy | None = None) -> dict:
    """Evaluate latest completed closes versus a fixed *prior* resistance.

    Resistance is derived from bars BEFORE the persistence window. Volume
    baseline and trend SMA also use earlier bars; latest data never sets its
    own reference thresholds. A PASS is historical evidence, not a trade.
    """
    p = policy or ConfirmationPolicy()
    if not isinstance(p, ConfirmationPolicy):
        raise TypeError("policy must be ConfirmationPolicy")
    base = {"state": "INSUFFICIENT_DATA", "actionable": False,
            "reasons": ["INSUFFICIENT_COMPLETED_HISTORY"],
            "volume_ratio": None, "trend_sma": None,
            "resistance": None, "confirmed_closes": 0}
    required = max(p.resistance_lookback + p.persistence_sessions,
                   p.volume_lookback + p.persistence_sessions,
                   p.trend_lookback + p.persistence_sessions)
    if history is None or not isinstance(history, pd.DataFrame) or len(history) < required:
        return base
    validated = derive_levels(history, lookback=required,
                              stop_lookback=min(10, required))
    if validated.get("state") != "LEVELS_DERIVED":
        return {**base, "reasons": validated.get("reasons", ["INVALID_HISTORY"])}
    prior = history.iloc[:-p.persistence_sessions]
    recent = history.iloc[-p.persistence_sessions:]
    resistance = float(prior["High"].tail(p.resistance_lookback).max())
    sma = float(prior["Close"].tail(p.trend_lookback).mean())
    average_volume = float(prior["Volume"].tail(p.volume_lookback).mean())
    latest_close = float(recent["Close"].iloc[-1])
    latest_volume = float(recent["Volume"].iloc[-1])
    if average_volume <= 0:
        return {**base, "reasons": ["ZERO_BASELINE_VOLUME"]}
    ratio = latest_volume / average_volume
    threshold = resistance * (1 + p.minimum_breakout_pct / 100)
    closes_above = int((recent["Close"] > threshold).sum())
    checks = {
        "persistence": bool((recent["Close"] > threshold).all()),
        "volume": ratio >= p.minimum_volume_ratio,
        "trend": latest_close > sma and sma > float(
            prior["Close"].iloc[-p.trend_lookback]
        ),
    }
    failed = [f"{name.upper()}_NOT_CONFIRMED" for name, passed in checks.items()
              if not passed]
    return {
        "state": "HISTORICAL_FILTERS_PASSED" if not failed else "FILTERS_NOT_MET",
        "actionable": False,
        "reasons": failed or ["HISTORICAL_EVIDENCE_ONLY_NOT_LIVE_SIGNAL"],
        "checks": checks, "confirmed_closes": closes_above,
        "required_closes": p.persistence_sessions,
        "resistance": round(resistance, 4), "trend_sma": round(sma, 4),
        "volume_ratio": round(ratio, 3), "latest_close": latest_close,
        "session": str(history.index[-1])[:10],
        "minimum_breakout_pct": p.minimum_breakout_pct,
    }
