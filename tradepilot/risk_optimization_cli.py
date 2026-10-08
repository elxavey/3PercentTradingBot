"""Phase 4.7: stop sensitivity research (no trading)."""
from __future__ import annotations
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from math import isfinite
from data_fetcher import get_price_history
from tradepilot.backtest_compare_cli import normalize_symbols
from tradepilot.backtest_validation import validated_backtest
from tradepilot.exploratory_backtest import exploratory_backtest
from tradepilot.historical_simulator import SimulationPolicy
from tradepilot.storage.database import DEFAULT_DB_PATH

STOPS = (1.8, 2.5, 3.0)

def risk_budget(capital=10000.0, risk_pct=1.0, stop_pct=2.5,
                fee=0.0025, slippage=0.001):
    values = (capital, risk_pct, stop_pct, fee, slippage)
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v) for v in values):
        raise ValueError("invalid numeric input")
    if capital <= 0 or not 0 < risk_pct <= 5 or not 0 < stop_pct < 100 or fee <= 0 or slippage <= 0 or fee + slippage >= 1:
        raise ValueError("invalid risk parameters")
    loss = 1 - (1 - stop_pct / 100) * (1 - slippage) * (1 - fee) / (1 + fee)
    allocation = min(capital, capital * risk_pct / 100 / loss)
    return {"stop_pct": stop_pct, "risk_budget_mxn": round(capital * risk_pct / 100, 2),
            "allocation_mxn": round(allocation, 2),
            "planned_stop_loss_mxn": round(allocation * loss, 2),
            "gap_risk_unbounded": True}

def latest_scan_symbols(limit=62, db_path=DEFAULT_DB_PATH):
    if not 1 <= limit <= 62:
        raise ValueError("limit must be 1..62")
    with sqlite3.connect(str(db_path)) as conn:
        scan = conn.execute("SELECT id FROM scan_runs WHERE status='SUCCEEDED' ORDER BY finished_at_utc DESC, id DESC LIMIT 1").fetchone()
        if not scan:
            raise ValueError("no successful scan found")
        names = [row[0] for row in conn.execute(
            "SELECT symbol FROM scan_candidates WHERE scan_run_id=? ORDER BY symbol LIMIT ?",
            (scan[0], limit))]
    return normalize_symbols(names)

def evaluate(symbols, *, fee, slippage, capital=10000.0, risk_pct=1.0,
             strict=False, fetcher=None, runner=None, as_of_utc=None):
    names = normalize_symbols(symbols)
    now = as_of_utc or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("timezone-aware date required")
    budgets = [risk_budget(capital, risk_pct, stop, fee, slippage) for stop in STOPS]
    fetcher = fetcher or get_price_history
    runner = runner or (validated_backtest if strict else exploratory_backtest)
    rows = []
    for symbol in names:
        market = "MX" if symbol.endswith(".MX") else "US"
        try:
            history = fetcher(symbol, period="2y")
        except Exception as exc:
            rows.append({"symbol": symbol, "status": "ERROR", "error": str(exc)[:160]})
            continue
        scenarios = []
        for stop in STOPS:
            try:
                policy = SimulationPolicy(stop_pct=stop, fee_rate_per_side=fee,
                                          slippage_rate_per_side=slippage)
                result = runner(history, symbol=symbol, market=market,
                                as_of_utc=now, simulation_policy=policy)
                if result["state"] != "RESEARCH_RESULT":
                    scenarios.append({"stop_pct": stop, "status": "REJECT",
                                      "reasons": result.get("reasons", [])})
                    continue
                report = result["backtest"]
                reasons = {}
                for trade in report["trades"]:
                    key = trade["exit_reason"]
                    reasons[key] = reasons.get(key, 0) + 1
                scenarios.append({"stop_pct": stop, "status": "RESEARCH_RESULT",
                                  "validation": result["validation"]["state"],
                                  "metrics": report["metrics"], "exit_reasons": reasons})
            except Exception as exc:
                scenarios.append({"stop_pct": stop, "status": "ERROR", "error": str(exc)[:160]})
        rows.append({"symbol": symbol, "market": market, "scenarios": scenarios})
    summary = []
    for i, stop in enumerate(STOPS):
        cases = [case for row in rows for case in row.get("scenarios", [])
                 if case["stop_pct"] == stop and case["status"] == "RESEARCH_RESULT"]
        n = sum(c["metrics"]["closed_trades"] for c in cases)
        wins = sum(c["metrics"]["wins"] for c in cases)
        net = sum(c["metrics"]["average_net_return_pct"] * c["metrics"]["closed_trades"]
                  for c in cases if c["metrics"]["closed_trades"])
        summary.append({"stop_pct": stop, "validated_symbols": len(cases),
                        "closed_trades": n, "wins": wins,
                        "win_rate_pct": round(100 * wins / n, 4) if n else None,
                        "mean_net_return_pct": round(net / n, 4) if n else None,
                        "risk": budgets[i]})
    return {"state": "SENSITIVITY_RESEARCH", "summaries": summary,
            "results": rows, "research_only": True, "actionable": False,
            "selected_stop": None,
            "limitations": ["NO_OUT_OF_SAMPLE_VALIDATION", "NO_PORTFOLIO_BACKTEST",
                            "GAP_LOSSES_MAY_EXCEED_BUDGET", "NO_EODHD_CALLS"]}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Stop sensitivity research")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--symbols", nargs="+")
    source.add_argument("--watchlist", action="store_true")
    source.add_argument("--universe", action="store_true")
    parser.add_argument("--limit", type=int, default=62)
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--risk-pct", type=float, default=1.0)
    parser.add_argument("--fee", type=float, required=True)
    parser.add_argument("--slippage", type=float, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 62:
        parser.error("limit must be 1..62")
    if args.universe:
        symbols = latest_scan_symbols(args.limit)
    elif args.watchlist:
        from tradepilot.watchlist import list_watchlist
        symbols = [row["symbol"] for row in list_watchlist()
                   if row["state"] in ("WATCHING", "PROMOTED")][:args.limit]
    else:
        symbols = args.symbols
    result = evaluate(symbols, fee=args.fee, slippage=args.slippage,
                      capital=args.capital, risk_pct=args.risk_pct, strict=args.strict)
    print(json.dumps(result, indent=2, default=str, allow_nan=False))
    return 0 if all(s["status"] == "RESEARCH_RESULT"
                    for row in result["results"] for s in row.get("scenarios", [])) else 2

if __name__ == "__main__":
    raise SystemExit(main())
