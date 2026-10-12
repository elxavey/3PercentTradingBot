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
from tradepilot.risk_diagnostics import diagnose_risk, compare_cost_scenarios, aggregate_risk_diagnostics


def simulate(future, trigger, stop, holding=10, fee=0.0025, slippage=0.001):
    """Pessimistic OHLC execution: stop wins ties and entry-bar ambiguity."""
    if not 0 < stop < trigger or not 0 <= fee < 1 or not 0 <= slippage < 1:
        return {"outcome": "INVALID_PLAN"}
    bars = future.iloc[:holding]
    if bars.empty:
        return {"outcome": "NO_FUTURE_BARS"}
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


def run_backtest(symbols, *, lookback=180, holding=10, stride=10, fetcher=None, progress=None, train_fraction=0.7):
    if not 0.5 <= train_fraction <= 0.9:
        raise ValueError("train_fraction must be 0.5..0.9")
    fetch = fetcher or get_price_history
    trades, audits, failures = [], [], []
    diagnostics = Counter()
    rejection_reasons = Counter()
    state_counts = Counter()
    per_symbol = {}
    evaluated_bars = 0
    signal_events = []
    unique_symbols = list(dict.fromkeys(symbols))
    for symbol_index, symbol in enumerate(unique_symbols, 1):
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
            per_symbol[symbol] = {"bars": len(data), "placeholders_removed": len(removed), "evaluations": 0}
            for end in range(first, len(data)-holding, stride):
                prefix = data.iloc[:end]
                date = prefix.index[-1]
                asof = pd.Timestamp(date)
                if asof.tzinfo is None:
                    asof = asof.tz_localize("UTC")
                # Use the next calendar day at UTC noon, before any following session closes.
                # This prevents using future OHLC while preserving the signal bar as completed.
                asof = asof.tz_convert("UTC").normalize() + pd.Timedelta(days=1, hours=12)
                evaluated_bars += 1
                per_symbol[symbol]["evaluations"] += 1
                for name, fn, confirmed in (
                    ("BREAKOUT", analyze_symbol, "CONFIRMED_RESEARCH"),
                    ("REBOUND", analyze_rebound, "REBOUND_CONFIRMED_RESEARCH")):
                    try:
                        kwargs = {"as_of_utc": asof.to_pydatetime()}
                        if name == "BREAKOUT":
                            kwargs["min_turnover"] = 5_000_000 if symbol.endswith(".MX") else 10_000_000
                        row = fn(symbol, prefix, **kwargs)
                    except Exception as exc:
                        diagnostics[name + ":SIGNAL_ERROR"] += 1
                        failures.append({"symbol": symbol, "reason": "SIGNAL_ERROR", "detail": str(exc)[:100]})
                        continue
                    state = row.get("state", "UNKNOWN")
                    state_counts[name + ":" + state] += 1
                    if state == "REJECT":
                        rejection_reasons[name + ":" + str(row.get("reason", "UNKNOWN"))] += 1
                    if state != confirmed:
                        diagnostics[name + ":NOT_CONFIRMED"] += 1
                        continue
                    diagnostics[name + ":CONFIRMED"] += 1
                    event = {"symbol": symbol, "market": "MX" if symbol.endswith(".MX") else "US",
                             "strategy": name, "signal_date": str(date)[:10], "risk_status": "NOT_EVALUATED"}
                    signal_events.append(event)
                    plan = row.get("trade_plan") or {}
                    trigger, stop = plan.get("entry_reference"), plan.get("stop_reference")
                    close = row.get("reference_close")
                    if not all(isinstance(x, (float, int)) for x in (trigger, stop, close)):
                        event["risk_status"] = "INVALID_PLAN"
                        diagnostics[name + ":INVALID_PLAN"] += 1
                        continue
                    audits.append({"symbol": symbol, "strategy": name, "date": str(date)[:10],
                                   "trigger_below_close": trigger < close, "close": close, "trigger": trigger})
                    risk = diagnose_risk(plan)
                    event["risk_diagnostic"] = risk
                    event["cost_scenarios"] = compare_cost_scenarios(plan)
                    if risk["status"] == "UNAVAILABLE":
                        event["risk_status"] = "INVALID_RISK_DIAGNOSTIC"
                        diagnostics[name + ":INVALID_RISK_DIAGNOSTIC"] += 1
                        continue
                    if risk["status"] == "FAIL":
                        event["risk_status"] = "RISK_BELOW_ONE"
                        diagnostics[name + ":RISK_BELOW_ONE"] += 1
                        continue
                    event["risk_status"] = "RISK_ACCEPTED"
                    diagnostics[name + ":RISK_ACCEPTED"] += 1
                    result = simulate(data.iloc[end:end+holding], trigger, stop, holding=holding)
                    event["outcome"] = result["outcome"]
                    diagnostics[name + ":" + result["outcome"]] += 1
                    trades.append({"symbol": symbol, "market": "MX" if symbol.endswith(".MX") else "US",
                                   "strategy": name, "signal_date": str(date)[:10], **result})
        except Exception as exc:
            failures.append({"symbol": symbol, "reason": "PROCESS_ERROR", "detail": str(exc)[:120]})
        finally:
            if progress:
                progress(symbol_index, len(unique_symbols), symbol, per_symbol.get(symbol, {}).get("evaluations", 0))
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
    dates = sorted(set(e["signal_date"] for e in signal_events))
    cutoff = dates[min(len(dates)-1, max(0, int(len(dates)*train_fraction)-1))] if dates else None
    def split_metrics(period):
        events = [e for e in signal_events if cutoff is not None and
                  ((e["signal_date"] <= cutoff) if period == "development" else (e["signal_date"] > cutoff))]
        executed = [t for t in trades if "net_pct" in t and
                    ((t["signal_date"] <= cutoff) if period == "development" else (t["signal_date"] > cutoff))]
        return {"confirmed_signals": len(events),
                "risk_accepted": sum(e["risk_status"] == "RISK_ACCEPTED" for e in events),
                "executed": len(executed),
                "targets": sum(t["outcome"] == "TARGET" for t in executed),
                "stops": sum(t["outcome"] == "STOP" for t in executed),
                "mean_net_pct": round(sum(t["net_pct"] for t in executed)/len(executed), 4) if executed else None}
    holdout = {"split_method": "CHRONOLOGICAL_SIGNAL_DATES_DESCRIPTIVE_ONLY",
               "cutoff_signal_date": cutoff, "development": split_metrics("development"),
               "holdout": split_metrics("holdout"),
               "warning": "NOT_TRUE_OUT_OF_SAMPLE: no train-only tuning; tickers selected using recent radar."}
    return {"state": "HISTORICAL_RESEARCH_ONLY", "summary": summary,
            "risk_diagnostics_summary": aggregate_risk_diagnostics(signal_events),
            "chronological_split": holdout, "signal_events": signal_events,
            "diagnostics": {"signal_states": dict(state_counts), "rejection_reasons": dict(rejection_reasons),
                            "funnel": dict(diagnostics), "evaluated_bars": evaluated_bars,
                            "by_symbol": per_symbol},
            "entry_audit": {"confirmed_signals": len(audits),
                            "trigger_below_close": sum(x["trigger_below_close"] for x in audits),
                            "examples": audits[:50]}, "trades": trades, "failures": failures,
            "limitations": ["NEXT_SESSION_ENTRY", "STOP_FIRST_IF_AMBIGUOUS",
                            "DESCRIPTIVE_HOLDOUT_NOT_PROVEN_OUT_OF_SAMPLE", "OVERLAPPING_SIGNALS_POSSIBLE",
                            "NO_LIVE_QUOTES", "NO_PROFITABILITY_CLAIM"]}


