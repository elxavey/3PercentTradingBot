"""Audit v6 financial coverage without treating missing data as financial risk."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

METRICS = ("revenue", "net_income", "assets", "liabilities", "cash",
           "long_term_debt", "operating_cash_flow")
COLUMNS = ("case_id", "symbol", "market", "signal_date", "metric",
           "coverage_status", "value", "unit", "filed", "period_end",
           "days_old_at_signal", "source_url", "note")


def audit(cases, fundamentals, errors=()):
    lookup = defaultdict(list)
    for row in fundamentals:
        lookup[(row["case_id"], row["metric"])].append(row)
    result = []
    for case in cases:
        for metric in METRICS:
            matches = lookup.get((case["case_id"], metric), [])
            if case["market"] != "US":
                status, note = "NOT_SUPPORTED_MX", "SEC US-GAAP extraction does not cover Mexican issuers"
            elif any(str(e).startswith(case["symbol"] + ":") for e in errors):
                status, note = "SOURCE_ERROR", "SEC lookup failed; see error log"
            elif len(matches) > 1:
                status, note = "DUPLICATE_FACT", "Multiple candidates for the same case and metric"
            elif not matches:
                status, note = "MISSING_FACT", "No eligible historical SEC XBRL fact; not a negative signal"
            else:
                status, note = "CANDIDATE", "Historical filing date only; financial interpretation not reviewed"
            fact = matches[0] if len(matches) == 1 else {}
            age = ""
            if fact.get("period_end"):
                from datetime import date
                age = (date.fromisoformat(case["signal_date"]) -
                       date.fromisoformat(fact["period_end"])).days
            result.append({
                "case_id": case["case_id"], "symbol": case["symbol"],
                "market": case["market"], "signal_date": case["signal_date"],
                "metric": metric, "coverage_status": status,
                "value": fact.get("value", ""), "unit": fact.get("unit", ""),
                "filed": fact.get("filed", ""),
                "period_end": fact.get("period_end", ""),
                "days_old_at_signal": age, "source_url": fact.get("source_url", ""),
                "note": note,
            })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit financial fact coverage for v6")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--fundamentals", default=".cache/v6_sec_fundamentals.csv")
    parser.add_argument("--errors", default=".cache/v6_sec_fundamentals_errors.json")
    parser.add_argument("--output", default=".cache/v6_financial_coverage.csv")
    parser.add_argument("--summary", default=".cache/v6_financial_coverage_summary.json")
    args = parser.parse_args(argv)
    def load_csv(path):
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream))
    cases, fundamentals = load_csv(args.cases), load_csv(args.fundamentals)
    errors = json.loads(Path(args.errors).read_text(encoding="utf-8"))
    rows = audit(cases, fundamentals, errors)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    from collections import Counter
    summary = {"cases": len(cases), "candidate_facts": len(fundamentals),
               "coverage": dict(Counter(row["coverage_status"] for row in rows)),
               "per_symbol": {
                   case["symbol"]: {
                       "candidates": sum(r["coverage_status"] == "CANDIDATE"
                                         for r in rows if r["case_id"] == case["case_id"]),
                       "missing": [r["metric"] for r in rows
                                   if r["case_id"] == case["case_id"]
                                   and r["coverage_status"] == "MISSING_FACT"]
                   } for case in cases}}
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Coverage: {len(rows)} case-metric rows, {summary['coverage']}")
    print(f"Saved: {args.output} and {args.summary}")


if __name__ == "__main__":
    main()
