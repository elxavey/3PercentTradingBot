"""Batch OHLCV forensic audit: cached vs Yahoo raw/repaired, never alters cache."""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from data_fetcher import _history_cache_path, _normalize_cached_history_index
from tradepilot.breakout_shortlist_cli import analyze_symbol

DEFAULT_SYMBOLS=["FEMSAUBD.MX","GENTERA.MX","CHDRAUIB.MX","AGUA.MX",
                 "AXTELCPO.MX","CTAXTELA.MX","HERDEZ.MX","TEAKCPO.MX",
                 "VASCONI.MX","VINTE.MX"]
FIELDS=["Open","High","Low","Close","Volume"]

def audit_frame(df, *, max_examples=12):
    if df is None or df.empty:
        return {"rows":0,"issues":{"EMPTY_HISTORY":1},"examples":[]}
    issues=Counter(); examples=[]
    missing=[field for field in FIELDS if field not in df.columns]
    if missing:
        return {"rows":len(df),"issues":{"MISSING_COLUMNS":len(missing)},
                "examples":[{"columns":missing}]}
    nums={field:pd.to_numeric(df[field],errors="coerce") for field in FIELDS}
    for i in range(len(df)):
        vals={k:float(v.iloc[i]) for k,v in nums.items()}
        faults=[]
        for key,val in vals.items():
            if not np.isfinite(val):faults.append(f"{key}_NONFINITE")
        if not faults:
            if any(vals[k]<=0 for k in ("Open","High","Low","Close")):faults.append("NONPOSITIVE_PRICE")
            if vals["Volume"]<0:faults.append("NEGATIVE_VOLUME")
            if vals["Volume"]==0:faults.append("ZERO_VOLUME")
            if vals["High"]<max(vals["Open"],vals["Close"],vals["Low"]):faults.append("HIGH_BELOW_OHLC")
            if vals["Low"]>min(vals["Open"],vals["Close"],vals["High"]):faults.append("LOW_ABOVE_OHLC")
        for fault in faults:issues[fault]+=1
        if faults and len(examples)<max_examples:
            examples.append({"date":str(df.index[i])[:10],"issues":faults,
                             "values":{k:round(v,6) if np.isfinite(v) else None for k,v in vals.items()}})
    return {"rows":len(df),"first_date":str(df.index[0])[:10],
            "last_date":str(df.index[-1])[:10],"issues":dict(issues),
            "examples":examples,"last_21_issue_count":sum(
                any((not np.isfinite(float(nums[k].iloc[i]))) for k in FIELDS)
                or float(nums["Volume"].iloc[i])<=0
                or any(float(nums[k].iloc[i])<=0 for k in FIELDS[:4])
                for i in range(max(0,len(df)-21),len(df)))}

def inspect(symbol, *, fetch_fresh=True, repair=False):
    path=_history_cache_path(symbol)
    result={"symbol":symbol,"cache_path":str(path),"cache_exists":path.exists(),"sources":{}}
    if path.exists():
        try:
            df=pd.read_csv(path,index_col=0)
            df=_normalize_cached_history_index(df,symbol)
            result["sources"]["cache"]={"audit":audit_frame(df),
                "radar":analyze_symbol(symbol,df,min_turnover=5_000_000)}
        except Exception as exc:
            result["sources"]["cache"]={"error":f"{type(exc).__name__}: {exc}"[:300]}
    if fetch_fresh:
        for name,fix in (("yahoo_raw",False),("yahoo_repaired",True)):
            if fix and not repair:continue
            try:
                df=yf.Ticker(symbol).history(period="6mo",interval="1d",auto_adjust=True,
                                            repair=fix,keepna=True)
                result["sources"][name]={"audit":audit_frame(df),
                    "radar":analyze_symbol(symbol,df,min_turnover=5_000_000)}
            except Exception as exc:
                result["sources"][name]={"error":f"{type(exc).__name__}: {exc}"[:300]}
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description="Read-only batch OHLCV forensic audit; no EODHD")
    p.add_argument("--symbols",nargs="+",default=DEFAULT_SYMBOLS)
    p.add_argument("--cache-only",action="store_true")
    p.add_argument("--compare-repair",action="store_true")
    p.add_argument("--output",type=Path,default=Path(".cache/ohlcv_audit.json"))
    p.add_argument("--csv",type=Path,default=Path(".cache/ohlcv_audit_summary.csv"))
    a=p.parse_args(argv)
    symbols=list(dict.fromkeys(s.upper() for s in a.symbols))
    report={"created_utc":datetime.now(timezone.utc).isoformat(),"symbols":symbols,
            "read_only":True,"repair_comparison_only":a.compare_repair,
            "results":[]}
    summary=[]
    for i,symbol in enumerate(symbols,1):
        result=inspect(symbol,fetch_fresh=not a.cache_only,repair=a.compare_repair)
        report["results"].append(result)
        for source,item in result["sources"].items():
            audit=item.get("audit",{})
            radar=item.get("radar",{})
            summary.append({"symbol":symbol,"source":source,"rows":audit.get("rows",0),
                            "first_date":audit.get("first_date",""),"last_date":audit.get("last_date",""),
                            "issues":json.dumps(audit.get("issues",{})),
                            "last_21_issue_count":audit.get("last_21_issue_count",""),
                            "radar_state":radar.get("state","ERROR"),
                            "radar_reason":radar.get("reason",""),
                            "turnover":radar.get("avg_turnover_local_currency",
                                              radar.get("avg_turnover_20d_local_currency","")),
                            "error":item.get("error","")})
        print(f"[{i}/{len(symbols)}] {symbol}: "+
              " | ".join(f"{src}={item.get('radar',{}).get('reason',item.get('radar',{}).get('state',item.get('error','ERROR')))}"
                       for src,item in result["sources"].items()),flush=True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    a.csv.parent.mkdir(parents=True,exist_ok=True)
    with a.csv.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["symbol","source","rows","first_date","last_date",
            "issues","last_21_issue_count","radar_state","radar_reason","turnover","error"])
        writer.writeheader();writer.writerows(summary)
    print(f"Saved {a.output} and {a.csv}. No cache or trading rules modified.")
    return 0
if __name__=="__main__":raise SystemExit(main())
