"""Experimental v6 financial quality research: no outcome leakage, no trade automation."""
import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

METRICS = ("revenue", "net_income", "operating_cash_flow")
WEIGHTS = {"revenue": 35, "net_income": 35, "operating_cash_flow": 30}
COLUMNS = ("case_id", "symbol", "market", "signal_date", "quality_score",
           "coverage_pct", "quality_status", "event_risk_status",
           "revenue_signal", "net_income_signal", "operating_cash_flow_signal",
           "notes")


def _number(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        result = float(value)
        import math
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def metric_signal(row):
    if not row or row.get("status") != "CANDIDATE_YOY":
        return None, "NO_COMPARABLE_DATA"
    latest = _number(row.get("latest_value"))
    previous = _number(row.get("previous_value"))
    if latest is None or previous is None:
        return None, "INVALID_VALUES"
    metric = row["metric"]
    if metric == "revenue":
        if previous <= 0:
            return None, "INVALID_REVENUE_BASELINE"
        ratio = (latest - previous) / previous
        return (1 if ratio >= .05 else -1 if ratio <= -.05 else 0), "REVENUE_YOY"
    # Signed cash/income: improvement in absolute units, not misleading percentage
    if previous < 0 <= latest:
        return 1, "TURNED_POSITIVE"
    if previous >= 0 > latest:
        return -1, "TURNED_NEGATIVE"
    if latest < 0 and previous < 0:
        return (1 if latest > previous else -1 if latest < previous else 0), "NEGATIVE_BASE_COMPARISON"
    if previous == 0:
        return None, "ZERO_BASELINE"
    ratio = (latest - previous) / abs(previous)
    return (1 if ratio >= .05 else -1 if ratio <= -.05 else 0), "SIGNED_YOY"


def score_cases(cases, trends):
    by_key = {}
    for trend in trends:
        key = (trend.get("case_id"), trend.get("metric"))
        if key in by_key:
            raise ValueError(f"Duplicate trend for {key}")
        by_key[key] = trend
    result = []
    for case in cases:
        cid = case["case_id"]
        parts, notes, weighted = {}, [], 0
        available_weight = 0
        for metric in METRICS:
            item = by_key.get((cid, metric))
            if item and (item.get("symbol") != case["symbol"] or
                         item.get("signal_date") != case["signal_date"]):
                raise ValueError(f"Trend identity mismatch for {cid}: {metric}")
            if item and item.get("status") == "CANDIDATE_YOY":
                for field in ("latest_filed", "previous_filed"):
                    if not item.get(field) or date.fromisoformat(item[field]) >= date.fromisoformat(case["signal_date"]):
                        raise ValueError(f"Point-in-time violation for {cid}: {metric}/{field}")
            signal, reason = metric_signal(item)
            parts[metric] = "MISSING" if signal is None else ("POSITIVE" if signal > 0 else "NEGATIVE" if signal < 0 else "NEUTRAL")
            notes.append(f"{metric}:{reason}")
            if signal is not None:
                available_weight += WEIGHTS[metric]
                weighted += (signal + 1) / 2 * WEIGHTS[metric]
        # Score is explicitly unavailable unless all three metrics are comparable.
        complete = available_weight == 100
        result.append({
            "case_id": cid, "symbol": case["symbol"], "market": case["market"],
            "signal_date": case["signal_date"],
            "quality_score": round(weighted, 2) if complete else "",
            "coverage_pct": available_weight,
            "quality_status": "EXPERIMENTAL_COMPLETE" if complete else "INSUFFICIENT_COVERAGE",
            "event_risk_status": "NOT_RESEARCHED",
            "revenue_signal": parts["revenue"],
            "net_income_signal": parts["net_income"],
            "operating_cash_flow_signal": parts["operating_cash_flow"],
            "notes": "; ".join(notes),
        })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental v6 financial quality score")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--trends", default=".cache/v6_financial_trends.csv")
    parser.add_argument("--output", default=".cache/v6_financial_quality.csv")
    parser.add_argument("--summary", default=".cache/v6_financial_quality_summary.json")
    args = parser.parse_args(argv)
    def load(path):
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream))
    cases, trends = load(args.cases), load(args.trends)
    rows = score_cases(cases, trends)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {"cases": len(rows), "quality_status": dict(Counter(r["quality_status"] for r in rows)),
               "event_risk": "NOT_RESEARCHED",
               "methodology": "Exploratory, unvalidated. No outcomes used. Missing data never scores as negative.",
               "weights": WEIGHTS, "signal_threshold": "5% YoY for comparable positive-base values",
               "score_range": [0, 100], "trade_recommendations": False}
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Quality research: {len(rows)} cases, {summary['quality_status']}")
    print(f"Saved: {args.output} and {args.summary}")


if __name__ == "__main__":
    main()
