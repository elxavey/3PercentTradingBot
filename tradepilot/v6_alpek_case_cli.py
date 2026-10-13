"""Reproducible Alpek historical case, with explicit partial-coverage audit.

Two confirmed consolidated metrics are seeded from Alpek's 3Q22 BMV report,
page 31; CFO is intentionally absent (reported EBITDA/Flujo is NOT operating cash).
Never manufacture a full score.
"""
import argparse
import csv
import json
from pathlib import Path

from tradepilot.v6_mx_financials_cli import (
    INPUT_COLUMNS, OUTPUT_COLUMNS, validated_observations, mx_trends,
)
from tradepilot.v6_financial_quality_cli import score_cases, COLUMNS as QUALITY_COLUMNS
from tradepilot.v6_stop_target_cli import analyze, DETAIL_COLUMNS, THRESHOLD_COLUMNS, write_csv


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def run(cases, observations):
    selected = [case for case in cases if case["symbol"] == "ALPEKA.MX"]
    if len(selected) != 1:
        raise ValueError("Expected exactly one ALPEKA.MX pilot case")
    verified, errors = validated_observations(observations)
    if errors:
        raise ValueError("; ".join(errors))
    trends = mx_trends(selected, verified)
    quality = score_cases(selected, trends)
    details, thresholds, summary = analyze(selected, quality)
    return trends, quality, details, thresholds, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Alpek official 3Q22 point-in-time financial case study")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--source", default="research/v6_alpek_verified_observations.csv")
    parser.add_argument("--prefix", default=".cache/v6_alpek")
    args = parser.parse_args(argv)
    observations = read_csv(args.source)
    trends, quality, details, thresholds, summary = run(read_csv(args.cases), observations)
    write_csv(args.prefix + "_trends.csv", trends, OUTPUT_COLUMNS)
    write_csv(args.prefix + "_quality.csv", quality, QUALITY_COLUMNS)
    write_csv(args.prefix + "_stop_target.csv", details, DETAIL_COLUMNS)
    write_csv(args.prefix + "_thresholds.csv", thresholds, THRESHOLD_COLUMNS)
    summary["source"] = args.source
    summary["source_document"] = "https://www.alpek.com/wp-content/uploads/2022/10/Alpek-BMV-3Q22.pdf"
    summary["source_page"] = 31
    summary["known_limitation"] = (
        "The BMV report's 'Flujo' is EBITDA, not operating cash flow. "
        "Operating cash flow is unverified, so quality_score MUST remain empty."
    )
    Path(args.prefix + "_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("ALPEK 3Q22/3Q21:")
    for row in trends:
        print(f"  {row['metric']}: {row['status']} "
              f"{row['change_pct'] if row['change_pct'] != '' else 'N/A'}%")
    print(f"Quality: {quality[0]['quality_status']} / coverage {quality[0]['coverage_pct']}%")
    print(f"Score: {quality[0]['quality_score'] or 'UNSCORED'}")
    print("Files: " + args.prefix + "_*.csv and " + args.prefix + "_summary.json")


if __name__ == "__main__":
    main()
