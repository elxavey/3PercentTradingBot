"""Research-only breakout shortlist from completed daily candles.

No broker orders, no EODHD requests, no invented quotes. Does not claim
a confirmed live breakout or a statistically validated profitable edge.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from math import isfinite

import pandas as pd

from config import BREAKOUT_TEST_SYMBOLS
from data_fetcher import get_price_history
from tradepilot.opportunity_monitor import classify_opportunity
from tradepilot.technical_setup import derive_levels
from tradepilot.holding_sensitivity_cli import exclude_trailing_empty_prices
from tradepilot.breakout_session_quality import assess_daily_sessions
from tradepilot.breakout_trade_plan import build_trade_plan
from tradepilot.rebound_engine import clean_placeholders


def analyze_symbol(symbol, history, *, near_pct=5.0, min_turnover=0.0,
                   as_of_utc=None):
    now = as_of_utc or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("as_of_utc must be timezone-aware")
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return {"symbol": symbol, "state": "REJECT", "reason": "NO_HISTORY"}
    data = history.copy()
    # Exclude UTC-current-date bars: they may be intraday or provider placeholders.
    # The exchange-specific latest completed session is not verified by this CLI.
    if isinstance(data.index, pd.DatetimeIndex):
        dates = pd.to_datetime(data.index, utc=True).date
        data = data.loc[dates < now.date()]
    market = "MX" if symbol.endswith(".MX") else "US"
    data, removed_placeholders = clean_placeholders(data)
    data, excluded_terminal_bars = exclude_trailing_empty_prices(data, as_of_utc=now, market=market)
    if len(data) < 21:
        return {"symbol": symbol, "state": "REJECT", "reason": "INSUFFICIENT_COMPLETED_BARS"}
    quality = assess_daily_sessions(data, market=market, as_of_utc=now)
    if quality["state"] == "REJECT":
        return {"symbol": symbol, "state": "REJECT", "reason": quality["reason"], "session_quality": quality, "removed_empty_price_placeholders": removed_placeholders}
    result = classify_opportunity(data, near_pct=near_pct)
    if result["state"] == "INSUFFICIENT_DATA":
        return {"symbol": symbol, "state": "REJECT", "reason": result["reason"]}
    levels = derive_levels(data.iloc[:-1])
    if levels["state"] != "LEVELS_DERIVED":
        return {"symbol": symbol, "state": "REJECT", "reason": "INVALID_LEVELS"}
    recent = data.tail(20)
    turnover = pd.to_numeric(recent["Close"], errors="coerce") * pd.to_numeric(recent["Volume"], errors="coerce")
    avg_turnover = float(turnover.mean())
    if not isfinite(avg_turnover) or avg_turnover < min_turnover:
        return {"symbol": symbol, "state": "REJECT", "reason": "LOW_OR_INVALID_TURNOVER",
                "avg_turnover_local_currency": avg_turnover if isfinite(avg_turnover) else None, "removed_empty_price_placeholders": removed_placeholders}
    volume = float(data["Volume"].iloc[-1])
    baseline = float(pd.to_numeric(data["Volume"].iloc[-21:-1]).mean())
    relative_volume = volume / baseline if baseline > 0 else 0.0
    closes = pd.to_numeric(data["Close"], errors="coerce")
    sma20 = float(closes.iloc[-20:].mean())
    sma50 = float(closes.iloc[-50:].mean()) if len(closes) >= 50 else None
    trend = bool(sma50 is not None and result["close"] > sma20 > sma50)
    breakout = result["close"] > result["resistance"] * 1.001
    volume_ok = relative_volume >= 1.5
    confirmed = bool(breakout and volume_ok and trend and quality["state"] == "CURRENT")
    state = ("CONFIRMED_RESEARCH" if confirmed else
             "BREAKOUT_PENDING_CONFIRMATION" if result["state"] == "BREAKOUT_CANDIDATE" else
             result["state"])
    checks = {"close_above_buffered_resistance": bool(breakout),
              "relative_volume_at_least_1_5": bool(volume_ok),
              "positive_sma20_sma50_trend": bool(trend),
              "current_completed_session": quality["state"] == "CURRENT"}
    resistance = result["resistance"]
    trigger = resistance * 1.001
    proximity = max(0.0, 1 - abs((resistance * 1.001 / result["close"] - 1) * 100) / near_pct)
    score = round(35 * proximity + 25 * min(relative_volume / 1.5, 1) +
                  20 * int(trend) + 20 * int(breakout), 2)
    plan = build_trade_plan({"reference_close": result["close"], "breakout_trigger": trigger,
                             "structural_stop_reference": levels["structural_stop"]})
    return {"symbol": symbol, "state": state, "trade_plan": plan,
            "session_quality": quality, "relative_volume": round(relative_volume, 3),
            "sma20": round(sma20, 4), "sma50": round(sma50, 4) if sma50 is not None else None,
            "confirmation_checks": checks, "quality_score": score,
            "excluded_terminal_bars": excluded_terminal_bars,
            "removed_empty_price_placeholders": removed_placeholders,
            "session": result["session"], "reference_close": result["close"],
            "resistance": resistance, "breakout_trigger": round(trigger, 4),
            "distance_to_trigger_pct": round(100 * (trigger / result["close"] - 1), 3),
            "avg_turnover_20d_local_currency": round(avg_turnover, 2),
            "structural_stop_reference": levels["structural_stop"],
            "confirmation": "REQUIRES_COMPLETED_CLOSE_ABOVE_RESISTANCE_AND_VOLUME_REVIEW",
            "actionable": False}


def shortlist(symbols, *, fetcher=get_price_history, near_pct=5.0,
              min_turnover_mx=5_000_000, min_turnover_us=10_000_000,
              as_of_utc=None):
    rows = []
    for symbol in dict.fromkeys(symbols):
        try:
            data = fetcher(symbol, period="6mo")
            rows.append(analyze_symbol(
                symbol, data, near_pct=near_pct,
                min_turnover=min_turnover_mx if symbol.endswith(".MX") else min_turnover_us,
                as_of_utc=as_of_utc))
        except Exception as exc:
            rows.append({"symbol": symbol, "state": "ERROR",
                         "reason": type(exc).__name__, "detail": str(exc)[:160]})
    candidates = [r for r in rows if r["state"] in ("APPROACHING", "BREAKOUT_PENDING_CONFIRMATION", "CONFIRMED_RESEARCH") and r["session_quality"]["state"] == "CURRENT"]
    candidates.sort(key=lambda r: (-r["quality_score"], r["symbol"]))
    return {"state": "BREAKOUT_SHORTLIST_RESEARCH", "as_of_utc": (as_of_utc or datetime.now(timezone.utc)).isoformat(),
            "top": candidates[:10], "results": rows,
            "research_only": True, "actionable": False,
            "limitations": ["NO_VERIFIED_LIVE_QUOTES", "HEURISTIC_RANK_NOT_PROBABILITY",
                            "NO_OUT_OF_SAMPLE_EDGE", "NOT_GBM_ACTIONABLE",
                            "CURRENT_UTC_DATE_EXCLUDED_CONSERVATIVELY"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="TradePilot daily breakout watchlist (research only)")
    parser.add_argument("--symbols", nargs="+", default=BREAKOUT_TEST_SYMBOLS)
    parser.add_argument("--near-pct", type=float, default=5.0)
    parser.add_argument("--output", default="breakout_shortlist.json")
    args = parser.parse_args(argv)
    if not 0 < args.near_pct <= 20:
        parser.error("--near-pct must be >0 and <=20")
    report = shortlist(args.symbols, near_pct=args.near_pct)
    from pathlib import Path
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print("Breakout research shortlist (NOT confirmed live trades)")
    for row in report["top"]:
        print(f'{row["symbol"]:16} {row["state"]:20} close={row["reference_close"]:.3f} '
              f'trigger={row["breakout_trigger"]:.3f} distance={row["distance_to_trigger_pct"]:+.2f}% '
              f'bar={row["session"]}')
    print(f'Saved: {args.output} | candidates: {len(report["top"])} | reviewed: {len(report["results"])}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
