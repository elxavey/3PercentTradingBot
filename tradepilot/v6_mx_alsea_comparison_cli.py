"""6.2.2: parse comparative ALSEA 2Q23 table without mixing IFRS bases.

Consumes v6_mx_structured_rows.csv; does not download or modify verified data.
"""
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

from tradepilot.v6_stop_target_cli import write_csv

COLUMNS = ("symbol","metric","basis","period_latest","period_previous",
           "latest_value","previous_value","reported_change_pct",
           "calculated_change_pct","difference_pp","currency","scale",
           "source_url","source_page","published_at","signal_date",
           "verification_status","note")
AUDIT_COLUMNS = ("symbol","metric","basis","status","reason","source_page")
AMOUNT = r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"
ROW = re.compile(
    r"^\s*(Ventas Netas|Utilidad Neta)\s+"
    + AMOUNT + r"\s+" + AMOUNT + r"\s+(-?\d+(?:\.\d+)?)%\s+"
    + AMOUNT + r"\s+" + AMOUNT + r"\s+(-?\d+(?:\.\d+)?)%\s*$",
    re.I,
)
METRIC = {"ventas netas":"revenue","utilidad neta":"net_income"}
BASIS = ("PRE_IFRS16","POST_IFRS16_REEXPRESSED")
PERIOD = ("2023-04-01/2023-06-30","2022-04-01/2022-06-30")


def parse(rows, tolerance_pp=0.35):
    candidates, audit, seen = [], [], set()
    for row in rows:
        symbol = row["symbol"]
        metric = row["metric"]
        text = row["table_row"].strip()
        match = ROW.fullmatch(text)
        if symbol != "ALSEA.MX" or metric not in ("revenue","net_income"):
            continue
        if not match:
            audit.append(dict(symbol=symbol,metric=metric,basis="",status="SKIPPED",
                              reason="Not an exact comparative table row",source_page=row["page"]))
            continue
        if METRIC[match.group(1).lower()] != metric:
            continue
        # Require both accounting-basis column labels and explicit comparative quarter header.
        header = row["header_context"].lower()
        if not (("pre-ifrs" in header and "post-ifrs" in header)
                and "2t23" in header and "2t22" in header):
            audit.append(dict(symbol=symbol,metric=metric,basis="",status="BLOCKED",
                              reason="Comparative column headers missing",source_page=row["page"]))
            continue
        if not row["published_at"] or date.fromisoformat(row["published_at"]) >= date.fromisoformat(row["signal_date"]):
            audit.append(dict(symbol=symbol,metric=metric,basis="",status="BLOCKED",
                              reason="Publication is not strictly before signal",source_page=row["page"]))
            continue
        for index, basis in enumerate(BASIS):
            offset = 2 if index == 0 else 5
            latest = int(match.group(offset).replace(",",""))
            previous = int(match.group(offset+1).replace(",",""))
            reported = float(match.group(offset+2))
            key = (symbol,metric,basis,row["source_url"],row["page"],text)
            if key in seen:
                audit.append(dict(symbol=symbol,metric=metric,basis=basis,status="DUPLICATE",
                                  reason="Identical row already parsed",source_page=row["page"]))
                continue
            seen.add(key)
            if previous == 0:
                status,calc,diff="BLOCKED_ZERO_BASELINE","",""
            else:
                calc = round((latest-previous)/abs(previous)*100,3)
                diff = round(abs(calc-reported),3)
                status = "PENDING_REVIEW" if diff <= tolerance_pp else "REPORTED_CHANGE_MISMATCH"
            candidates.append(dict(
                symbol=symbol,metric=metric,basis=basis,
                period_latest=PERIOD[0],period_previous=PERIOD[1],
                latest_value=latest,previous_value=previous,
                reported_change_pct=reported,calculated_change_pct=calc,
                difference_pp=diff,currency="MXN",scale="UNCONFIRMED",
                source_url=row["source_url"],source_page=row["page"],
                published_at=row["published_at"],signal_date=row["signal_date"],
                verification_status=status,
                note="Quarter and accounting basis parsed; verify report unit, consolidation and numeric column positions in original PDF before VERIFIED",
            ))
            audit.append(dict(symbol=symbol,metric=metric,basis=basis,status=status,
                              reason="Arithmetic cross-check; no automatic verification",source_page=row["page"]))
    # Explicitly show missing CFO, never replace with EBITDA.
    if not any(c["metric"]=="operating_cash_flow" for c in candidates):
        audit.append(dict(symbol="ALSEA.MX",metric="operating_cash_flow",basis="",
                          status="MISSING_SOURCE",reason="Consolidated quarterly operating cash flow not established; EBITDA is not CFO",source_page=""))
    return candidates,audit


def main(argv=None):
    parser=argparse.ArgumentParser(description="Audit ALSEA comparative IFRS financial rows")
    parser.add_argument("--input",default=".cache/v6_mx_structured_rows.csv")
    parser.add_argument("--prefix",default=".cache/v6_mx_alsea_comparison")
    args=parser.parse_args(argv)
    with Path(args.input).open(newline="",encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    candidates,audit=parse(rows)
    write_csv(args.prefix+"_candidates.csv",candidates,COLUMNS)
    write_csv(args.prefix+"_audit.csv",audit,AUDIT_COLUMNS)
    summary={"candidates":len(candidates),"pending_review":sum(x["verification_status"]=="PENDING_REVIEW" for x in candidates),
             "verified":0,"cfo_status":"MISSING_SOURCE","scores_changed":False}
    p=Path(args.prefix+"_summary.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(f"ALSEA comparisons: {len(candidates)} candidates; VERIFIED=0; CFO missing")


if __name__=="__main__":
    main()
