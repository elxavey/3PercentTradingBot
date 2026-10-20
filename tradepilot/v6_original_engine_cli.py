"""Research-only evaluation of scanner-selected symbols using existing engines."""
import argparse
import json
from datetime import date, datetime, time, timezone
from pathlib import Path

from tradepilot.v6_actual_scanner_report_cli import report
from tradepilot.v6_cached_history_bridge import load_cached_history
from tradepilot.breakout_confirmation import confirm_breakout
from tradepilot.breakout_session_quality import assess_daily_sessions
from tradepilot.breakout_trade_plan import build_trade_plan
from tradepilot.technical_setup import derive_levels


def evaluate(db, as_of, top=20):
    ranked, scanner = report(db, as_of, limit=top)
    rows = []
    for candidate in ranked:
        symbol = candidate["symbol"]
        market = str(candidate["exchange_code"]).upper()
        row = {"symbol": symbol, "market": market, "state": "REJECT",
               "reason": "", "plan": None}
        history, error = load_cached_history(symbol)
        if error:
            row["reason"] = error
        elif market not in ("US", "MX"):
            row["reason"] = "UNKNOWN_MARKET"
        else:
            day = date.fromisoformat(as_of)
            history = history.loc[history.index.date <= day]
            if history.empty or history.index[-1].date() != day:
                row["reason"] = "NO_REQUESTED_SESSION_BAR"
            else:
                try:
                    quality = assess_daily_sessions(
                        history, market=market,
                        as_of_utc=datetime.combine(day, time(23, 59), tzinfo=timezone.utc))
                    if quality["state"] != "CURRENT":
                        row["reason"] = "SESSION_" + quality.get("reason", quality["state"])
                    else:
                        row["state"] = "WATCHING"
                        confirmation = confirm_breakout(history)
                        if confirmation["state"] != "HISTORICAL_FILTERS_PASSED":
                            row["reason"] = confirmation["state"]
                        else:
                            levels = derive_levels(history.iloc[:-1])
                            if levels["state"] != "LEVELS_DERIVED":
                                row["reason"] = "INVALID_LEVELS"
                            else:
                                row["plan"] = build_trade_plan({
                                    "reference_close": float(history["Close"].iloc[-1]),
                                    "breakout_trigger": float(confirmation["resistance"]) * 1.001,
                                    "structural_stop_reference": levels["structural_stop"]})
                                row["reason"] = "UNVERIFIED_CACHED_HISTORY"
                except (ValueError, TypeError, KeyError) as exc:
                    row["reason"] = "ENGINE_ERROR_" + type(exc).__name__
        rows.append(row)
    return {"scanner_status": scanner["status"], "as_of": as_of,
            "ready": 0, "research_only": True, "candidates": rows}


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
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
