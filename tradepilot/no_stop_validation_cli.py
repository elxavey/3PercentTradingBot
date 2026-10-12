"""Historical no-stop research on CONFIRMED signals only.

Signal close is never an entry. Entry is conditional on later OHLC crossing the
research trigger. The full remaining observed history is used without a fixed
holding horizon. No execution or profit guarantee.
"""
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
from tradepilot.historical_v5 import compare_exit_policies, aggregate_comparisons, suppress_overlapping_entries


def follow_without_stop(future, trigger, *, fee=0.0025, slippage=0.001):
    """Return target latency and drawdown from executed (gap-aware) entry.

    Same-bar OHLC ordering is unknown: on the entry bar we count the target
    only if the OPEN is already at or above target; subsequent bars use HIGH.
    Intrabar LOW on entry bar is ambiguous, reported separately.
    """
    if not 0 < trigger or not 0 <= fee < 1 or not 0 <= slippage < 1:
        return {"outcome": "INVALID_PLAN"}
    if future.empty:
        return {"outcome": "NO_FUTURE_DATA", "sessions_observed": 0}
    entry_idx = None
    for i, (_, b) in enumerate(future.iterrows()):
        if float(b["Open"]) >= trigger or float(b["High"]) >= trigger:
            entry_idx = i
            break
    if entry_idx is None:
        return {"outcome": "ENTRY_NOT_TRIGGERED", "sessions_observed": len(future)}
    b = future.iloc[entry_idx]
    entry_price = max(float(b["Open"]), trigger) * (1 + slippage)
    target = entry_price * (1 + fee) * 1.03 / ((1 - fee) * (1 - slippage))
    observed = future.iloc[entry_idx:]
    # Entry bar low may have occurred before entry. Keep it separate.
    first_low = float(observed.iloc[0]["Low"])
    ambiguous_first_bar_dd = round(100 * max(0.0, 1 - first_low / entry_price), 4)
    max_dd = 0.0
    hit_idx = None
    for j, (_, bar) in enumerate(observed.iterrows()):
        if j > 0:
            max_dd = max(max_dd, 100 * max(0.0, 1 - float(bar["Low"]) / entry_price))
        # Cannot infer whether HIGH followed a mid-bar trigger on entry day.
        if (j == 0 and float(bar["Open"]) >= target) or (j > 0 and float(bar["High"]) >= target):
            hit_idx = j
            break
    def net_close(close):
        return round(100 * (close * (1 - fee) * (1 - slippage) /
                            (entry_price * (1 + fee)) - 1), 4)
    base = {"entry_date": str(observed.index[0])[:10],
            "entry_price_including_slippage": round(entry_price, 6),
            "target_price_3pct_net": round(target, 6),
            "sessions_after_signal_to_entry": entry_idx + 1,
            "entry_bar_low_drawdown_ambiguous_pct": ambiguous_first_bar_dd,
            "entry_bar_ohlc_order_unknown": True,
            "sessions_available_after_entry": len(observed),
            "last_observed_date": str(observed.index[-1])[:10]}
    if hit_idx is not None:
        return {**base, "outcome": "TARGET_3PCT_NET",
                "sessions_to_target_including_entry": hit_idx + 1,
                "sessions_after_entry_to_target": hit_idx,
                "target_date": str(observed.index[hit_idx])[:10],
                "max_drawdown_before_target_pct_excluding_entry_bar": round(max_dd, 4),
                "max_drawdown_full_observed_pct_excluding_entry_bar": round(
                    max([max(0.0, 100*(1-float(x)/entry_price)) for x in observed.iloc[1:]["Low"]] or [0.0]),4)}
    return {**base, "outcome": "NOT_REACHED_BY_LAST_AVAILABLE_DATE",
            "sessions_to_target_including_entry": None, "target_date": None,
            "max_drawdown_before_target_pct_excluding_entry_bar": None,
            "max_drawdown_full_observed_pct_excluding_entry_bar": round(max_dd, 4),
            "last_close_net_pct_if_sold": net_close(float(observed.iloc[-1]["Close"]))}


