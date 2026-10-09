"""Historical EOD validation: signal at close, simulated entry on later bars only."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from data_fetcher import get_price_history
from tradepilot.breakout_shortlist_cli import analyze_symbol
from tradepilot.rebound_engine import analyze_rebound, clean_placeholders


def simulate(future, trigger, stop, holding=10, fee=0.0025, slippage=0.001):
    """Pessimistic OHLC execution: stop wins ties and entry-bar ambiguity."""
    if not 0 < stop < trigger or not 0 <= fee < 1 or not 0 <= slippage < 1:
        return {"outcome": "INVALID_PLAN"}
    bars = future.iloc[:holding]
    entry = None
    for i, (_, bar) in enumerate(bars.iterrows()):
        op, hi = float(bar["Open"]), float(bar["High"])
        if op >= trigger:
            entry = op * (1 + slippage)
        elif hi >= trigger:
            entry = trigger * (1 + slippage)
        if entry is not None:
            break
    if entry is None:
        return {"outcome": "NOT_TRIGGERED"}
    target = entry * (1 + fee) * 1.03 / ((1 - fee) * (1 - slippage))
    def net(px):
        return round(100 * (px * (1 - fee) * (1 - slippage) / (entry * (1 + fee)) - 1), 4)
    for j in range(i, len(bars)):
        bar = bars.iloc[j]
        op, lo, hi = (float(bar[k]) for k in ("Open", "Low", "High"))
        if lo <= stop:
            exit_px = min(op, stop) if j > i else stop
            return {"outcome": "STOP", "net_pct": net(exit_px), "entry": round(entry, 4),
                    "exit": round(exit_px, 4), "bars_held": j-i+1, "ambiguous_entry_bar": j == i}
        if hi >= target:
            return {"outcome": "TARGET", "net_pct": net(target), "entry": round(entry, 4),
                    "exit": round(target, 4), "bars_held": j-i+1}
    px = float(bars.iloc[-1]["Close"])
    return {"outcome": "TIMEOUT", "net_pct": net(px), "entry": round(entry, 4),
            "exit": round(px, 4), "bars_held": len(bars)-i}


def run_backtest(symbols, *, lookback=180, holding=10, stride=10, fetcher=None):
    fetch = fetcher or get_price_history
    trades, audits, failures = [], [], []
    for symbol in dict.fromkeys(symbols):
        try:
            data = fetch(symbol, period="2y")
            if fetcher is None and data is not None and len(data) < 300:
                data = get_price_history(symbol, period="2y", force_refresh=True)
            if data is None or data.empty or not isinstance(data.index, pd.DatetimeIndex):
                failures.append({"symbol": symbol, "reason": "NO_VALID_HISTORY"}); continue
            data = data.sort_index()
            data = data.loc[pd.to_datetime(data.index, utc=True).date < datetime.now(timezone.utc).date()]
            data, removed = clean_placeholders(data)
            cols = ["Open", "High", "Low", "Close", "Volume"]
            if len(data) < 90 or not set(cols).issubset(data):
                failures.append({"symbol": symbol, "reason": "INSUFFICIENT_HISTORY"}); continue
            n = data[cols].apply(pd.to_numeric, errors="coerce")
            if n.isna().any().any() or (n[cols[:4]] <= 0).any().any() or (n["Volume"] < 0).any():
                failures.append({"symbol": symbol, "reason": "INVALID_OHLCV"}); continue
            first = max(75, len(data)-lookback-holding)
            for end in range(first, len(data)-holding, stride):
                prefix = data.iloc[:end]
                date = prefix.index[-1]
                asof = pd.Timestamp(date)
                if asof.tzinfo is None:
                    asof = asof.tz_localize("UTC")
                asof = asof.tz_convert("UTC") + pd.Timedelta(days=1)
                for name, fn, confirmed in (
                    ("BREAKOUT", analyze_symbol, "CONFIRMED_RESEARCH"),
                    ("REBOUND", analyze_rebound, "REBOUND_CONFIRMED_RESEARCH")):
                    try:
                        kwargs = {"as_of_utc": asof.to_pydatetime()}
                        if name == "BREAKOUT":
                            kwargs["min_turnover"] = 5_000_000 if symbol.endswith(".MX") else 10_000_000
                        row = fn(symbol, prefix, **kwargs)
                    except Exception as exc:
                        failures.append({"symbol": symbol, "reason": "SIGNAL_ERROR", "detail": str(exc)[:100]})
                        continue
                    if row.get("state") != confirmed:
                        continue
                    plan = row.get("trade_plan") or {}
                    trigger, stop = plan.get("entry_reference"), plan.get("stop_reference")
                    close = row.get("reference_close")
                    if not all(isinstance(x, (float, int)) for x in (trigger, stop, close)):
                        continue
                    audits.append({"symbol": symbol, "strategy": name, "date": str(date)[:10],
                                   "trigger_below_close": trigger < close, "close": close, "trigger": trigger})
                    if (plan.get("reward_risk_net") or 0) < 1:
                        continue
                    result = simulate(data.iloc[end:end+holding], trigger, stop, holding=holding)
                    trades.append({"symbol": symbol, "market": "MX" if symbol.endswith(".MX") else "US",
                                   "strategy": name, "signal_date": str(date)[:10], **result})
        except Exception as exc:
            failures.append({"symbol": symbol, "reason": "PROCESS_ERROR", "detail": str(exc)[:120]})
    summary = {}
    for market in ("MX", "US"):
        for strategy in ("BREAKOUT", "REBOUND"):
            subset = [t for t in trades if t["market"] == market and t["strategy"] == strategy]
            executed = [t for t in subset if "net_pct" in t]
            summary[market+"_"+strategy] = {
                "signals_passing_risk": len(subset), "executed": len(executed),
                "outcomes": dict(Counter(t["outcome"] for t in subset)),
                "target_rate_executed_pct": round(100*sum(t["outcome"]=="TARGET" for t in executed)/len(executed),2) if executed else None,
                "mean_net_pct": round(sum(t["net_pct"] for t in executed)/len(executed),3) if executed else None}
    return {"state": "HISTORICAL_RESEARCH_ONLY", "summary": summary,
            "entry_audit": {"confirmed_signals": len(audits),
                            "trigger_below_close": sum(x["trigger_below_close"] for x in audits),
                            "examples": audits[:50]}, "trades": trades, "failures": failures,
            "limitations": ["NEXT_SESSION_ENTRY", "STOP_FIRST_IF_AMBIGUOUS",
                            "NOT_OUT_OF_SAMPLE", "OVERLAPPING_SIGNALS_POSSIBLE",
                            "NO_LIVE_QUOTES", "NO_PROFITABILITY_CLAIM"]}


def main(argv=None):
    p = argparse.ArgumentParser(description="TradePilot offline historical strategy research")
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--lookback", type=int, default=180)
    p.add_argument("--holding", type=int, default=10)
    p.add_argument("--stride", type=int, default=10)
    p.add_argument("--output", default=".cache/strategy_validation.json")
    a = p.parse_args(argv)
    if not 30 <= a.lookback <= 500 or not 1 <= a.holding <= 30 or not 1 <= a.stride <= 60:
        p.error("Invalid lookback, holding or stride")
    result = run_backtest(a.symbols, lookback=a.lookback, holding=a.holding, stride=a.stride)
    path = Path(a.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "entry_audit": result["entry_audit"],
                      "failures": len(result["failures"]), "output": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
