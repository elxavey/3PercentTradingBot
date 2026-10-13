"""Single reproducible batch audit for the five remaining Mexican v6 cases.

Only independently VERIFIED official-source observations are eligible. Empty
coverage is reported as UNSCORED; no simulated data, no threshold tuning.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from tradepilot.v6_mx_financials_cli import INPUT_COLUMNS, OUTPUT_COLUMNS, validated_observations, mx_trends
from tradepilot.v6_financial_quality_cli import score_cases, COLUMNS as QUALITY_COLUMNS
from tradepilot.v6_stop_target_cli import analyze, DETAIL_COLUMNS, THRESHOLD_COLUMNS, write_csv

SYMBOLS = ("ALSEA.MX", "BIMBOA.MX", "LIVEPOLC-1.MX", "CHDRAUIB.MX", "PINFRA.MX")
COVERAGE_COLUMNS = ("case_id", "symbol", "signal_date", "fixed_outcome",
                    "revenue", "net_income", "operating_cash_flow",
                    "coverage_pct", "quality_score", "decision_at_50")


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def batch(cases, source_rows):
    selected = [case for case in cases if case["symbol"] in SYMBOLS and case["market"] == "MX"]
    if len(selected) != len(SYMBOLS) or {c["symbol"] for c in selected} != set(SYMBOLS):
        raise ValueError("Expected exactly five distinct MX cases in pilot")
    facts, errors = validated_observations(source_rows)
    if errors:
        raise ValueError("Invalid source observations: " + "; ".join(errors))
    trends = mx_trends(selected, facts)
    quality = score_cases(selected, trends)
    detail, thresholds, summary = analyze(selected, quality)
    by_trend = {(r["case_id"], r["metric"]): r for r in trends}
    by_quality = {r["case_id"]: r for r in quality}
    by_detail = {r["case_id"]: r for r in detail}
    coverage = []
    for case in selected:
        cid = case["case_id"]
        q = by_quality[cid]
        d = by_detail[cid]
        coverage.append({
            "case_id": cid, "symbol": case["symbol"], "signal_date": case["signal_date"],
            "fixed_outcome": case["fixed_outcome"],
            **{metric: by_trend[(cid, metric)]["status"]
               for metric in ("revenue", "net_income", "operating_cash_flow")},
            "coverage_pct": q["coverage_pct"],
            "quality_score": q["quality_score"],
            "decision_at_50": d["decision_at_50"],
        })
    summary["market"] = "MX"
    summary["scope"] = "Five remaining MX pilot cases, excluding ALPEKA.MX"
    summary["financial_status_counts"] = dict(Counter(r["status"] for r in trends))
    summary["sources_reviewed"] = len(source_rows)
    summary["note"] = "Missing or unverified official data is UNSCORED, never treated as an exclusion."
    return trends, quality, detail, thresholds, coverage, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Five-company Mexican point-in-time v6 batch audit")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--observations", default=".cache/v6_mx_observations.csv")
    parser.add_argument("--prefix", default=".cache/v6_mx_batch")
    args = parser.parse_args(argv)
    path = Path(args.observations)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        write_csv(path, [], INPUT_COLUMNS)
    rows = read_csv(path)
    trends, quality, detail, thresholds, coverage, summary = batch(read_csv(args.cases), rows)
    for suffix, data, fields in (
        ("_trends.csv", trends, OUTPUT_COLUMNS),
        ("_quality.csv", quality, QUALITY_COLUMNS),
        ("_stop_target.csv", detail, DETAIL_COLUMNS),
        ("_thresholds.csv", thresholds, THRESHOLD_COLUMNS),
        ("_coverage.csv", coverage, COVERAGE_COLUMNS),
    ):
        write_csv(args.prefix + suffix, data, fields)
    Path(args.prefix + "_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"MX batch: {len(coverage)} companies, scored={summary['sample']['scored']}, "
          f"unscored={summary['sample']['unscored']}")
    for row in coverage:
        print(f"  {row['symbol']}: coverage={row['coverage_pct']}%, "
              f"score={row['quality_score'] or 'UNSCORED'}, decision={row['decision_at_50']}")
    print("Historical case-control analysis only. No trading recommendations.")


if __name__ == "__main__":
    main()