def research(symbols, *, lookback=180, stride=15, fetcher=None, progress=None):
    fetch = fetcher or get_price_history
    records, errors = [], []
    for idx, symbol in enumerate(dict.fromkeys(symbols), 1):
        try:
            data = fetch(symbol, period="5y")
            if fetcher is None:
                # Existing cache may hold a shorter period than requested.
                data = get_price_history(symbol, period="5y", force_refresh=True)
            if data is None or data.empty or not isinstance(data.index, pd.DatetimeIndex):
                errors.append({"symbol":symbol,"reason":"NO_HISTORY"}); continue
            data = data.sort_index()
            data = data.loc[pd.to_datetime(data.index, utc=True).date < datetime.now(timezone.utc).date()]
            data, _ = clean_placeholders(data)
            columns = ("Open","High","Low","Close","Volume")
            if len(data)<90 or not set(columns).issubset(data):
                errors.append({"symbol":symbol,"reason":"INSUFFICIENT_HISTORY"}); continue
            nums = data[list(columns)].apply(pd.to_numeric,errors="coerce")
            if nums.isna().any().any() or (nums[["Open","High","Low","Close"]]<=0).any().any():
                errors.append({"symbol":symbol,"reason":"INVALID_OHLC"}); continue
            # Every signal is scanned against ALL later observed sessions.
            first = max(75, len(data)-lookback)
            for end in range(first,len(data),stride):
                prefix = data.iloc[:end]
                signal_date = prefix.index[-1]
                asof = pd.Timestamp(signal_date)
                if asof.tzinfo is None: asof=asof.tz_localize("UTC")
                asof = asof.tz_convert("UTC").normalize()+pd.Timedelta(days=1,hours=12)
                for strategy,fn,confirmed in (("BREAKOUT",analyze_symbol,"CONFIRMED_RESEARCH"),
                                               ("REBOUND",analyze_rebound,"REBOUND_CONFIRMED_RESEARCH")):
                    try:
                        kwargs={"as_of_utc":asof.to_pydatetime()}
                        if strategy=="BREAKOUT":
                            kwargs["min_turnover"]=5_000_000 if symbol.endswith(".MX") else 10_000_000
                        signal=fn(symbol,prefix,**kwargs)
                        if signal.get("state")!=confirmed: continue
                        plan=signal.get("trade_plan") or {}
                        trigger=plan.get("entry_reference")
                        if not isinstance(trigger,(float,int)) or trigger<=0:
                            result={"outcome":"INVALID_PLAN"}
                        else:
                            result=follow_without_stop(data.iloc[end:],trigger)
                        comparison = compare_exit_policies(data.iloc[end:], trigger, plan.get("stop_reference")) if isinstance(trigger,(float,int)) and trigger>0 else None
                        records.append({"exit_comparison":comparison,"no_stop_exit_date":result.get("target_date"),"symbol":symbol,"market":"MX" if symbol.endswith(".MX") else "US",
                                        "strategy":strategy,"signal_date":str(signal_date)[:10],
                                        "original_risk_gate":plan.get("reward_risk_net"),
                                        **result})
                    except Exception as exc:
                        errors.append({"symbol":symbol,"strategy":strategy,"reason":"SIGNAL_ERROR",
                                       "detail":str(exc)[:120]})
        except Exception as exc:
            errors.append({"symbol":symbol,"reason":"PROCESS_ERROR","detail":str(exc)[:120]})
        finally:
            if progress:progress(idx,len(symbols),symbol)
    summary={}
    for market in ("MX","US"):
        for strategy in ("BREAKOUT","REBOUND"):
            group=[r for r in records if r["market"]==market and r["strategy"]==strategy]
            entries=[r for r in group if r["outcome"] in ("TARGET_3PCT_NET","NOT_REACHED_BY_LAST_AVAILABLE_DATE")]
            hits=[r for r in entries if r["outcome"]=="TARGET_3PCT_NET"]
            summary[market+"_"+strategy]={
                "confirmed_signals":len(group),"entries_triggered":len(entries),
                "targets_hit":len(hits),"not_reached_as_of_last_available_bar":len(entries)-len(hits),
                "entry_not_triggered":sum(r["outcome"]=="ENTRY_NOT_TRIGGERED" for r in group),
                "target_hit_pct_of_triggered_entries":round(100*len(hits)/len(entries),2) if entries else None,
                "median_sessions_to_target":float(pd.Series([r["sessions_to_target_including_entry"] for r in hits]).median()) if hits else None}
    deduplicated = suppress_overlapping_entries(records)
    return {"state":"HISTORICAL_NO_STOP_RESEARCH_ONLY","summary":summary,
            "v5_comparison":aggregate_comparisons(records),
            "v5_nonoverlapping_comparison":aggregate_comparisons(deduplicated),
            "v5_nonoverlapping_signals":len(deduplicated),
            "signals":records,"errors":errors,
            "limitations":["NO_STOP_LOSS_IS_NOT_A_RECOMMENDATION",
                           "RIGHT_CENSORED_RECENT_SIGNALS",
                           "SIGNAL_SELECTION_USES_HISTORICAL_DATA_NOT_POINT_IN_TIME_UNIVERSE",
                           "OVERLAPPING_SIGNALS_NOT_INDEPENDENT",
                           "ENTRY_BAR_LOW_ORDER_UNKNOWN",
                           "EOD_ONLY_INTRADAY_SEQUENCE_UNKNOWN",
                           "NO_FIXED_HOLDING_LIMIT_BUT_ONLY_AVAILABLE_HISTORY",
                           "NO_PROFITABILITY_CLAIM","STOP_ON_ENTRY_BAR_NOT_MODELED_DUE_TO_OHLC_AMBIGUITY",
                           "SAME_BAR_TARGET_STOP_COUNTS_AS_STOP","NONOVERLAP_DESCRIPTIVE_ONLY"]}


def main(argv=None):
    p=argparse.ArgumentParser(description="Confirmed signals, unlimited observed sessions, no stop")
    p.add_argument("--symbols-file",required=True)
    p.add_argument("--max-symbols",type=int,default=100)
    p.add_argument("--lookback",type=int,default=1000)
    p.add_argument("--stride",type=int,default=15)
    p.add_argument("--output",default=".cache/no_stop_validation.json")
    a=p.parse_args(argv)
    if not 1<=a.max_symbols<=1000 or not 90<=a.lookback<=1250 or not 1<=a.stride<=60:
        p.error("Invalid arguments")
    symbols=list(dict.fromkeys(line.strip().upper() for line in Path(a.symbols_file).read_text(encoding="utf-8-sig").splitlines()
                            if line.strip() and not line.lstrip().startswith("#")))[:a.max_symbols]
    result=research(symbols,lookback=a.lookback,stride=a.stride,
                    progress=lambda i,n,s:print(f"[{i}/{n}] {s}",flush=True))
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"summary":result["summary"],"errors":len(result["errors"]),
                      "output":str(out),"v5_comparison":result["v5_comparison"],
                      "v5_nonoverlapping_comparison":result["v5_nonoverlapping_comparison"]},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
