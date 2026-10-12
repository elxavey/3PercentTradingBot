"""MX official-source quarterly observations -> point-in-time v6 YoY trend candidates.

Input is manually verified transcription from issuer reports, NOT scraped estimates.
Dates must be publication dates, not document retrieval dates.
"""
import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from tradepilot.v6_financial_trends_cli import COLUMNS as TREND_COLUMNS

METRICS = ("revenue", "net_income", "operating_cash_flow")
INPUT_COLUMNS = ("symbol", "metric", "period_start", "period_end", "published_at",
                 "value", "currency", "scale", "source_url", "source_page",
                 "verification_status")
OUTPUT_COLUMNS = TREND_COLUMNS + ("source_url_latest", "source_url_previous", "currency", "scale")


def validated_observations(rows):
    verified = defaultdict(list)
    problems = []
    for index, row in enumerate(rows, 2):
        try:
            symbol = row["symbol"].strip().upper()
            metric = row["metric"].strip()
            if metric not in METRICS:
                raise ValueError("unsupported metric")
            if row["verification_status"].strip().upper() != "VERIFIED":
                continue
            start, end, published = (date.fromisoformat(row[k]) for k in
                                     ("period_start", "period_end", "published_at"))
            if not (60 <= (end - start).days <= 120 and end <= published):
                raise ValueError("invalid quarterly dates")
            if not row["source_url"].startswith("https://"):
                raise ValueError("missing HTTPS primary source")
            if not row["source_page"].strip():
                raise ValueError("missing source page")
            currency = row["currency"].strip().upper()
            if currency not in ("MXN", "USD"):
                raise ValueError("currency must be MXN or USD")
            scale = row["scale"].strip()
            if scale not in ("1", "1000", "1000000"):
                raise ValueError("scale must be 1, 1000 or 1000000")
            value = float(row["value"])
            import math
            if not math.isfinite(value):
                raise ValueError("nonfinite value")
            verified[(symbol, metric)].append({
                "start": start, "end": end, "published": published,
                "value": value * int(scale), "currency": currency,
                "source_url": row["source_url"], "scale": scale,
            })
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"line {index}: {exc}")
    return verified, problems


def mx_trends(cases, observations):
    results = []
    for case in cases:
        if case.get("market") != "MX":
            continue
        symbol, signal = case["symbol"].upper(), date.fromisoformat(case["signal_date"])
        for metric in METRICS:
            eligible = [r for r in observations.get((symbol, metric), [])
                        if r["published"] < signal]
            # Reject ambiguous conflicting data for identical quarter/currency.
            periods = defaultdict(list)
            for r in eligible:
                periods[(r["start"], r["end"], r["currency"])].append(r)
            ambiguous = any(len({(r["value"], r["source_url"]) for r in items}) > 1
                            for items in periods.values())
            latest = max(eligible, key=lambda r: (r["end"], r["published"])) if eligible else None
            previous = None
            if latest:
                matches = [r for r in eligible
                           if r["currency"] == latest["currency"]
                           and 350 <= (latest["end"] - r["end"]).days <= 380
                           and abs((latest["end"] - latest["start"]).days -
                                   (r["end"] - r["start"]).days) <= 14]
                previous = max(matches, key=lambda r: (r["end"], r["published"])) if matches else None
            status = ("AMBIGUOUS_SOURCE" if ambiguous else
                      "MISSING_LATEST" if latest is None else
                      "MISSING_YOY_COMPARISON" if previous is None else
                      "ZERO_BASELINE" if previous["value"] == 0 else "CANDIDATE_YOY")
            change = (round((latest["value"] - previous["value"]) /
                            abs(previous["value"]) * 100, 3)
                      if status == "CANDIDATE_YOY" else "")
            results.append({
                "case_id": case["case_id"], "symbol": symbol,
                "signal_date": case["signal_date"], "metric": metric,
                "latest_value": latest["value"] if latest else "",
                "previous_value": previous["value"] if previous else "",
                "change_pct": change,
                "latest_period_end": latest["end"].isoformat() if latest else "",
                "previous_period_end": previous["end"].isoformat() if previous else "",
                "latest_filed": latest["published"].isoformat() if latest else "",
                "previous_filed": previous["published"].isoformat() if previous else "",
                "status": status,
                "note": "MX official report, manually verified; strictly before signal",
                "source_url_latest": latest["source_url"] if latest else "",
                "source_url_previous": previous["source_url"] if previous else "",
                "currency": latest["currency"] if latest else "",
                "scale": "1",
            })
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build Mexico PIT trends from verified official report observations")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--input", default=".cache/v6_mx_observations.csv")
    parser.add_argument("--output", default=".cache/v6_mx_financial_trends.csv")
    parser.add_argument("--errors", default=".cache/v6_mx_validation_errors.json")
    args = parser.parse_args(argv)
    source = Path(args.input)
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        with source.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=INPUT_COLUMNS)
            writer.writeheader()
        print(f"Created empty verification template: {source}")
    def read(path):
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream))
    observations, errors = validated_observations(read(source))
    results = mx_trends(read(args.cases), observations)
    output = Path(args.output)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    Path(args.errors).write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    print(f"MX trends: {len(results)} rows; valid YoY: {sum(r['status']=='CANDIDATE_YOY' for r in results)}; errors: {len(errors)}")
    print("Unverified or absent observations are missing, never assigned invented scores.")


if __name__ == "__main__":
    main()
