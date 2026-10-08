"""Run one validated historical research backtest from the Windows project root.

Example:
python -m tradepilot.backtest_cli --symbol ALSEA.MX --market MX --fee 0.0025 --slippage 0.001
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json

from data_fetcher import get_price_history
from tradepilot.backtest_validation import validated_backtest
from tradepilot.historical_simulator import SimulationPolicy


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
    args = parser.parse_args(argv)
    if (args.market == "MX") != args.symbol.upper().endswith(".MX"):
        parser.error("market and .MX ticker suffix must agree")
    policy = SimulationPolicy(fee_rate_per_side=args.fee,
                              slippage_rate_per_side=args.slippage)
    now = datetime.now(timezone.utc)
    history = get_price_history(args.symbol, period="2y",
                                force_refresh=args.force_refresh)
    result = validated_backtest(history, symbol=args.symbol, market=args.market,
                                as_of_utc=now, simulation_policy=policy,
                                min_sessions=args.min_sessions)
    if result["state"] == "REJECT":
        print(json.dumps(result, indent=2, default=str))
        return 2
    report = result["backtest"]
    print(json.dumps({
        "state": result["state"], "symbol": report["symbol"],
        "market": report["market"], "currency": report["currency"],
        "validation": result["validation"],
        "historical_sessions": report["historical_sessions"],
        "confirmed_signal_sessions": report["confirmed_signal_sessions"],
        "metrics": report["metrics"], "trades": report["trades"],
        "simulation_policy": report["simulation_policy"],
        "limitations": report["limitations"],
        "research_only": True,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
