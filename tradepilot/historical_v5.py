"""Comparable historical exit policies, with conservative OHLC ordering.

All scenarios share the same conditional entry and entry price. Stops are
simulated only after entry; entry-day low is ambiguous and not used as a stop.
A same-day target/stop collision after entry is counted as STOP.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from statistics import median

def compare_exit_policies(future, trigger, structural_stop, *, fee=.0025, slippage=.001):
    if future.empty or not trigger or trigger <= 0:
        return {k:{"outcome":"INVALID_OR_NO_FUTURE"} for k in ("NO_STOP","FIXED_3PCT","STRUCTURAL")}
    idx=next((i for i,(_,b) in enumerate(future.iterrows())
              if float(b["Open"])>=trigger or float(b["High"])>=trigger),None)
    if idx is None:
        return {k:{"outcome":"ENTRY_NOT_TRIGGERED"} for k in ("NO_STOP","FIXED_3PCT","STRUCTURAL")}
    bars=future.iloc[idx:]
    entry=max(float(bars.iloc[0]["Open"]),trigger)*(1+slippage)
    buy=entry*(1+fee)
    sell_factor=(1-fee)*(1-slippage)
    target=buy*1.03/sell_factor
    fixed_stop=entry*.97
    stops={"NO_STOP":None,"FIXED_3PCT":fixed_stop,
           "STRUCTURAL":float(structural_stop) if structural_stop and 0<float(structural_stop)<entry else None}
    out={}
    for policy,stop in stops.items():
        if policy=="STRUCTURAL" and stop is None:
            out[policy]={"outcome":"INVALID_STRUCTURAL_STOP"};continue
        maximum_dd=0.
        outcome=None
        for j,(_,bar) in enumerate(bars.iterrows()):
            op,hi,lo=(float(bar[k]) for k in ("Open","High","Low"))
            if j>0:
                maximum_dd=max(maximum_dd,max(0.,100*(1-lo/entry)))
            # On entry bar, only an opening gap can guarantee target hit.
            hit_target=(op>=target if j==0 else hi>=target)
            # Entry-bar low may have occurred before the entry trigger.
            hit_stop=(j>0 and stop is not None and lo<=stop)
            if hit_stop:
                exit_price=min(op,stop) if op<stop else stop
                outcome="STOP"
            elif hit_target:
                exit_price=target
                outcome="TARGET"
            if outcome:
                out[policy]={"outcome":outcome,"sessions_held":j+1,
                             "net_pct":round(100*(exit_price*sell_factor/buy-1),4),
                             "max_drawdown_before_exit_pct_excluding_entry_bar":round(maximum_dd,4)}
                break
        if outcome is None:
            out[policy]={"outcome":"OPEN_AT_LAST_BAR","sessions_held":len(bars),
                         "net_pct_if_closed":round(100*(float(bars.iloc[-1]["Close"])*sell_factor/buy-1),4),
                         "max_drawdown_before_exit_pct_excluding_entry_bar":round(maximum_dd,4)}
    return out

def aggregate_comparisons(records):
    groups=defaultdict(list)
    for r in records:
        groups["ALL"].append(r)
        groups[r["market"]+"_"+r["strategy"]].append(r)
        groups[r["signal_date"][:4]].append(r)
    output={}
    for key,rows in sorted(groups.items()):
        by_policy={}
        for policy in ("NO_STOP","FIXED_3PCT","STRUCTURAL"):
            values=[r["exit_comparison"][policy] for r in rows if "exit_comparison" in r]
            entered=[v for v in values if v["outcome"] in ("TARGET","STOP","OPEN_AT_LAST_BAR")]
            targets=[v for v in entered if v["outcome"]=="TARGET"]
            by_policy[policy]={"entries":len(entered),"targets":len(targets),
                "stops":sum(v["outcome"]=="STOP" for v in entered),
                "still_open":sum(v["outcome"]=="OPEN_AT_LAST_BAR" for v in entered),
                "target_pct_of_entries":round(100*len(targets)/len(entered),2) if entered else None,
                "median_sessions_to_target":median([v["sessions_held"] for v in targets]) if targets else None}
        output[key]={"signals":len(rows),"policies":by_policy}
    return output

def suppress_overlapping_entries(records):
    """Descriptive non-overlap: earliest signal wins per ticker+strategy until exit.

    Uses each NO_STOP exit date as a conservative proxy for occupancy. If a
    target was never reached, the position remains occupied to last data.
    """
    kept=[];last_occupied={}
    for r in sorted(records,key=lambda x:(x["signal_date"],x["symbol"],x["strategy"])):
        key=(r["symbol"],r["strategy"])
        if r["signal_date"]<=last_occupied.get(key,""):
            continue
        kept.append(r)
        last_occupied[key]=r.get("no_stop_exit_date") or r.get("last_observed_date") or r["signal_date"]
    return kept
