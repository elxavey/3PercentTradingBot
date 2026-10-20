"""Build a symbol-independent official-source research queue from case CSV.

The registry is data, not a hardcoded symbol allowlist. Unknown issuers remain
UNKNOWN_SOURCE rather than guessed. Never automatically marks documents verified.
"""
import argparse
import csv
from pathlib import Path
from tradepilot.v6_stop_target_cli import write_csv

COLUMNS=("case_id","symbol","market","signal_date","source_status",
         "official_archive","initial_document","review_note")


def build(cases,catalog):
    registry={r["symbol"].strip().upper():r for r in catalog if r.get("symbol")}
    result=[]
    for case in cases:
        symbol=case["symbol"].upper()
        record=registry.get(symbol,{})
        if case["market"]=="US":
            status="SEC_PROVIDER"
        elif record.get("official_archive") or record.get("initial_document"):
            status="OFFICIAL_SOURCE_LEAD"
        else:
            status="UNKNOWN_SOURCE"
        result.append(dict(case_id=case["case_id"],symbol=symbol,market=case["market"],
                           signal_date=case["signal_date"],source_status=status,
                           official_archive=record.get("official_archive",""),
                           initial_document=record.get("initial_document",""),
                           review_note=record.get("notes","Official source not registered; discovery required")))
    return result


def read(path):
    p=Path(path)
    if not p.exists():
        return []
    with p.open(newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--cases",default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--catalog",default="research/v6_mx_source_catalog.csv")
    parser.add_argument("--output",default=".cache/v6_financial_source_queue.csv")
    args=parser.parse_args(argv)
    result=build(read(args.cases),read(args.catalog))
    write_csv(args.output,result,COLUMNS)
    print(f"Source queue: {len(result)} cases, {sum(r['source_status']=='UNKNOWN_SOURCE' for r in result)} unknown issuers")


if __name__=="__main__":
    main()
