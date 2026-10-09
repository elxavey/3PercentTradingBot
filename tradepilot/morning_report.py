"""Market-separated daily research report with strict principal/watch tiers."""
from __future__ import annotations
from datetime import datetime, timezone
from time import perf_counter
from tradepilot.breakout_shortlist_cli import analyze_symbol
from tradepilot.rebound_engine import analyze_rebound
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



def risk_diagnostics(row):
    """Explain the unchanged minimum 1.0 reward/risk threshold."""
    plan = row.get("trade_plan") or {}
    entry = plan.get("entry_reference")
    stop = plan.get("stop_reference")
    ratio = plan.get("reward_risk_net")
    if not all(isinstance(x, (int, float)) for x in (entry, stop, ratio)) or entry <= 0:
        return {"reason": "PLAN_UNAVAILABLE", "minimum_reward_risk": MIN_REWARD_RISK}
    return {"reason": "PASSED" if ratio >= MIN_REWARD_RISK else "STOP_TOO_WIDE_FOR_3_PERCENT_NET_TARGET",
            "minimum_reward_risk": MIN_REWARD_RISK, "reward_risk_net": ratio,
            "distance_entry_to_stop_pct": round(100 * (entry - stop) / entry, 3),
            "reward_risk_shortfall": round(max(0, MIN_REWARD_RISK - ratio), 3)}


def rebound_priority(row):
    return (-{"REBOUND_CONFIRMED_RESEARCH": 3, "REBOUND_SETUP": 2,
             "REBOUND_WATCH": 1}.get(row["state"], 0),
            -row["quality_score"], row["symbol"])


def run_market_report(symbols, *, fetcher=None, as_of_utc=None, progress=None,
                      primary_limit=10, watch_limit=3):
    if not 1 <= primary_limit <= 10 or not 0 <= watch_limit <= 3:
        raise ValueError("limits exceed report policy")
    now = as_of_utc or datetime.now(timezone.utc)
    fetch = fetcher or get_price_history
    requested = list(dict.fromkeys(symbols))
    rows = []
    rebound_rows = []
    timings = []
    started = perf_counter()
    for i, symbol in enumerate(requested, 1):
        t = perf_counter()
        try:
            history = fetch(symbol, period="6mo")
            rebound = analyze_rebound(symbol, history, as_of_utc=now)
            row = analyze_symbol(symbol, history, as_of_utc=now,
                                 min_turnover=5_000_000 if symbol.endswith(".MX") else 10_000_000)
        except Exception as exc:
            rebound = {"symbol": symbol, "state": "ERROR", "reason": type(exc).__name__, "actionable": False}
            row = {"symbol": symbol, "state": "ERROR",
                   "reason": type(exc).__name__, "detail": str(exc)[:160], "actionable": False}
        if row.get("state") in (PRIMARY, *WATCH):
            row["risk_assessment"] = risk_label(row)
            row["risk_diagnostics"] = risk_diagnostics(row)
        if rebound.get("state") in ("REBOUND_CONFIRMED_RESEARCH", "REBOUND_SETUP", "REBOUND_WATCH"):
            rebound["risk_assessment"] = risk_label(rebound)
            rebound["risk_diagnostics"] = risk_diagnostics(rebound)
        rows.append(row)
        rebound_rows.append(rebound)
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
        rebound_local = [r for r in rebound_rows if r["symbol"].endswith(".MX") == (market == "MX")]
        rebound_current = [r for r in rebound_local if (r.get("session_quality") or {}).get("state") == "CURRENT"]
        rebound_primary = sorted((r for r in rebound_current if r["state"] == "REBOUND_CONFIRMED_RESEARCH" and r.get("risk_assessment") == "RISK_ACCEPTABLE_FOR_RESEARCH"), key=lambda r: (-r["quality_score"], r["symbol"]))[:primary_limit]
        rebound_watch = sorted((r for r in rebound_current if r["state"] in ("REBOUND_WATCH", "REBOUND_SETUP") or (r["state"] == "REBOUND_CONFIRMED_RESEARCH" and r.get("risk_assessment") != "RISK_ACCEPTABLE_FOR_RESEARCH")), key=rebound_priority)[:watch_limit]
        markets[market] = {"rebounds": {"primary": rebound_primary, "watch": rebound_watch, "current": len(rebound_current)}, "reviewed": len(local), "current": len(valid),
                           "primary": primary, "watch": watch,
                           "risk_filtered": sum(r.get("risk_assessment") == "UNFAVORABLE_RISK_REWARD" for r in valid),
                           "primary_excluded_by_risk": sum(r["state"] == PRIMARY and r.get("risk_assessment") != "RISK_ACCEPTABLE_FOR_RESEARCH" for r in valid),
                           "rejected_or_error": sum(r["state"] in ("REJECT", "ERROR") for r in local)}
    elapsed = perf_counter() - started
    return {"state": "DAILY_RESEARCH_REPORT", "as_of_utc": now.isoformat(),
            "markets": markets, "results": rows, "rebound_results": rebound_rows, "requested": len(requested),
            "completed": len(rows), "elapsed_seconds": round(elapsed, 3),
            "fetch_and_analysis_seconds": round(sum(timings), 3),
            "mean_symbol_seconds": round(sum(timings) / len(timings), 3) if timings else None,
            "estimated_1000_seconds_linear": round(elapsed * 1000 / len(requested), 1) if requested else None,
            "risk_policy": {"min_reward_risk": MIN_REWARD_RISK, "status": "PROVISIONAL_NOT_BACKTEST_VALIDATED"},
            "research_only": True, "actionable": False,
            "limitations": ["EOD_ONLY_NOT_INTRADAY", "NO_VERIFIED_LIVE_QUOTE",
                            "NO_OOS_VALIDATION", "NO_AUTOMATED_BROKER_ORDERS",
                            "LINEAR_PROJECTION_NOT_BENCHMARK"]}
