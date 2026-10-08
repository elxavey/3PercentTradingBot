"""Phase 4.6: read-only multi-symbol historical research comparison.

No EODHD calls, no automatic gap recovery, no orders or SQLite writes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from math import isfinite

from data_fetcher import get_price_history
from tradepilot.backtest_validation import validated_backtest
from tradepilot.exploratory_backtest import exploratory_backtest
from tradepilot.historical_simulator import SimulationPolicy

MIN_RANKED_TRADES = 10


def normalize_symbols(symbols: list[str]) -> list[str]:
    if not isinstance(symbols, list):
        raise ValueError("symbols must be a list")
    normalized = []
    seen = set()
    for value in symbols:
        if not isinstance(value, str):
            raise ValueError("invalid symbol")
        symbol = value.strip().upper()
        if not symbol or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^" for c in symbol):
            raise ValueError(f"invalid symbol: {value!r}")
        if symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    if not normalized or len(normalized) > 62:
        raise ValueError("provide 1 to 62 unique symbols")
    return normalized


def compare_symbols(symbols: list[str], *, simulation_policy: SimulationPolicy,
                    as_of_utc: datetime, strict: bool = False,
                    min_sessions: int = 100, fetcher=None) -> dict:
    """Compare identical simulation assumptions; never silently drop failures."""
    symbols = normalize_symbols(symbols)
    if not isinstance(simulation_policy, SimulationPolicy):
        raise TypeError("simulation policy required")
    if simulation_policy.fee_rate_per_side <= 0 or simulation_policy.slippage_rate_per_side <= 0:
        raise ValueError("positive fees and slippage required")
    if not isinstance(as_of_utc, datetime) or as_of_utc.utcoffset() is None:
        raise ValueError("timezone-aware as_of_utc required")
    fetcher = fetcher or get_price_history
    runner = validated_backtest if strict else exploratory_backtest
    rows = []
    for symbol in symbols:
        market = "MX" if symbol.endswith(".MX") else "US"
        try:
            history = fetcher(symbol, period="2y")
            result = runner(history, symbol=symbol, market=market,
                            as_of_utc=as_of_utc, simulation_policy=simulation_policy,
                            min_sessions=min_sessions)
            validation = result.get("validation", {})
            if result["state"] != "RESEARCH_RESULT":
                rows.append({"symbol": symbol, "market": market, "status": "REJECT",
                             "reasons": result.get("reasons", []),
                             "missing_sessions_count": validation.get("missing_sessions_count", 0),
                             "validation": validation.get("state", "REJECT"),
                             "rank_eligible": False})
                continue
            report = result["backtest"]
            metrics = report["metrics"]
            n = metrics["closed_trades"]
            rows.append({"symbol": symbol, "market": market, "status": "RESEARCH_RESULT",
                         "validation": validation["state"],
                         "historical_sessions": report["historical_sessions"],
                         "missing_sessions_count": validation.get("missing_sessions_count", 0),
                         "segments": validation.get("segments", 1),
                         "excluded_short_segments": validation.get("excluded_short_segments", 0),
                         "confirmed_signal_sessions": report["confirmed_signal_sessions"],
                         **metrics,
                         "rank_eligible": n >= MIN_RANKED_TRADES})
        except Exception as exc:
            rows.append({"symbol": symbol, "market": market, "status": "ERROR",
                         "reasons": [type(exc).__name__, str(exc)[:180]],
                         "rank_eligible": False})
    # Cross-symbol returns are trade-level percentages, not a combined portfolio.
    eligible = [r for r in rows if r["rank_eligible"]]
    eligible.sort(key=lambda r: (
        -r["average_net_return_pct"],
        -(r["profit_factor"] if r["profit_factor"] is not None else float("inf")),
        r["symbol"]))
    for i, row in enumerate(eligible, 1):
        row["rank"] = i
    # Preserve original symbol order in report, regardless of ranking.
    ranked = sorted(({"rank": r["rank"], "symbol": r["symbol"],
                      "average_net_return_pct": r["average_net_return_pct"],
                      "closed_trades": r["closed_trades"],
                      "win_rate_pct": r["win_rate_pct"],
                      "profit_factor": r["profit_factor"],
                      "max_closed_trade_drawdown_pct": r["max_closed_trade_drawdown_pct"]}
                     for r in eligible), key=lambda r: r["rank"])
    return {"state": "COMPARISON_RESULT", "mode": "STRICT" if strict else "EXPLORATORY",
            "as_of_utc": as_of_utc.isoformat(), "symbols_requested": len(symbols),
            "symbols_validated": sum(r["status"] == "RESEARCH_RESULT" for r in rows),
            "symbols_rejected": sum(r["status"] == "REJECT" for r in rows),
            "symbols_errored": sum(r["status"] == "ERROR" for r in rows),
            "min_ranked_trades": MIN_RANKED_TRADES,
            "ranking": ranked, "results": rows,
            "simulation_policy": {
                "target_gross_pct": simulation_policy.target_gross_pct,
                "stop_pct": simulation_policy.stop_pct,
                "max_holding_sessions": simulation_policy.max_holding_sessions,
                "fee_rate_per_side": simulation_policy.fee_rate_per_side,
                "slippage_rate_per_side": simulation_policy.slippage_rate_per_side},
            "research_only": True, "actionable": False,
            "limitations": ["NO_OUT_OF_SAMPLE_VALIDATION", "SMALL_SAMPLE_NOT_RANKED",
                            "PERCENT_RETURNS_NOT_A_COMBINED_PORTFOLIO",
                            "HISTORICAL_UNIVERSE_SURVIVORSHIP_NOT_VERIFIED",
                            "NO_EODHD_OR_MISSING_BAR_RECOVERY"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TradePilot multi-symbol research comparison")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--symbols", nargs="+", help="Ticker symbols, e.g. ALSEA.MX WALMEX.MX")
    source.add_argument("--watchlist", action="store_true", help="Read active local SQLite watchlist")
    parser.add_argument("--limit", type=int, default=12, help="Max watchlist symbols, 1 to 62")
    parser.add_argument("--fee", type=float, required=True)
    parser.add_argument("--slippage", type=float, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--min-sessions", type=int, default=100)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 62:
        parser.error("--limit must be 1..62")
    symbols = args.symbols
    if args.watchlist:
        from tradepilot.watchlist import list_watchlist
        symbols = [r["symbol"] for r in list_watchlist()
                   if r["state"] in ("WATCHING", "PROMOTED")][:args.limit]
        if not symbols:
            parser.error("no active symbols in local watchlist; use --symbols")
    policy = SimulationPolicy(fee_rate_per_side=args.fee,
                              slippage_rate_per_side=args.slippage)
    result = compare_symbols(symbols, simulation_policy=policy,
                             as_of_utc=datetime.now(timezone.utc),
                             strict=args.strict, min_sessions=args.min_sessions)
    print(json.dumps(result, indent=2, default=str, allow_nan=False))
    return 0 if result["symbols_rejected"] == 0 and result["symbols_errored"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
