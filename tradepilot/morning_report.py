"""Market-separated daily research report with strict principal/watch tiers."""
from __future__ import annotations
from datetime import datetime, timezone
from time import perf_counter
from tradepilot.breakout_shortlist_cli import analyze_symbol
from data_fetcher import get_price_history

PRIMARY = "CONFIRMED_RESEARCH"
WATCH = ("BREAKOUT_PENDING_CONFIRMATION", "APPROACHING")
MIN_REWARD_RISK = 1.0  # Provisional research gate; not empirically optimized.


def risk_label(row):
    plan = row.get("trade_plan") or {}
    ratio = plan.get("reward_risk_net")
    if plan.get("plan_state") != "ILLUSTRATIVE_UNTRIGGERED" or not isinstance(ratio, (int, float)):
        return "RISK_UNAVAILABLE"
    return "RISK_ACCEPTABLE_FOR_RESEARCH" if ratio >= MIN_REWARD_RISK else "UNFAVORABLE_RISK_REWARD"



def run_market_report(symbols, *, fetcher=None, as_of_utc=None, progress=None,
                      primary_limit=10, watch_limit=3):
    if not 1 <= primary_limit <= 10 or not 0 <= watch_limit <= 3:
        raise ValueError("limits exceed report policy")
    now = as_of_utc or datetime.now(timezone.utc)
    fetch = fetcher or get_price_history
    requested = list(dict.fromkeys(symbols))
    rows = []
    timings = []
    started = perf_counter()
    for i, symbol in enumerate(requested, 1):
        t = perf_counter()
        try:
            history = fetch(symbol, period="6mo")
            row = analyze_symbol(symbol, history, as_of_utc=now,
                                 min_turnover=5_000_000 if symbol.endswith(".MX") else 10_000_000)
        except Exception as exc:
            row = {"symbol": symbol, "state": "ERROR",
                   "reason": type(exc).__name__, "detail": str(exc)[:160], "actionable": False}
        if row.get("state") in (PRIMARY, *WATCH):
            row["risk_assessment"] = risk_label(row)
        rows.append(row)
        timings.append(perf_counter() - t)
        if progress:
            progress(i, len(requested), symbol, row["state"])
    markets = {}
    for market in ("MX", "US"):
        local = [r for r in rows if r["symbol"].endswith(".MX") == (market == "MX")]
        valid = [r for r in local if (r.get("session_quality") or {}).get("state") == "CURRENT"]
        primary = sorted((r for r in valid if r["state"] == PRIMARY and r.get("risk_assessment") == "RISK_ACCEPTABLE_FOR_RESEARCH"),
                         key=lambda r: (-r["quality_score"], r["symbol"]))[:primary_limit]
        watch = sorted((r for r in valid if r["state"] in WATCH or (r["state"] == PRIMARY and r.get("risk_assessment") != "RISK_ACCEPTABLE_FOR_RESEARCH")),
                       key=lambda r: (-r["quality_score"], r["symbol"]))[:watch_limit]
        markets[market] = {"reviewed": len(local), "current": len(valid),
                           "primary": primary, "watch": watch,
                           "risk_filtered": sum(r["state"] == PRIMARY and r.get("risk_assessment") != "RISK_ACCEPTABLE_FOR_RESEARCH" for r in valid),
                           "rejected_or_error": sum(r["state"] in ("REJECT", "ERROR") for r in local)}
    elapsed = perf_counter() - started
    return {"state": "DAILY_RESEARCH_REPORT", "as_of_utc": now.isoformat(),
            "markets": markets, "results": rows, "requested": len(requested),
            "completed": len(rows), "elapsed_seconds": round(elapsed, 3),
            "fetch_and_analysis_seconds": round(sum(timings), 3),
            "mean_symbol_seconds": round(sum(timings) / len(timings), 3) if timings else None,
            "estimated_1000_seconds_linear": round(elapsed * 1000 / len(requested), 1) if requested else None,
            "risk_policy": {"min_reward_risk": MIN_REWARD_RISK, "status": "PROVISIONAL_NOT_BACKTEST_VALIDATED"},
            "research_only": True, "actionable": False,
            "limitations": ["EOD_ONLY_NOT_INTRADAY", "NO_VERIFIED_LIVE_QUOTE",
                            "NO_OOS_VALIDATION", "NO_AUTOMATED_BROKER_ORDERS",
                            "LINEAR_PROJECTION_NOT_BENCHMARK"]}
