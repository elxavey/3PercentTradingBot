"""Explain the structural risk gate without changing trading decisions.

All prices are historical research references, not executable quotes.
"""
from __future__ import annotations
from collections import Counter
from math import isfinite


def diagnose_risk(plan, *, target_net_pct=3.0, min_rr=1.0):
    base = {"status": "UNAVAILABLE", "gate_min_rr": min_rr,
            "target_net_pct": target_net_pct, "research_only": True}
    try:
        entry = float(plan["entry_reference"])
        stop = float(plan["stop_reference"])
        fee = float(plan.get("assumed_fee_per_side", 0.0025))
        slip = float(plan.get("assumed_slippage_per_side", 0.001))
        if not all(isfinite(x) for x in (entry, stop, fee, slip, target_net_pct, min_rr)):
            return {**base, "reason": "NON_FINITE_INPUT"}
        if not (0 < stop < entry and 0 <= fee < 1 and 0 <= slip < 1 and 0 < target_net_pct and min_rr > 0):
            return {**base, "reason": "INVALID_INPUT"}
        buy = entry * (1 + fee + slip)
        sell_factor = 1 - fee - slip
        if sell_factor <= 0:
            return {**base, "reason": "INVALID_SELL_FACTOR"}
        target = buy * (1 + target_net_pct / 100) / sell_factor
        gain = target * sell_factor - buy
        loss = buy - stop * sell_factor
        if gain <= 0 or loss <= 0:
            return {**base, "reason": "INVALID_PAYOFF"}
        rr = gain / loss
        # Minimum stop necessary to achieve min_rr at the same entry/target.
        # Diagnostic ONLY: never move an actual structural stop to this value.
        required_stop = (buy - gain / min_rr) / sell_factor
        risk_budget = gain / min_rr
        excess_loss = max(0.0, loss - risk_budget)
        gap = max(0.0, min_rr - rr)
        result = {
            **base, "status": "PASS" if rr >= min_rr else "FAIL",
            "reason": "RISK_ACCEPTABLE" if rr >= min_rr else "STRUCTURAL_RISK_EXCEEDS_REWARD",
            "entry_reference": round(entry, 6), "structural_stop_reference": round(stop, 6),
            "target_exit_reference": round(target, 6),
            "entry_to_stop_pct": round(100 * (entry - stop) / entry, 4),
            "gross_target_distance_pct": round(100 * (target / entry - 1), 4),
            "round_trip_fee_slippage_pct_approx": round(200 * (fee + slip), 4),
            "net_target_pct": target_net_pct,
            "net_reward_cash_per_share": round(gain, 6),
            "net_risk_cash_per_share": round(loss, 6),
            "reward_risk_net_unrounded": round(rr, 6),
            "rr_gap_to_gate": round(gap, 6),
            "excess_risk_cash_per_share": round(excess_loss, 6),
            "excess_risk_pct_of_entry": round(100 * excess_loss / entry, 4),
            "required_stop_for_gate_diagnostic_only": round(required_stop, 6),
            "stop_gap_to_required_pct_of_entry": round(100 * max(0.0, required_stop - stop) / entry, 4),
            "structural_stop_must_not_be_moved_to_pass": True,
            "technical_trigger_reference": plan.get("technical_trigger_reference"),
        }
        return result
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return {**base, "reason": "MISSING_OR_INVALID_PLAN"}


def compare_cost_scenarios(plan, *, target_net_pct=3.0):
    scenarios = (("BASELINE", 0.0025, 0.001), ("LOWER_COST_RESEARCH", 0.001, 0.0005),
                 ("HIGHER_COST_STRESS", 0.005, 0.002))
    return [
        {"scenario": label, "fee_per_side": fee, "slippage_per_side": slip,
         **diagnose_risk({**plan, "assumed_fee_per_side": fee,
                          "assumed_slippage_per_side": slip}, target_net_pct=target_net_pct)}
        for label, fee, slip in scenarios
    ]


def aggregate_risk_diagnostics(events):
    relevant = [e for e in events if e.get("risk_diagnostic", {}).get("status") in ("PASS", "FAIL")]
    groups = {}
    for market in ("MX", "US"):
        for strategy in ("BREAKOUT", "REBOUND"):
            subset = [e["risk_diagnostic"] for e in relevant
                      if e.get("market") == market and e.get("strategy") == strategy]
            rejected = [x for x in subset if x["status"] == "FAIL"]
            key = market + "_" + strategy
            groups[key] = {
                "evaluated": len(subset), "passed": len(subset) - len(rejected),
                "failed": len(rejected),
                "mean_rr": round(sum(x["reward_risk_net_unrounded"] for x in subset) / len(subset), 4) if subset else None,
                "mean_excess_risk_pct_of_entry_failed": round(
                    sum(x["excess_risk_pct_of_entry"] for x in rejected) / len(rejected), 4) if rejected else None,
                "reasons": dict(Counter(x["reason"] for x in subset))}
    return groups
