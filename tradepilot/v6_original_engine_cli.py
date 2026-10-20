"""Evaluate only real, eligible scanner candidates with the original research engine.

The cutoff is the next UTC day so the requested completed session is retained.
No candidate is actionable; provider-finality and broker execution are not verified.
"""
import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from tradepilot.v6_actual_scanner_report_cli import report
from tradepilot.v6_cached_history_bridge import load_cached_history
from tradepilot.breakout_shortlist_cli import analyze_symbol
from tradepilot.breakout_session_quality import assess_daily_sessions


def evaluate(db, as_of, top=20):
    day = date.fromisoformat(as_of)
    if top < 1:
        raise ValueError("top must be positive")
    ranked, scanner = report(db, as_of, limit=top)
    rows = []
    # The existing analyzer excludes the UTC current day. Next-day cutoff
    # permits the requested session but still excludes future observations.
    cutoff = datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)
    for candidate in ranked:
        symbol = candidate["symbol"]
        market = str(candidate["exchange_code"]).upper()
        row = {"symbol": symbol, "market": market, "scanner_rank": candidate["rank"],
               "scanner_score": candidate["opportunity_score"],
               "state": "REJECT", "reason": "", "actionable": False}
        if market not in ("US", "MX"):
            row["reason"] = "UNKNOWN_MARKET"
            rows.append(row)
            continue
        if (symbol.endswith(".MX") and market != "MX") or (not symbol.endswith(".MX") and market != "US"):
            row["reason"] = "SYMBOL_MARKET_MISMATCH"
            rows.append(row)
            continue
        history, error = load_cached_history(symbol)
        if error:
            row["reason"] = error
            rows.append(row)
            continue
        history = history.loc[history.index.date <= day].copy()
        if history.empty or history.index[-1].date() != day:
            row["reason"] = "NO_REQUESTED_SESSION_BAR"
            rows.append(row)
            continue
        try:
            # Evaluate quality at the end of the requested UTC date. This
            # verifies exchange sessions, not finality of provider quotes.
            as_of = datetime.combine(day, time(23, 59), tzinfo=timezone.utc)
            quality = assess_daily_sessions(history, market=market, as_of_utc=as_of)
            if quality["state"] != "CURRENT":
                row["reason"] = "SESSION_" + str(quality.get("reason", quality["state"]))
            else:
                technical = analyze_symbol(symbol, history, as_of_utc=cutoff,
                                           min_turnover=5_000_000 if market == "MX" else 10_000_000)
                row.update(technical)
                row["reason"] = technical.get("reason", "RESEARCH_ONLY_UNVERIFIED_PROVIDER_FINALITY")
                row["actionable"] = False
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            row["state"] = "REJECT"
            row["reason"] = "ENGINE_ERROR_" + type(exc).__name__
        rows.append(row)
    return {"scanner_status": scanner["status"], "as_of": as_of,
            "ready": 0, "research_only": True, "actionable": False,
            "candidates": rows}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/tradepilot.db")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--output", default=".cache/v6_original_engine.json")
    args = parser.parse_args(argv)
    result = evaluate(args.db, args.as_of, args.top)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False, default=str))


if __name__ == "__main__":
    main()
