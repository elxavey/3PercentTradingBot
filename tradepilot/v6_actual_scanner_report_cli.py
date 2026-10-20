"""Read-only actual scanner-run report. No manually chosen tickers or fake trade setups."""
import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone, date, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from tradepilot.v6_stop_target_cli import write_csv

COLUMNS=("rank","symbol","exchange_code","currency","opportunity_score",
         "quality_pass","price","price_source","observed_at_utc","scan_run_id",
         "scan_status","run_finished_at_utc","freshness","setup_status",
         "entry","target","stop","reason")


def _db(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True)


def _date(value):
    if not value:
        return None
    try:
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError,TypeError):
        return None


def report(db_path,as_of,limit=3,run_id=None):
    requested=date.fromisoformat(as_of)
    if limit<1:
        raise ValueError("limit must be positive")
    with closing(_db(db_path)) as conn:
        conn.row_factory=sqlite3.Row
        if run_id is None:
            run=conn.execute("SELECT * FROM scan_runs WHERE status='SUCCEEDED' ORDER BY finished_at_utc DESC, id DESC LIMIT 1").fetchone()
        else:
            run=conn.execute("SELECT * FROM scan_runs WHERE id=?",(run_id,)).fetchone()
        if run is None:
            return [],dict(as_of=as_of,status="NO_SCAN_RUN",source="scanner SQLite read-only",
                           selected=0,notes=["No matching scan run"])
        run=dict(run)
        candidates=[dict(r) for r in conn.execute(
            "SELECT * FROM scan_candidates WHERE scan_run_id=?",
            (run["id"],))]
    finish=_date(run.get("finished_at_utc"))
    run_day=finish.date() if finish else None
    # Date of run is a UTC day, not proof of an exchange close or quote date.
    freshness="RUN_UTC_DATE_MATCH" if run_day==requested else "STALE_OR_UNDATED_RUN"
    eligible=[]
    errors=Counter()
    # Conservative weekday regular-session boundaries, including DST via zoneinfo.
    # A completed scan after close is necessary, not sufficient, to certify EOD bars.
    close_windows={"US":("America/New_York",time(16,0)),
                   "MX":("America/Mexico_City",time(15,0))}
    for row in candidates:
        try:
            import math
            score=float(row["opportunity_score"])
            price=float(row["price"])
            if not math.isfinite(score) or not 0<=score<=100 or not math.isfinite(price) or price<=0:
                raise ValueError()
        except (ValueError,TypeError):
            errors["INVALID_SCORE_OR_PRICE"]+=1
            continue
        if not row.get("symbol") or not row.get("exchange_code"):
            errors["MISSING_IDENTITY"]+=1
            continue
        if row.get("quality_pass") not in (1,True,"1"):
            errors["QUALITY_GATE_NOT_PASSED"]+=1
            continue
        if freshness!="RUN_UTC_DATE_MATCH":
            errors["STALE_RUN"]+=1
            continue
        # Date of observation must also match requested UTC day. Exchange-local
        # close verification requires calendar/bar-level integration.
        observation=_date(row.get("observed_at_utc"))
        if not observation or observation.date()!=requested:
            errors["STALE_OR_UNDATED_OBSERVATION"]+=1
            continue
        exchange=str(row['exchange_code']).upper()
        if exchange not in close_windows:
            errors['UNKNOWN_EXCHANGE_CLOSE_WINDOW']+=1
            continue
        tz_name,close_clock=close_windows[exchange]
        local_finish=finish.astimezone(ZoneInfo(tz_name)) if finish else None
        if (not local_finish or local_finish.date()!=requested or
                local_finish.weekday()>=5 or local_finish.time()<close_clock):
            errors['PRE_CLOSE_OR_NON_SESSION_RUN']+=1
            continue
        eligible.append(row)
    eligible.sort(key=lambda r:(-float(r["opportunity_score"]),str(r["symbol"])))
    # Exchange codes are not mapped to markets without an authoritative mapping.
    selected=eligible[:limit]
    output=[]
    for index,row in enumerate(selected,1):
        output.append(dict(rank=index,symbol=row["symbol"],
            exchange_code=row["exchange_code"],currency=row.get("currency",""),
            opportunity_score=row["opportunity_score"],quality_pass=row["quality_pass"],
            price=row["price"],price_source=row.get("price_source",""),
            observed_at_utc=row.get("observed_at_utc",""),
            scan_run_id=run["id"],scan_status=run.get("status",""),
            run_finished_at_utc=run.get("finished_at_utc",""),
            freshness="POST_REGULAR_CLOSE_RUN_ONLY",setup_status="UNVERIFIED",
            entry="",target="",stop="",
            reason="Scanner quality passed after regular close; EOD bar and strategy setup NOT validated"))
    summary=dict(as_of=as_of,source="scanner SQLite read-only",run_id=run["id"],
        run_status=run.get("status"),run_finished_at_utc=run.get("finished_at_utc"),
        scanner_candidates=len(candidates),eligible=len(eligible),
        selected=len(output),excluded=dict(errors),
        status="POST_CLOSE_SCAN_UNVERIFIED_BAR" if output else "ABSTAIN",
        notes=["No ticker was selected manually",
               "Regular close time checked per exchange and DST; holidays, half-days, and final EOD bars not independently verified",
               "Opportunity score is not a calibrated probability",
               "No strategy confirmation, entry, target or stop is invented",
               "Top ranked globally; exchange-to-market mapping not inferred",
               "No orders or portfolio changes"])
    return output,summary


def main(argv=None):
    parser=argparse.ArgumentParser(description="Report real scanner candidates from TradePilot SQLite, read-only")
    parser.add_argument("--db",default="data/tradepilot.db")
    parser.add_argument("--as-of",required=True)
    parser.add_argument("--top",type=int,default=20)
    parser.add_argument("--run-id",type=int)
    parser.add_argument("--prefix",default=".cache/v6_actual_scanner")
    args=parser.parse_args(argv)
    rows,summary=report(args.db,args.as_of,args.top,args.run_id)
    write_csv(args.prefix+"_ranked.csv",rows,COLUMNS)
    path=Path(args.prefix+"_summary.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    for row in rows:
        print(f"#{row['rank']} {row['symbol']} {row['exchange_code']} score={row['opportunity_score']} price={row['price']} setup=UNVERIFIED")
    if not rows:
        print("ABSTAIN: no fresh, quality-passed scanner candidates for requested UTC date")


if __name__=="__main__":
    main()
