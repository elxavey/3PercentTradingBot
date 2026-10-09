"""Phase 4.9: offline diagnostics for the saved Phase 4.8 matrix.

No market-data calls, strategy modifications, orders, or scenario selection.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def aggregate(cases):
    """Pool closed trades, never average per-symbol percentages unweighted."""
    trades = sum(int(c["metrics"]["closed_trades"]) for c in cases)
    wins = sum(int(c["metrics"]["wins"]) for c in cases)
    weighted = sum(float(c["metrics"]["average_net_return_pct"]) *
                   int(c["metrics"]["closed_trades"]) for c in cases
                   if c["metrics"]["closed_trades"] and
                   c["metrics"]["average_net_return_pct"] is not None)
    exits = Counter()
    for c in cases:
        exits.update(c.get("exit_reasons", {}))
    return {
        "symbols": len(cases),
        "closed_trades": trades,
        "wins": wins,
        "win_rate_pct": round(100 * wins / trades, 4) if trades else None,
        "mean_net_return_pct": round(weighted / trades, 4) if trades else None,
        "exit_reasons": dict(sorted(exits.items())),
        "exit_reason_pct": {k: round(100 * v / trades, 4) if trades else None
                            for k, v in sorted(exits.items())},
    }


def analyze(report, *, min_trades=10):
    if report.get("state") != "HOLDING_SENSITIVITY_RESEARCH":
        raise ValueError("expected Phase 4.8 HOLDING_SENSITIVITY_RESEARCH report")
    if not isinstance(min_trades, int) or min_trades < 1:
        raise ValueError("min_trades must be positive integer")
    rows = report.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError("no per-symbol results; supply full JSON, not console summary")
    combinations = sorted({(c["stop_pct"], c["holding_sessions"])
                           for r in rows for c in r.get("scenarios", [])
                           if c.get("status") == "RESEARCH_RESULT"})
    if not combinations:
        raise ValueError("no successful scenarios")
    scenario_reports = []
    for stop, holding in combinations:
        selected = []
        rejected = []
        for r in rows:
            matches = [c for c in r.get("scenarios", [])
                       if c.get("stop_pct") == stop and c.get("holding_sessions") == holding]
            if len(matches) != 1 or matches[0].get("status") != "RESEARCH_RESULT":
                rejected.append(r["symbol"])
                continue
            selected.append((r, matches[0]))
        by_market = {
            market: aggregate([c for r, c in selected if r["market"] == market])
            for market in ("MX", "US")
        }
        instrument_rows = []
        for r, c in selected:
            metrics = c["metrics"]
            instrument_rows.append({
                "symbol": r["symbol"], "market": r["market"],
                "history_validation": c.get("validation"),
                "closed_trades": metrics["closed_trades"],
                "wins": metrics["wins"],
                "win_rate_pct": metrics["win_rate_pct"],
                "mean_net_return_pct": metrics["average_net_return_pct"],
                "profit_factor": metrics.get("profit_factor"),
                "exit_reasons": c.get("exit_reasons", {}),
            })
        ranked = [r for r in instrument_rows if r["closed_trades"] >= min_trades
                  and r["mean_net_return_pct"] is not None]
        ranked.sort(key=lambda r: (-r["mean_net_return_pct"], r["symbol"]))
        scenario_reports.append({
            "stop_pct": stop, "holding_sessions": holding,
            "all": aggregate([c for _, c in selected]),
            "by_market": by_market,
            "rejected_symbols": rejected,
            "instruments": instrument_rows,
            "ranking_min_trades": min_trades,
            "ranked_best": ranked[:10],
            "ranked_worst": list(reversed(ranked[-10:])),
            "insufficient_sample_symbols": [
                r["symbol"] for r in instrument_rows if r["closed_trades"] < min_trades
            ],
        })
    return {
        "state": "ENTRY_DIAGNOSTICS_RESEARCH",
        "source": "PHASE_4_8_SAVED_JSON",
        "symbols": len(rows),
        "scenarios": scenario_reports,
        "research_only": True, "actionable": False,
        "selected_scenario": None,
        "limitations": [
            "IN_SAMPLE_ONLY_NO_OUT_OF_SAMPLE",
            "NO_ENTRY_TIME_FEATURES_IN_PHASE_4_8_REPORT",
            "EXIT_REASONS_ARE_COUNTS_NOT_CAUSAL_EXPLANATIONS",
            "NO_PORTFOLIO_EQUITY_OR_FX",
            "NO_MULTIPLE_TESTING_CORRECTION",
            "SMALL_INSTRUMENT_TRADE_SAMPLES",
            "PER_SYMBOL_RETURNS_ARE_NOT_POSITION_WEIGHTED",
            "NO_NEW_MARKET_DATA_OR_EODHD_CALLS",
        ],
        "next_research": [
            "Capture point-in-time entry features during historical replay",
            "Compare predeclared filters on chronological out-of-sample data",
            "Do not pick an optimal scenario from in-sample performance alone",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline Phase 4.9 diagnostics")
    parser.add_argument("--input", default="phase_4_8_results_complete.json")
    parser.add_argument("--output", default="phase_4_9_diagnostics.json")
    parser.add_argument("--min-trades", type=int, default=10)
    args = parser.parse_args(argv)
    source = Path(args.input)
    report = json.loads(source.read_text(encoding="utf-8"))
    result = analyze(report, min_trades=args.min_trades)
    destination = Path(args.output)
    if destination.resolve() == source.resolve():
        parser.error("output must differ from input")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Source: {source.resolve()}")
    print(f"Saved: {destination.resolve()}")
    print(f"Symbols: {result['symbols']} | scenarios: {len(result['scenarios'])}")
    print("stop hold | MX trades net% | US trades net% | ALL trades net% | rejects")
    for row in result["scenarios"]:
        mx, us, all_ = row["by_market"]["MX"], row["by_market"]["US"], row["all"]
        fmt = lambda v: f"{v:+.4f}" if v is not None else "N/A"
        print(f"{row['stop_pct']:4.1f} {row['holding_sessions']:4d} | "
              f"{mx['closed_trades']:3d} {fmt(mx['mean_net_return_pct']):>8} | "
              f"{us['closed_trades']:3d} {fmt(us['mean_net_return_pct']):>8} | "
              f"{all_['closed_trades']:3d} {fmt(all_['mean_net_return_pct']):>8} | "
              f"{len(row['rejected_symbols'])}")
    print("Detailed exit reasons and eligible per-symbol rankings are in the saved JSON.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
