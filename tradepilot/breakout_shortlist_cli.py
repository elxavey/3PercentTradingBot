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
    if len(data) < 21:
        return {"symbol": symbol, "state": "REJECT", "reason": "INSUFFICIENT_COMPLETED_BARS"}
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
                "avg_turnover_local_currency": avg_turnover if isfinite(avg_turnover) else None}
    resistance = result["resistance"]
    trigger = resistance * 1.001
    return {"symbol": symbol, "state": result["state"],
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
    candidates = [r for r in rows if r["state"] in ("APPROACHING", "BREAKOUT_CANDIDATE")]
    candidates.sort(key=lambda r: (r["state"] != "APPROACHING",
                                   abs(r["distance_to_trigger_pct"]), r["symbol"]))
    return {"state": "BREAKOUT_SHORTLIST_RESEARCH", "as_of_utc": (as_of_utc or datetime.now(timezone.utc)).isoformat(),
            "top": candidates[:10], "results": rows,
            "research_only": True, "actionable": False,
            "limitations": ["NO_VERIFIED_LIVE_QUOTES", "NO_VOLUME_CONFIRMATION",
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