def main(argv=None):
    p = argparse.ArgumentParser(description="TradePilot offline historical strategy research")
    p.add_argument("--symbols", nargs="*", default=[])
    p.add_argument("--symbols-file", help="Text file with one ticker per line; # comments supported")
    p.add_argument("--max-symbols", type=int, default=250)
    p.add_argument("--lookback", type=int, default=180)
    p.add_argument("--holding", type=int, default=10)
    p.add_argument("--stride", type=int, default=10)
    p.add_argument("--train-fraction", type=float, default=0.7)
    p.add_argument("--output", default=".cache/strategy_validation.json")
    a = p.parse_args(argv)
    if not 1 <= a.max_symbols <= 1000:
        p.error("--max-symbols must be 1..1000")
    if not 0.5 <= a.train_fraction <= 0.9:
        p.error("--train-fraction must be 0.5..0.9")
    if not 30 <= a.lookback <= 500 or not 1 <= a.holding <= 30 or not 1 <= a.stride <= 60:
        p.error("Invalid lookback, holding or stride")
    symbols = list(a.symbols)
    if a.symbols_file:
        symbols.extend(line.strip().upper() for line in Path(a.symbols_file).read_text(encoding="utf-8-sig").splitlines()
                       if line.strip() and not line.lstrip().startswith("#"))
    symbols = list(dict.fromkeys(symbols))[:a.max_symbols]
    if not symbols:
        p.error("Supply --symbols or --symbols-file")
    result = run_backtest(symbols, lookback=a.lookback, holding=a.holding, stride=a.stride,
                          train_fraction=a.train_fraction,
                          progress=lambda i, n, sym, windows: print(f"[{i}/{n}] {sym}: {windows} windows", flush=True))
    path = Path(a.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "risk_diagnostics_summary": result["risk_diagnostics_summary"],
                      "chronological_split": result["chronological_split"],
                      "diagnostics": result["diagnostics"], "entry_audit": result["entry_audit"],
                      "failures": len(result["failures"]), "output": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
