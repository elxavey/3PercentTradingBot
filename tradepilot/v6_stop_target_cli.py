"""Retrospective v6 STOP/TARGET score audit; outcomes used only for evaluation."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

THRESHOLDS = (25, 35, 50, 65, 75)
DETAIL_COLUMNS = ("case_id", "symbol", "market", "strategy", "fixed_outcome",
                  "signal_date", "quality_status", "quality_score", "coverage_pct",
                  "event_risk_status", "decision_at_50", "fixed_net_pct")
THRESHOLD_COLUMNS = ("threshold", "eligible_scored", "eligible_stop", "eligible_target",
                     "excluded_stop", "excluded_target", "retained_stop",
                     "retained_target", "unscored_stop", "unscored_target",
                     "excluded_stop_pct", "excluded_target_pct")


def analyze(cases, quality, thresholds=THRESHOLDS):
    by_id = {}
    for row in quality:
        cid = row["case_id"]
        if cid in by_id:
            raise ValueError(f"Duplicate quality case: {cid}")
        by_id[cid] = row
    if set(by_id) != {c["case_id"] for c in cases}:
        raise ValueError("Case IDs differ between pilot and quality data")
    details = []
    for case in cases:
        cid = case["case_id"]
        q = by_id[cid]
        if (q["symbol"] != case["symbol"] or
                q["signal_date"] != case["signal_date"] or
                q["market"] != case["market"]):
            raise ValueError(f"Identity mismatch for {cid}")
        outcome = case["fixed_outcome"]
        if outcome not in ("STOP", "TARGET"):
            raise ValueError(f"Unexpected FIXED_3PCT outcome for {cid}: {outcome}")
        complete = q["quality_status"] == "EXPERIMENTAL_COMPLETE"
        if complete:
            try:
                score = float(q["quality_score"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid score for {cid}") from exc
            import math
            if not math.isfinite(score) or not 0 <= score <= 100 or float(q["coverage_pct"]) != 100:
                raise ValueError(f"Invalid complete coverage/score for {cid}")
            decision = "EXCLUDE" if score < 50 else "RETAIN"
        else:
            if q["quality_score"] not in ("", None):
                raise ValueError(f"Incomplete case has score: {cid}")
            score, decision = None, "UNSCORED"
        details.append({
            "case_id": cid, "symbol": case["symbol"], "market": case["market"],
            "strategy": case["strategy"], "fixed_outcome": outcome,
            "signal_date": case["signal_date"], "quality_status": q["quality_status"],
            "quality_score": score if score is not None else "",
            "coverage_pct": q["coverage_pct"],
            "event_risk_status": q["event_risk_status"],
            "decision_at_50": decision, "fixed_net_pct": case["fixed_net_pct"],
        })
    sensitivity = []
    for threshold in thresholds:
        scored = [r for r in details if r["quality_score"] != ""]
        unscored = [r for r in details if r["quality_score"] == ""]
        excluded = [r for r in scored if r["quality_score"] < threshold]
        retained = [r for r in scored if r["quality_score"] >= threshold]
        count = lambda rows, outcome: sum(r["fixed_outcome"] == outcome for r in rows)
        stop = count(scored, "STOP")
        target = count(scored, "TARGET")
        excluded_stop, excluded_target = count(excluded, "STOP"), count(excluded, "TARGET")
        sensitivity.append({
            "threshold": threshold, "eligible_scored": len(scored),
            "eligible_stop": stop, "eligible_target": target,
            "excluded_stop": excluded_stop, "excluded_target": excluded_target,
            "retained_stop": count(retained, "STOP"),
            "retained_target": count(retained, "TARGET"),
            "unscored_stop": count(unscored, "STOP"),
            "unscored_target": count(unscored, "TARGET"),
            "excluded_stop_pct": round(100 * excluded_stop / stop, 2) if stop else None,
            "excluded_target_pct": round(100 * excluded_target / target, 2) if target else None,
        })
    summary = {
        "sample": {"total": len(details), "outcomes": dict(Counter(r["fixed_outcome"] for r in details)),
                   "scored": sum(r["quality_score"] != "" for r in details),
                   "unscored": sum(r["quality_score"] == "" for r in details)},
        "threshold_rule": "EXCLUDE when score < threshold; missing scores are UNSCORED, never automatically excluded",
        "primary_threshold": 50,
        "thresholds_exploratory_not_optimized": list(thresholds),
        "by_outcome": {
            outcome: {
                "total": sum(r["fixed_outcome"] == outcome for r in details),
                "scored": sum(r["fixed_outcome"] == outcome and r["quality_score"] != "" for r in details),
                "unscored": sum(r["fixed_outcome"] == outcome and r["quality_score"] == "" for r in details),
                "scores": [r["quality_score"] for r in details
                           if r["fixed_outcome"] == outcome and r["quality_score"] != ""],
            } for outcome in ("STOP", "TARGET")
        },
        "limitations": [
            "Retrospective case-control sample selected using known outcomes, not prospective validation.",
            "Financial score is experimental; thresholds and weights are not validated.",
            "Missing coverage is not a negative financial signal.",
            "No event-risk evidence has been evaluated.",
            "Scores must not be interpreted as success probabilities or trading recommendations.",
        ],
    }
    return details, sensitivity, summary


def write_csv(path, rows, columns):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Retrospective v6 STOP vs TARGET quality comparison")
    parser.add_argument("--cases", default=".cache/v6_pilot_cases.csv")
    parser.add_argument("--quality", default=".cache/v6_financial_quality.csv")
    parser.add_argument("--detail", default=".cache/v6_stop_target_comparison.csv")
    parser.add_argument("--sensitivity", default=".cache/v6_stop_target_thresholds.csv")
    parser.add_argument("--summary", default=".cache/v6_stop_target_summary.json")
    args = parser.parse_args(argv)
    def load(path):
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream))
    details, thresholds, summary = analyze(load(args.cases), load(args.quality))
    write_csv(args.detail, details, DETAIL_COLUMNS)
    write_csv(args.sensitivity, thresholds, THRESHOLD_COLUMNS)
    path = Path(args.summary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pilot: {summary['sample']}")
    for row in thresholds:
        print(f"Threshold {row['threshold']}: exclude {row['excluded_stop']} STOP / "
              f"{row['excluded_target']} TARGET; unscored "
              f"{row['unscored_stop']} STOP / {row['unscored_target']} TARGET")
    print("Exploratory retrospective audit only; no trading decisions.")


if __name__ == "__main__":
    main()
