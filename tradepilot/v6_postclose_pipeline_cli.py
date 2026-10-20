"""One-command post-close research pipeline from persisted dynamic scanner results.

Run the existing scheduled scanner first. This CLI never chooses tickers or
triggers broker orders. It abstains if no eligible completed scan exists.
"""
import argparse
import csv
import json
from datetime import date
from pathlib import Path

from tradepilot.v6_actual_scanner_report_cli import report
from tradepilot.v6_selected_history_refresh_cli import refresh
from tradepilot.v6_original_engine_cli import evaluate


def run(db, as_of, top=20, *, download=False):
    date.fromisoformat(as_of)
    if top < 1:
        raise ValueError("top must be positive")
    ranked, scanner = report(db, as_of, limit=top)
    result = {"as_of": as_of, "scanner": scanner, "selected": len(ranked),
              "refreshed": 0, "research_only": True, "orders_sent": 0,
              "status": "ABSTAIN", "candidates": []}
    if not ranked:
        result["reason"] = "NO_ELIGIBLE_POST_CLOSE_SCANNER_CANDIDATES"
        return result
    if download:
        update = refresh(db, as_of, top=top)
        result["refreshed"] = update["refreshed"]
        result["refresh_results"] = update["results"]
    technical = evaluate(db, as_of, top=top)
    result["candidates"] = technical["candidates"]
    result["status"] = "RESEARCH_ONLY"
    return result


def save(result, prefix):
    path = Path(prefix)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_path = Path(str(path) + ".json")
    csv_path = Path(str(path) + ".csv")
    json_path.write_text(json.dumps(result, indent=2, default=str, allow_nan=False) + "\n", encoding="utf-8")
    columns = ["symbol", "market", "scanner_rank", "scanner_score",
               "state", "reason", "actionable", "reference_close",
               "breakout_trigger", "structural_stop_reference",
               "quality_score"]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["candidates"])
    return str(json_path), str(csv_path)


def main(argv=None):
    p = argparse.ArgumentParser(description="Post-close TradePilot V6 research pipeline")
    p.add_argument("--db", default="data/tradepilot.db")
    p.add_argument("--as-of", required=True)
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--refresh", action="store_true",
                   help="Explicitly permit Yahoo downloads for eligible scanner symbols")
    p.add_argument("--prefix", default=".cache/v6_postclose")
    a = p.parse_args(argv)
    result = run(a.db, a.as_of, a.top, download=a.refresh)
    outputs = save(result, a.prefix)
    print(json.dumps({"status": result["status"], "selected": result["selected"],
                      "refreshed": result["refreshed"], "files": outputs,
                      "reason": result.get("reason"), "orders_sent": 0}, indent=2))


if __name__ == "__main__":
    main()
