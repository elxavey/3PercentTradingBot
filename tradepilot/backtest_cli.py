"""Run one validated historical research backtest from the Windows project root.

Example:
python -m tradepilot.backtest_cli --symbol ALSEA.MX --market MX --fee 0.0025 --slippage 0.001
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os

from data_fetcher import get_price_history
from tradepilot.exploratory_backtest import exploratory_backtest
from tradepilot.backtest_validation import validated_backtest
from tradepilot.historical_simulator import SimulationPolicy
from tradepilot.backtest_validation import validate_history
from tradepilot.history_recovery import recover_missing_sessions
from tradepilot.eodhd_source import verified_eodhd_daily, diagnose_eodhd_neighbors


def main(argv=None):
    parser = argparse.ArgumentParser(description="TradePilot validated historical research only")
    parser.add_argument("--symbol", default="ALSEA.MX")
    parser.add_argument("--market", choices=["MX", "US"], default="MX")
    parser.add_argument("--fee", type=float, required=True,
                        help="Assumed fraction per side, e.g. 0.0025 = 0.25%%")
    parser.add_argument("--slippage", type=float, required=True,
                        help="Assumed fraction per side, e.g. 0.001 = 0.1%%")
    parser.add_argument("--min-sessions", type=int, default=100)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="Require complete history; default is segmented exploratory mode")
    parser.add_argument("--use-eodhd", action="store_true",
                        help="Explicitly authorize limited EODHD recovery requests")
    parser.add_argument("--diagnose-eodhd", action="store_true",
                        help="Extra provider calls to diagnose rejected EODHD recovery")
    args = parser.parse_args(argv)
    if args.diagnose_eodhd and not args.use_eodhd:
        parser.error("--diagnose-eodhd requires --use-eodhd")
    if (args.market == "MX") != args.symbol.upper().endswith(".MX"):
        parser.error("market and .MX ticker suffix must agree")
    policy = SimulationPolicy(fee_rate_per_side=args.fee,
                              slippage_rate_per_side=args.slippage)
    now = datetime.now(timezone.utc)
    history = get_price_history(args.symbol, period="2y",
                                force_refresh=args.force_refresh)
    initial = validate_history(history, market=args.market, as_of_utc=now,
                               min_sessions=args.min_sessions)
    recovery = {"state": "NOT_NEEDED", "recovered": [], "unresolved": []}
    if args.strict and initial["state"] == "REJECT" and initial["reasons"] == ["MISSING_EXCHANGE_SESSIONS"]:
        history, recovery = recover_missing_sessions(
            history, initial["missing_sessions"], symbol=args.symbol)
    secondary = {"state": "NOT_NEEDED", "recovered": [], "unresolved": []}
    if recovery.get("unresolved"):
        if args.use_eodhd and os.getenv("EODHD_API_TOKEN"):
            def secondary_fetch(symbol, start, end):
                return verified_eodhd_daily(symbol, start, end, reference=history)
            history, secondary = recover_missing_sessions(
                history, recovery["unresolved"], symbol=args.symbol,
                fetcher=secondary_fetch)
            secondary["source"] = "EODHD_VERIFIED_NEIGHBOR_CLOSES"
        else:
            secondary = {"state": "NOT_CONFIGURED" if args.use_eodhd else "DISABLED_BY_DEFAULT",
                         "recovered": [], "unresolved": recovery["unresolved"]}
    runner = validated_backtest if args.strict else exploratory_backtest
    result = runner(history, symbol=args.symbol, market=args.market,
                    as_of_utc=now, simulation_policy=policy,
                    min_sessions=args.min_sessions)
    if result["state"] == "REJECT":
        diagnostic = None
        if args.diagnose_eodhd and args.use_eodhd and os.getenv("EODHD_API_TOKEN") and secondary.get("unresolved"):
            diagnostic = diagnose_eodhd_neighbors(
                args.symbol, secondary["unresolved"][0], reference=history)
        print(json.dumps({**result, "recovery": recovery,
                          "secondary_recovery": secondary,
                          "eodhd_diagnostic": diagnostic}, indent=2, default=str))
        return 2
    report = result["backtest"]
    print(json.dumps({
        "state": result["state"], "symbol": report["symbol"],
        "market": report["market"], "currency": report["currency"],
        "validation": result["validation"], "recovery": recovery,
        "secondary_recovery": secondary,
        "historical_sessions": report["historical_sessions"],
        "confirmed_signal_sessions": report["confirmed_signal_sessions"],
        "metrics": report["metrics"], "trades": report["trades"],
        "simulation_policy": report["simulation_policy"],
        "limitations": report["limitations"],
        "research_only": True,
        "excluded_segments": result.get("excluded_segments", 0),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
