"""Review-only BMV candidate validation with cached 2-year daily histories."""
from __future__ import annotations
import argparse
import csv
import re
import time
from pathlib import Path
import pandas as pd
from data_fetcher import get_price_history

def compact(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())

def main(argv=None):
    p=argparse.ArgumentParser(description="Validate Yahoo BMV candidates; does not enable radar")
    p.add_argument("--input",type=Path,default=Path(".cache/mx_bmv_search_candidates.csv"))
    p.add_argument("--output",type=Path,default=Path(".cache/mx_bmv_candidate_validation.csv"))
    p.add_argument("--min-bars",type=int,default=350)
    p.add_argument("--delay",type=float,default=0.4)
    a=p.parse_args(argv)
    if a.min_bars<30 or a.delay<0:p.error("min-bars >=30 and delay >=0 required")
    with a.input.open(encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    output=[]; cache={}
    for row in rows:
        symbol=row.get("yahoo_candidate","").strip().upper()
        if not symbol:continue
        issuer=row.get("clave_emisora","").strip().upper()
        typ=row.get("yahoo_quote_type","").strip().upper()
        name=row.get("razon_social","")
        yahoo_name=row.get("yahoo_name","")
        prefix=compact(symbol.removesuffix(".MX")).startswith(compact(issuer))
        # Yahoo search names can refer to unrelated issuers; prefix alone is a clue.
        if typ!="EQUITY": status="EXCLUDED_INSTRUMENT"
        elif not prefix:status="MANUAL_ISSUER_REVIEW"
        else:status="SERIES_AND_ISSUER_REVIEW"
        if symbol not in cache and typ=="EQUITY":
            history,timing=get_price_history(symbol,period="2y",return_timing=True)
            if history is None or history.empty:cache[symbol]=(0,0.0,"NO_HISTORY",timing["cache_hit"])
            else:
                vol=pd.to_numeric(history.get("Volume",pd.Series(dtype=float)),errors="coerce").dropna()
                cache[symbol]=(len(history),float(vol.tail(60).median()) if not vol.empty else 0.0,
                               "ENOUGH_BARS" if len(history)>=a.min_bars else "SHORT_HISTORY",
                               timing["cache_hit"])
            if not timing["cache_hit"]:time.sleep(a.delay)
        bars,median_vol,hstatus,cache_hit=cache.get(symbol,(0,0.0,"NOT_CHECKED",False))
        output.append({"clave_emisora":issuer,"razon_social":name,"symbol":symbol,
            "yahoo_name":yahoo_name,"quote_type":typ,"issuer_prefix_match":prefix,
            "mapping_status":status,"history_status":hstatus,"daily_bars":bars,
            "median_volume_last_60":round(median_vol,2),"cache_hit":cache_hit,
            "eligible_for_automatic_radar":False})
        print(f"{issuer:12} {symbol:20} {status:26} {hstatus:15} bars={bars}",flush=True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="",encoding="utf-8-sig") as f:
        fields=list(output[0]) if output else ["symbol"]
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(output)
    print(f"Candidates={len(output)} | equities={sum(x['quote_type']=='EQUITY' for x in output)} | "
          f"enough_history={sum(x['history_status']=='ENOUGH_BARS' for x in output)}")
    print(f"Saved {a.output}; automatic radar inclusion remains disabled pending verification.")
if __name__=="__main__":main()
