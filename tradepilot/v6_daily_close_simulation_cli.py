"""TradePilot daily-close dry run from ACTUAL scanner-exported candidates.

Never manufactures symbols, quotes, strategies or signals. Scanner is the sole
candidate selector; this module validates its exported snapshot and reports it.
A date mismatch or missing data fails closed, not silently replaced by old bars.
"""
import argparse
import csv
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from tradepilot.v6_stop_target_cli import write_csv

COLUMNS=("rank","symbol","market","strategy","signal_status","reference_date",
         "close","currency","opportunity_score","entry","target","stop",
         "financial_status","financial_score","classification","reason")
REQUIRED=("symbol","market","strategy","signal_status","reference_date","close",
          "currency","opportunity_score","entry","target","stop")
ALLOWED_STATUSES=("WATCHING","CONFIRMED","READY","REJECT")
ALLOWED_MARKETS=("MX","US")


def number(value,name):
    try:
        result=float(value)
        if not math.isfinite(result):
            raise ValueError()
        return result
    except (TypeError,ValueError):
        raise ValueError(f"Invalid {name}: {value!r}")


def simulate(candidates,as_of,financial=(),top_per_market=3):
    day=date.fromisoformat(as_of)
    if top_per_market<1:
        raise ValueError("top_per_market must be positive")
    fin={}
    for item in financial:
        key=(item.get("symbol","").upper(),item.get("market",""))
        if key in fin:
            raise ValueError(f"Duplicate financial score for {key}")
        fin[key]=item
    seen=set()
    evaluated=[]
    for index,row in enumerate(candidates,2):
        for field in REQUIRED:
            if not str(row.get(field,"")).strip():
                raise ValueError(f"Scanner row {index}: missing {field}")
        symbol=row["symbol"].strip().upper()
        market=row["market"].strip().upper()
        if market not in ALLOWED_MARKETS:
            raise ValueError(f"Scanner row {index}: invalid market")
        strategy=row["strategy"].strip()
        status=row["signal_status"].strip().upper()
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Scanner row {index}: invalid signal status")
        bar=date.fromisoformat(row["reference_date"])
        if bar>day:
            raise ValueError(f"Scanner row {index}: future bar")
        key=(market,symbol,strategy)
        if key in seen:
            raise ValueError(f"Duplicate scanner setup: {key}")
        seen.add(key)
        close=number(row["close"],"close")
        entry=number(row["entry"],"entry")
        target=number(row["target"],"target")
        stop=number(row["stop"],"stop")
        score=number(row["opportunity_score"],"opportunity_score")
        if close<=0 or entry<=0 or target<=0 or stop<=0:
            raise ValueError("Prices must be positive")
        if not 0<=score<=100:
            raise ValueError("Opportunity score must be 0..100")
        if not stop<entry<target:
            raise ValueError(f"Invalid long-side stop/entry/target for {symbol}")
        f=fin.get((symbol,market))
        fstatus=f.get("quality_status","") if f else "NOT_EVALUATED"
        fscore=f.get("quality_score","") if f else ""
        if fstatus!="EXPERIMENTAL_COMPLETE":
            fscore=""
        if bar!=day:
            classification="STALE_BAR"
            reason=f"Last bar {bar.isoformat()} is not requested close {as_of}"
        elif status=="REJECT":
            classification="REJECT"
            reason="Scanner rejected setup"
        elif status in ("WATCHING",):
            classification="WATCH"
            reason="Scanner has not confirmed entry"
        else:
            classification="CANDIDATE"
            reason="Scanner-confirmed setup; financial evidence informational only"
        evaluated.append(dict(rank="",symbol=symbol,market=market,strategy=strategy,
            signal_status=status,reference_date=bar.isoformat(),close=close,
            currency=row["currency"],opportunity_score=score,entry=entry,
            target=target,stop=stop,financial_status=fstatus,financial_score=fscore,
            classification=classification,reason=reason))
    selected=[]
    for market in ALLOWED_MARKETS:
        eligible=sorted((r for r in evaluated if r["market"]==market
                         and r["classification"]=="CANDIDATE"),
                        key=lambda r:(-r["opportunity_score"],r["symbol"],r["strategy"]))
        for rank,item in enumerate(eligible[:top_per_market],1):
            item["rank"]=rank
            selected.append(item)
    summary=dict(as_of=as_of,scanner_rows=len(candidates),
        eligible=len([r for r in evaluated if r["classification"]=="CANDIDATE"]),
        selected=len(selected),by_market=dict(Counter(r["market"] for r in selected)),
        classifications=dict(Counter(r["classification"] for r in evaluated)),
        status="NO_VALID_CANDIDATES" if not selected else "RESEARCH_ONLY",
        source="Scanner-exported local CSV; no manual ticker selection",
        financial_policy="Informational; no retrospective financial score applied to live signals",
        limitations=["Dry run only; scanner CSV must be generated from the actual close",
                     "No broker mapping, transaction cost validation, or order execution",
                     "Opportunity score is a heuristic, not probability",
                     "No current market data is fetched by this report"])
    return evaluated,selected,summary


def read(path):
    with Path(path).open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main(argv=None):
    parser=argparse.ArgumentParser(description="Daily-close simulation from real TradePilot scanner exports")
    parser.add_argument("--scanner",required=True,help="Actual scanner export CSV using REQUIRED columns")
    parser.add_argument("--as-of",required=True,help="Target close date YYYY-MM-DD")
    parser.add_argument("--financial",help="Optional financial quality export; matching symbol+market only")
    parser.add_argument("--top",type=int,default=3)
    parser.add_argument("--prefix",default=".cache/v6_daily_close")
    args=parser.parse_args(argv)
    rows,selected,summary=simulate(read(args.scanner),args.as_of,
        read(args.financial) if args.financial else [],args.top)
    write_csv(args.prefix+"_evaluated.csv",rows,COLUMNS)
    write_csv(args.prefix+"_selected.csv",selected,COLUMNS)
    path=Path(args.prefix+"_summary.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Daily close {args.as_of}: {summary['scanner_rows']} scanner setups, "
          f"{summary['eligible']} eligible, {summary['selected']} selected")
    for r in selected:
        print(f"  {r['market']} #{r['rank']} {r['symbol']} {r['strategy']} "
              f"score={r['opportunity_score']} entry={r['entry']} target={r['target']} stop={r['stop']}")
    if not selected:
        print("ABSTAIN: no eligible current-close setups; no symbols invented")
    print("Dry run only; no orders sent")


if __name__=="__main__":
    main()
