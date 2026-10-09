"""Phase 4.8: research-only stop and holding-period sensitivity matrix."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
import time
from pathlib import Path

from data_fetcher import get_price_history
from tradepilot.backtest_compare_cli import normalize_symbols
from tradepilot.backtest_validation import validated_backtest
from tradepilot.exploratory_backtest import exploratory_backtest
from tradepilot.historical_simulator import SimulationPolicy
from tradepilot.risk_optimization_cli import latest_scan_symbols, risk_budget

STOPS = (1.8, 2.5, 3.0, 4.0)
HOLDING_SESSIONS = (5, 7, 10)


def evaluate_matrix(symbols, *, capital=10000.0, risk_pct=1.0,
                    fee=0.0025, slippage=0.001, strict=False,
                    fetcher=None, runner=None, as_of_utc=None, progress=None):
    names = normalize_symbols(symbols)
    if len(names) > 62:
        raise ValueError("maximum 62 symbols")
    now = as_of_utc or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("timezone-aware as_of_utc required")
    budgets = {stop: risk_budget(capital, risk_pct, stop, fee, slippage)
               for stop in STOPS}
    fetch = fetcher or get_price_history
    run = runner or (validated_backtest if strict else exploratory_backtest)
    rows = []
    started = time.monotonic()
    stamp = lambda: datetime.now().astimezone().isoformat(timespec="seconds")
    if progress:
        progress(f"Process started: {stamp()} | {len(names)} symbols | {len(STOPS)*len(HOLDING_SESSIONS)} scenarios")
    for idx, symbol in enumerate(names, 1):
        t0 = time.monotonic()
        market = "MX" if symbol.endswith(".MX") else "US"
        if progress:
            progress(f"[{idx}/{len(names)}] {symbol}: fetching history...")
        try:
            history = fetch(symbol, period="2y")
        except Exception as exc:
            rows.append({"symbol": symbol, "market": market, "status": "ERROR",
                         "error": str(exc)[:160], "scenarios": []})
            if progress:
                progress(f"[{idx}/{len(names)}] {symbol}: FETCH ERROR ({time.monotonic()-t0:.1f}s)")
            continue
        scenarios = []
        for stop in STOPS:
            for holding in HOLDING_SESSIONS:
                try:
                    policy = SimulationPolicy(stop_pct=stop,
                                              max_holding_sessions=holding,
                                              fee_rate_per_side=fee,
                                              slippage_rate_per_side=slippage)
                    result = run(history, symbol=symbol, market=market,
                                 as_of_utc=now, simulation_policy=policy)
                    case = {"stop_pct": stop, "holding_sessions": holding}
                    if result["state"] != "RESEARCH_RESULT":
                        case.update(status="REJECT", reasons=result.get("reasons", []))
                    else:
                        report = result["backtest"]
                        exits = {}
                        for trade in report["trades"]:
                            reason = trade["exit_reason"]
                            exits[reason] = exits.get(reason, 0) + 1
                        case.update(status="RESEARCH_RESULT",
                                    validation=result["validation"]["state"],
                                    metrics=report["metrics"], exit_reasons=exits)
                    scenarios.append(case)
                except Exception as exc:
                    scenarios.append({"stop_pct": stop, "holding_sessions": holding,
                                      "status": "ERROR", "error": str(exc)[:160]})
            if progress:
                progress(f"[{idx}/{len(names)}] {symbol}: stop {stop}% completed "
                         f"({time.monotonic()-t0:.1f}s)")
        rows.append({"symbol": symbol, "market": market, "scenarios": scenarios})
        if progress:
            ok = sum(c["status"] == "RESEARCH_RESULT" for c in scenarios)
            progress(f"[{idx}/{len(names)}] {symbol}: {ok}/12 research results "
                     f"({time.monotonic()-t0:.1f}s; total {time.monotonic()-started:.1f}s)")
    summaries = []
    for stop in STOPS:
        for holding in HOLDING_SESSIONS:
            cases = [c for row in rows for c in row["scenarios"]
                     if c["stop_pct"] == stop and c["holding_sessions"] == holding
                     and c["status"] == "RESEARCH_RESULT"]
            count = sum(c["metrics"]["closed_trades"] for c in cases)
            wins = sum(c["metrics"]["wins"] for c in cases)
            weighted_net = sum(c["metrics"]["average_net_return_pct"] *
                               c["metrics"]["closed_trades"] for c in cases
                               if c["metrics"]["closed_trades"])
            summaries.append({"stop_pct": stop, "holding_sessions": holding,
                              "validated_symbols": len(cases),
                              "closed_trades": count, "wins": wins,
                              "win_rate_pct": round(100*wins/count, 4) if count else None,
                              "mean_net_return_pct": round(weighted_net/count, 4) if count else None,
                              "risk": budgets[stop]})
    if progress:
        progress(f"Process finished: {stamp()} | elapsed {time.monotonic()-started:.1f}s")
    return {"state": "HOLDING_SENSITIVITY_RESEARCH",
            "started_as_of_utc": now.isoformat(), "symbols_requested": len(names),
            "summaries": summaries, "results": rows, "selected_scenario": None,
            "research_only": True, "actionable": False,
            "limitations": ["NO_OUT_OF_SAMPLE_VALIDATION", "NO_PORTFOLIO_BACKTEST",
                            "GAP_LOSSES_MAY_EXCEED_BUDGET", "NO_EODHD_CALLS",
                            "HISTORICAL_UNIVERSE_SURVIVORSHIP_RISK"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Phase 4.8 stop x holding research")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--universe", action="store_true")
    source.add_argument("--symbols", nargs="+")
    parser.add_argument("--limit", type=int, default=62)
    parser.add_argument("--capital", type=float, default=10000)
    parser.add_argument("--risk-pct", type=float, default=1)
    parser.add_argument("--fee", type=float, default=0.0025)
    parser.add_argument("--slippage", type=float, default=0.001)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", default="phase_4_8_results.json")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 62:
        parser.error("limit must be 1..62")
    symbols = latest_scan_symbols(args.limit) if args.universe else args.symbols[:args.limit]
    report = evaluate_matrix(symbols, capital=args.capital, risk_pct=args.risk_pct,
                             fee=args.fee, slippage=args.slippage, strict=args.strict,
                             progress=lambda s: print(s, file=sys.stderr, flush=True))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Results saved: {output.resolve()}")
    print(json.dumps({"state": report["state"], "summaries": report["summaries"],
                      "rejected_symbols": [r["symbol"] for r in report["results"]
                                           if any(c["status"] != "RESEARCH_RESULT"
                                                  for c in r["scenarios"]) or not r["scenarios"]},
                     indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
