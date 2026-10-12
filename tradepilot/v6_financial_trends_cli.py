"""Point-in-time financial trends from SEC XBRL, without forward leakage."""
import argparse
import csv
import json
import os
import time
from datetime import date
from pathlib import Path

from tradepilot.v6_sec_fundamentals_cli import (
    METRICS, SEC_FACTS, SEC_TICKERS, cik_mapping, fetch_json,
)

FLOW_METRICS = ("revenue", "net_income", "operating_cash_flow")
COLUMNS = ("case_id", "symbol", "signal_date", "metric", "latest_value",
           "previous_value", "change_pct", "latest_period_end",
           "previous_period_end", "latest_filed", "previous_filed",
           "status", "note")


def eligible(facts, metric, signal_date):
    day = date.fromisoformat(signal_date)
    found = []
    for priority, tag in enumerate(METRICS[metric]):
        for unit, observations in facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).items():
            if unit != "USD":
                continue
            for item in observations:
                if item.get("form") not in ("10-Q", "10-K", "20-F", "6-K"):
                    continue
                try:
                    filed = date.fromisoformat(item["filed"])
                    end = date.fromisoformat(item["end"])
                    start = date.fromisoformat(item["start"])
                except (KeyError, ValueError, TypeError):
                    continue
                duration = (end - start).days
                if filed >= day or end > filed or not 60 <= duration <= 120:
                    continue
                if not isinstance(item.get("val"), (int, float)) or isinstance(item["val"], bool):
                    continue
                found.append({"value": item["val"], "start": start, "end": end,
                              "filed": filed, "priority": priority, "tag": tag})
    return found


def compare(facts, metric, signal_date):
    observations = eligible(facts, metric, signal_date)
    if not observations:
        return {"status": "MISSING_LATEST", "note": "No eligible quarter before signal"}
    # A quarterly observation can be refiled: choose newest available filing per period.
    by_period = {}
    for item in observations:
        key = (item["start"], item["end"])
        old = by_period.get(key)
        if old is None or (item["filed"], -item["priority"]) > (old["filed"], -old["priority"]):
            by_period[key] = item
    latest = max(by_period.values(), key=lambda r: (r["end"], r["filed"], -r["priority"]))
    # Match year-over-year quarter, rather than preceding quarter or fiscal YTD.
    matches = [r for r in by_period.values()
               if 350 <= (latest["end"] - r["end"]).days <= 380
               and abs((latest["end"] - latest["start"]).days -
                       (r["end"] - r["start"]).days) <= 14]
    previous = max(matches, key=lambda r: (r["end"], r["filed"], -r["priority"])) if matches else None
    base = {"latest_value": latest["value"], "latest_period_end": latest["end"].isoformat(),
            "latest_filed": latest["filed"].isoformat(),
            "previous_value": previous["value"] if previous else "",
            "previous_period_end": previous["end"].isoformat() if previous else "",
            "previous_filed": previous["filed"].isoformat() if previous else ""}
    if previous is None:
        return {**base, "status": "MISSING_YOY_COMPARISON",
                "note": "No matching prior-year quarter filed before signal"}
    if previous["value"] == 0:
        return {**base, "status": "ZERO_BASELINE", "note": "Percent change undefined for zero baseline"}
    change = (latest["value"] - previous["value"]) / abs(previous["value"]) * 100
    return {**base, "change_pct": round(change, 3), "status": "CANDIDATE_YOY",
            "note": "Quarterly year-over-year candidate; not yet manually reviewed"}


def build(cases, mapping, fetcher):
    rows, errors = [], []
    by_symbol = {}
    for case in cases:
        if case.get("market") == "US":
            by_symbol.setdefault(case["symbol"].upper(), []).append(case)
    for symbol, selected in sorted(by_symbol.items()):
        cik = mapping.get(symbol)
        if cik is None:
            errors.append(f"{symbol}: no SEC CIK match")
            continue
        try:
            facts = fetcher(SEC_FACTS.format(cik=cik))
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")
            continue
        for case in selected:
            for metric in FLOW_METRICS:
                rows.append({"case_id": case["case_id"], "symbol": symbol,
                             "signal_date": case["signal_date"], "metric": metric,
                             "latest_value": "", "previous_value": "",
                             "change_pct": "", "latest_period_end": "",
                             "previous_period_end": "", "latest_filed": "",
                             "previous_filed": "", **compare(facts, metric, case["signal_date"])})
    return rows, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Historical SEC year-over-year financial trend candidates")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--output", default=".cache/v6_financial_trends.csv")
    parser.add_argument("--errors", default=".cache/v6_financial_trends_errors.json")
    args = parser.parse_args(argv)
    agent = os.getenv("SEC_USER_AGENT", "").strip()
    if "@" not in agent:
        parser.error("Set SEC_USER_AGENT with real contact email")
    with Path(args.cases).open(newline="", encoding="utf-8-sig") as stream:
        cases = list(csv.DictReader(stream))
    mapping = cik_mapping(fetch_json(SEC_TICKERS, agent))
    def polite_fetch(url):
        time.sleep(0.2)
        return fetch_json(url, agent)
    rows, errors = build(cases, mapping, polite_fetch)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    Path(args.errors).write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    print(f"Trend candidates: {len(rows)}; errors: {len(errors)}")
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
