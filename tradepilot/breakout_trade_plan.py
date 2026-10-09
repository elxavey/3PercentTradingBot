"""Conservative, illustrative breakout trade levels from completed daily bars.

Not a quote, not a fill assumption, not a validated profitable strategy.
"""
from __future__ import annotations
from math import isfinite


def build_trade_plan(row: dict, *, target_net_pct: float = 3.0,
                     fee_per_side: float = 0.0025,
                     slippage_per_side: float = 0.001) -> dict:
    base = {"plan_state": "UNAVAILABLE", "entry_reference": None,
            "target_exit_reference": None, "stop_reference": None,
            "estimated_net_target_pct": None, "reward_risk_net": None,
            "quote_type": "LAST_COMPLETED_DAILY_CLOSE", "actionable": False}
    try:
        close = float(row["reference_close"])
        trigger = float(row["breakout_trigger"])
        structural = float(row["structural_stop_reference"])
        values = (close, trigger, structural, target_net_pct, fee_per_side, slippage_per_side)
        if not all(isfinite(x) for x in values) or min(close, trigger, structural) <= 0:
            return {**base, "plan_reason": "INVALID_LEVELS"}
        if target_net_pct <= 0 or min(fee_per_side, slippage_per_side) < 0:
            return {**base, "plan_reason": "INVALID_COST_ASSUMPTIONS"}
        # A plan is anchored at a *future* trigger, never at an assumed execution.
        entry = trigger
        stop = structural * 0.999
        if not 0 < stop < entry:
            return {**base, "plan_reason": "INVALID_STOP"}
        buy_cost = entry * (1 + fee_per_side + slippage_per_side)
        sell_factor = 1 - fee_per_side - slippage_per_side
        if sell_factor <= 0:
            return {**base, "plan_reason": "INVALID_SELL_COST"}
        target = buy_cost * (1 + target_net_pct / 100) / sell_factor
        loss = buy_cost - stop * sell_factor
        gain = target * sell_factor - buy_cost
        if loss <= 0:
            return {**base, "plan_reason": "INVALID_RISK"}
        return {**base, "plan_state": "ILLUSTRATIVE_UNTRIGGERED",
                "plan_reason": "REQUIRES_LIVE_PRICE_AND_CONFIRMATION",
                "entry_reference": round(entry, 4),
                "target_exit_reference": round(target, 4),
                "stop_reference": round(stop, 4),
                "estimated_net_target_pct": target_net_pct,
                "reward_risk_net": round(gain / loss, 3),
                "assumed_fee_per_side": fee_per_side,
                "assumed_slippage_per_side": slippage_per_side}
    except (KeyError, TypeError, ValueError, OverflowError):
        return {**base, "plan_reason": "MISSING_LEVELS"}
