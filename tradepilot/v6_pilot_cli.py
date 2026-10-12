"""Reproducible v6 pilot selection from historical v5 research JSON.

Selection is descriptive and stratified by market, strategy, and fixed-stop
outcome. Outcome labels are used ONLY to build a retrospective research sample;
they must never be used as live trading features.
"""
import argparse
import csv
import json
from pathlib import Path

GROUPS = (("MX", "BREAKOUT"), ("MX", "REBOUND"), ("US", "BREAKOUT"), ("US", "REBOUND"))
OUTCOMES = ("STOP", "TARGET")
FIELDS = ("case_id", "symbol", "market", "strategy", "signal_date",
          "entry_date", "fixed_outcome", "structural_outcome",
          "no_stop_outcome", "fixed_net_pct", "fixed_sessions",
          "no_stop_sessions", "no_stop_drawdown_pct",
          "evidence_status", "evidence_count", "research_notes")


def select_cases(payload, per_outcome=6):
    if per_outcome < 1:
        raise ValueError("per_outcome must be positive")
    records = payload.get("signals")
    if not isinstance(records, list):
        raise ValueError("Input must contain a signals array")
    pools = {}
    for market, strategy in GROUPS:
        for outcome in OUTCOMES:
            rows = [r for r in records
                    if r.get("market") == market and r.get("strategy") == strategy
                    and isinstance(r.get("exit_comparison"), dict)
                    and r["exit_comparison"].get("FIXED_3PCT", {}).get("outcome") == outcome
                    and r.get("entry_date") and r.get("signal_date")]
            pools[(market, strategy, outcome)] = sorted(
                rows, key=lambda r: (r["signal_date"], r["symbol"], r["entry_date"]))
    selected = []
    selected_ids = set()
    used_symbols = set()
    for outcome in OUTCOMES:
        chosen = []
        # First cover every market x strategy, then balance markets.
        for market, strategy in GROUPS:
            candidates = pools[(market, strategy, outcome)]
            candidate = next((r for r in candidates if r["symbol"] not in used_symbols), None)
            if candidate is None and candidates:
                candidate = candidates[0]
            if candidate is not None and len(chosen) < per_outcome:
                chosen.append(candidate)
                selected_ids.add((candidate["symbol"], candidate["strategy"], candidate["signal_date"]))
                used_symbols.add(candidate["symbol"])
        while len(chosen) < per_outcome:
            market_counts = {m: sum(r["market"] == m for r in chosen) for m in ("MX", "US")}
            candidates = [r for r in records if r.get("market") in market_counts
                          and isinstance(r.get("exit_comparison"), dict)
                          and r["exit_comparison"].get("FIXED_3PCT", {}).get("outcome") == outcome
                          and r.get("entry_date") and r.get("signal_date")
                          and (r["symbol"], r["strategy"], r["signal_date"]) not in selected_ids]
            if not candidates:
                break
            candidates.sort(key=lambda r: (market_counts[r["market"]],
                                           r["symbol"] in used_symbols,
                                           r["signal_date"], r["symbol"], r["strategy"]))
            candidate = candidates[0]
            chosen.append(candidate)
            selected_ids.add((candidate["symbol"], candidate["strategy"], candidate["signal_date"]))
            used_symbols.add(candidate["symbol"])
        selected.extend(chosen)
    result = []
    for index, r in enumerate(selected, 1):
        comparisons = r["exit_comparison"]
        fixed = comparisons["FIXED_3PCT"]
        no_stop = comparisons.get("NO_STOP", {})
        result.append({
            "case_id": f"V6-{index:03d}", "symbol": r["symbol"],
            "market": r["market"], "strategy": r["strategy"],
            "signal_date": r["signal_date"], "entry_date": r["entry_date"],
            "fixed_outcome": fixed["outcome"],
            "structural_outcome": comparisons.get("STRUCTURAL", {}).get("outcome"),
            "no_stop_outcome": no_stop.get("outcome"),
            "fixed_net_pct": fixed.get("net_pct"),
            "fixed_sessions": fixed.get("sessions_held"),
            "no_stop_sessions": no_stop.get("sessions_held"),
            "no_stop_drawdown_pct": no_stop.get("max_drawdown_before_exit_pct_excluding_entry_bar"),
            "evidence_status": "NOT_RESEARCHED", "evidence_count": 0,
            "research_notes": "",
        })
    return result


def write_pilot(payload, output_dir, per_outcome=6):
    rows = select_cases(payload, per_outcome)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "v6_pilot_cases.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    evidence = {
        "schema_version": 1,
        "methodology": "Retrospective case-control sample; NOT predictive validation.",
        "cutoff_rule": "Only evidence publicly available by the close of the signal session; exact timestamp required for same-day releases.",
        "cases": [{"case_id": r["case_id"], "symbol": r["symbol"],
                   "signal_date": r["signal_date"], "evidence": [],
                   "review_status": "NOT_RESEARCHED"} for r in rows],
        "evidence_fields": {
            "category": "EARNINGS|DIVIDEND|M_AND_A|GUIDANCE|DEBT|REGULATORY|OTHER",
            "headline": "Verifiable fact, not a prediction",
            "source_url": "Primary source URL",
            "published_at": "ISO 8601 timestamp with timezone, if available",
            "available_by_signal_close": "true|false|unknown",
            "assessment": "FAVORABLE|RISK|NEUTRAL|UNCERTAIN",
            "notes": "Why this fact could matter; do not use future outcome",
        },
    }
    json_path = output_dir / "v6_evidence.json"
    if not json_path.exists():
        json_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rows, csv_path, json_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build retrospective TradePilot v6 pilot")
    parser.add_argument("--input", required=True, help="Path to historical_v5.json")
    parser.add_argument("--output-dir", default=".cache")
    parser.add_argument("--per-outcome", type=int, default=6)
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    rows, csv_path, json_path = write_pilot(payload, args.output_dir, args.per_outcome)
    print(f"Selected {len(rows)} cases: {sum(r['fixed_outcome']=='STOP' for r in rows)} STOP, "
          f"{sum(r['fixed_outcome']=='TARGET' for r in rows)} TARGET")
    if len(rows) < args.per_outcome * 2:
        print("WARNING: insufficient eligible cases for requested sample size")
    print(f"Cases: {csv_path}")
    print(f"Evidence template: {json_path}")


if __name__ == "__main__":
    main()
