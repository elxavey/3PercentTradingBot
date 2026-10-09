"""Audit a completed dual-radar JSON. No network, trading, or emails."""
from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path


def summarize(report):
    rows = report.get("results") or []
    rebounds = report.get("rebound_results") or []
    requested = report.get("requested", 0)
    markets = {}
    for market in ("MX", "US"):
        in_market = lambda row: str(row.get("symbol", "")).endswith(".MX") == (market == "MX")
        breakout = [r for r in rows if in_market(r)]
        rebound = [r for r in rebounds if in_market(r)]
        def states(data):
            return dict(sorted(Counter(r.get("state", "UNKNOWN") for r in data).items()))
        def reasons(data):
            return dict(Counter(r.get("reason", "UNKNOWN") for r in data
                                if r.get("state") in ("REJECT", "ERROR")).most_common(12))
        def risk(data):
            return dict(sorted(Counter(r.get("risk_assessment", "NOT_EVALUATED")
                                       for r in data if r.get("state") not in ("REJECT", "ERROR")).items()))
        markets[market] = {
            "breakout": {"reviewed":len(breakout),"states":states(breakout),
                         "rejections":reasons(breakout),"risk":risk(breakout)},
            "rebound": {"reviewed":len(rebound),"states":states(rebound),
                        "rejections":reasons(rebound),"risk":risk(rebound)},
        }
    errors = []
    if requested != len(rows) or requested != len(rebounds):
        errors.append("COVERAGE_MISMATCH")
    if len({r.get("symbol") for r in rows}) != len(rows):
        errors.append("DUPLICATE_BREAKOUT_SYMBOLS")
    if {r.get("symbol") for r in rows} != {r.get("symbol") for r in rebounds}:
        errors.append("STRATEGY_SYMBOL_MISMATCH")
    for market, m in (report.get("markets") or {}).items():
        for strategy, group in (("breakout", m), ("rebound", m.get("rebounds") or {})):
            for row in group.get("primary") or []:
                expected = "CONFIRMED_RESEARCH" if strategy == "breakout" else "REBOUND_CONFIRMED_RESEARCH"
                if row.get("state") != expected or row.get("risk_assessment") != "RISK_ACCEPTABLE_FOR_RESEARCH":
                    errors.append("INVALID_PRIMARY_" + market + "_" + strategy + "_" + str(row.get("symbol")))
                if (row.get("session_quality") or {}).get("state") != "CURRENT":
                    errors.append("STALE_PRIMARY_" + market + "_" + strategy + "_" + str(row.get("symbol")))
            if len(group.get("primary") or []) > 10 or len(group.get("watch") or []) > 3:
                errors.append("REPORT_LIMIT_EXCEEDED_" + market + "_" + strategy)
    return {"requested":requested,"breakout_rows":len(rows),"rebound_rows":len(rebounds),
            "coverage_pct":round(100 * len(rows)/requested,2) if requested else 0,
            "markets":markets,"validation_errors":errors,"passed":not errors,
            "notes":["Quality/coverage validation only; not a profitable-strategy backtest.",
                     "No intraday quotes or order execution."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit completed TradePilot research JSON")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = summarize(report)
    path = Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    print("Validation: " + ("PASS" if summary["passed"] else "FAIL"))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
