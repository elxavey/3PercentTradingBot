"""Generic, market-agnostic financial research aggregation for TradePilot v6.

Consumes existing provider outputs; does not scrape, invent, verify or trade.
A case is identified by (case_id, symbol, market, signal_date).
"""
import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from tradepilot.v6_financial_quality_cli import METRICS, score_cases, COLUMNS as QUALITY_COLUMNS
from tradepilot.v6_financial_trends_cli import COLUMNS as TREND_COLUMNS
from tradepilot.v6_mx_financials_cli import validated_observations, mx_trends, INPUT_COLUMNS
from tradepilot.v6_stop_target_cli import write_csv

COVERAGE_COLUMNS = ("case_id","symbol","market","signal_date","metric",
                    "status","latest_period_end","previous_period_end",
                    "latest_filed","previous_filed","currency","scale",
                    "source_url_latest","source_url_previous","reason")
REQUIRED_CASE_FIELDS = ("case_id","symbol","market","signal_date")
ALLOWED_MARKETS = ("US","MX")


def aggregate(cases, us_trends, mx_source_rows):
    seen = set()
    for case in cases:
        for field in REQUIRED_CASE_FIELDS:
            if not case.get(field):
                raise ValueError(f"Missing case field: {field}")
        if case["market"] not in ALLOWED_MARKETS:
            raise ValueError(f"Unsupported market: {case['market']}")
        date.fromisoformat(case["signal_date"])
        if case["case_id"] in seen:
            raise ValueError(f"Duplicate case_id: {case['case_id']}")
        seen.add(case["case_id"])
    facts, problems = validated_observations(mx_source_rows)
    if problems:
        raise ValueError("Invalid MX observations: " + "; ".join(problems))
    mx_cases = [c for c in cases if c["market"] == "MX"]
    mx_rows = mx_trends(mx_cases, facts)
    us_cases = {c["case_id"]:c for c in cases if c["market"] == "US"}
    selected_us = []
    us_keys = set()
    for row in us_trends:
        case = us_cases.get(row.get("case_id"))
        if case is None:
            continue
        if row.get("symbol") != case["symbol"] or row.get("signal_date") != case["signal_date"]:
            raise ValueError(f"US trend identity mismatch: {row.get('case_id')}")
        metric = row.get("metric")
        if metric not in METRICS:
            raise ValueError(f"Invalid US metric: {metric}")
        key=(case["case_id"],metric)
        if key in us_keys:
            raise ValueError(f"Duplicate US trend: {key}")
        us_keys.add(key)
        selected_us.append({k:row.get(k,"") for k in TREND_COLUMNS})
    # Missing provider rows must remain missing, not silently disappear.
    for case in us_cases.values():
        for metric in METRICS:
            if (case["case_id"],metric) not in us_keys:
                selected_us.append(dict(case_id=case["case_id"],symbol=case["symbol"],
                    signal_date=case["signal_date"],metric=metric,status="MISSING_PROVIDER_DATA",
                    note="US provider has no row for this metric"))
    trends = mx_rows + selected_us
    quality = score_cases(cases, trends)
    coverage=[]
    market_by_case={c["case_id"]:c["market"] for c in cases}
    for row in trends:
        coverage.append({
            "case_id":row["case_id"],"symbol":row["symbol"],
            "market":market_by_case[row["case_id"]],
            "signal_date":row["signal_date"],"metric":row["metric"],
            "status":row["status"],"latest_period_end":row.get("latest_period_end",""),
            "previous_period_end":row.get("previous_period_end",""),
            "latest_filed":row.get("latest_filed",""),
            "previous_filed":row.get("previous_filed",""),
            "currency":row.get("currency",""),"scale":row.get("scale",""),
            "source_url_latest":row.get("source_url_latest",""),
            "source_url_previous":row.get("source_url_previous",""),
            "reason":row.get("note",""),
        })
    summary={
        "cases":len(cases),"by_market":dict(Counter(c["market"] for c in cases)),
        "coverage_status":dict(Counter(r["status"] for r in trends)),
        "quality_status":dict(Counter(r["quality_status"] for r in quality)),
        "mx_verified_source_rows":sum(r.get("verification_status","").upper()=="VERIFIED" for r in mx_source_rows),
        "methodology":"Historical research only; provider data is not independently certified by this aggregator",
        "limitations":["US CANDIDATE_YOY is an experimental provider candidate, not a VERIFIED filing audit",
                       "MX source observations must be independently verified before import",
                       "Missing data never becomes a negative signal",
                       "No trading recommendations or execution"],
    }
    return trends,quality,coverage,summary


def read(path):
    with Path(path).open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def main(argv=None):
    parser=argparse.ArgumentParser(description="Generic US/MX financial quality research pipeline")
    parser.add_argument("--cases",default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--us-trends",default=".cache/v6_financial_trends.csv")
    parser.add_argument("--mx-observations",default=".cache/v6_mx_observations.csv")
    parser.add_argument("--prefix",default=".cache/v6_financial_engine")
    args=parser.parse_args(argv)
    cases=read(args.cases)
    us_path=Path(args.us_trends)
    mx_path=Path(args.mx_observations)
    us_rows=read(us_path) if us_path.exists() else []
    mx_rows=read(mx_path) if mx_path.exists() else []
    trends,quality,coverage,summary=aggregate(cases,us_rows,mx_rows)
    # Normalize provider-specific fields for the shared trend schema. Preserve
    # extra MX provenance in the coverage report instead of dropping its audit trail.
    write_csv(args.prefix+"_trends.csv",
              [{field: row.get(field,"") for field in TREND_COLUMNS} for row in trends],
              TREND_COLUMNS)
    write_csv(args.prefix+"_quality.csv",quality,QUALITY_COLUMNS)
    write_csv(args.prefix+"_coverage.csv",coverage,COVERAGE_COLUMNS)
    path=Path(args.prefix+"_summary.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Financial Engine: {summary['cases']} cases; quality: {summary['quality_status']}")
    print("Research-only; missing sources remain unscored; no production decisions.")


if __name__=="__main__":
    main()
