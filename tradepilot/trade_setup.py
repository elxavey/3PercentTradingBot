"""Phase 3.1 pure, conservative research setup and risk calculations.

No broker orders, no market-data fetching, no DB writes. A valid research
calculation is never a live or GBM-actionable BUY signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite


@dataclass(frozen=True)
class RiskPolicy:
    equity: float = 10000.0
    risk_fraction: float = 0.005
    max_positions: int = 3
    max_allocation_fraction: float = 0.33
    min_reward_risk: float = 1.5
    fee_rate_per_side: float = 0.0
    slippage_rate_per_side: float = 0.0


def evaluate_setup(
    *, symbol: str, market: str, entry: float | None,
    stop: float | None, target: float | None, policy: RiskPolicy,
    open_positions: int = 0, available_cash: float | None = None,
    quote_freshness: str = "UNKNOWN", quote_timestamp_verified: bool = False,
    instrument_verified: bool = False, currency_conversion_verified: bool = False,
    lot_size: int = 1,
) -> dict:
    """Return a deterministic, fail-closed *research* proposal.

    Currency is MXN for MX, USD for US. Equity and available_cash must be
    denominated in that same currency. No automatic FX conversion.
    """
    reasons: list[str] = []
    if not symbol or not symbol.strip() or market not in ("MX", "US"):
        raise ValueError("valid symbol and market MX/US required")
    if lot_size < 1 or not isinstance(lot_size, int):
        raise ValueError("lot_size must be a positive integer")
    for field in ("equity", "risk_fraction", "max_allocation_fraction",
                  "min_reward_risk", "fee_rate_per_side", "slippage_rate_per_side"):
        value = getattr(policy, field)
        if not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError(f"{field} must be finite")
    if (policy.equity <= 0 or not 0 < policy.risk_fraction <= 1
            or not 0 < policy.max_allocation_fraction <= 1
            or policy.min_reward_risk <= 0 or policy.max_positions < 1
            or policy.fee_rate_per_side < 0 or policy.slippage_rate_per_side < 0
            or policy.fee_rate_per_side + policy.slippage_rate_per_side >= 1):
        raise ValueError("invalid risk policy")
    if not isinstance(open_positions, int) or open_positions < 0:
        raise ValueError("open_positions must be nonnegative integer")
    cash = policy.equity if available_cash is None else available_cash
    if not isinstance(cash, (int, float)) or not isfinite(cash) or cash < 0:
        raise ValueError("available_cash must be finite and nonnegative")
    if open_positions >= policy.max_positions:
        reasons.append("MAX_POSITIONS_REACHED")
    if quote_freshness != "FRESH" or not quote_timestamp_verified:
        reasons.append("LIVE_QUOTE_NOT_VERIFIED")
    if not instrument_verified:
        reasons.append("INSTRUMENT_NOT_VERIFIED")
    if market == "US" and not currency_conversion_verified:
        reasons.append("US_FX_NOT_VERIFIED")
    prices = (entry, stop, target)
    if any(v is None or not isinstance(v, (int, float)) or not isfinite(v) or v <= 0
           for v in prices):
        reasons.append("INVALID_PRICE_INPUT")
        return _rejected(symbol, market, reasons)
    entry, stop, target = (float(v) for v in prices)
    if not stop < entry < target:
        reasons.append("INVALID_LONG_STRUCTURE")
        return _rejected(symbol, market, reasons)
    roundtrip = policy.fee_rate_per_side + policy.slippage_rate_per_side
    entry_cost = entry * (1 + roundtrip)
    stop_proceeds = stop * (1 - roundtrip)
    target_proceeds = target * (1 - roundtrip)
    unit_risk = entry_cost - stop_proceeds
    unit_reward = target_proceeds - entry_cost
    rr = unit_reward / unit_risk if unit_risk > 0 else 0.0
    if unit_reward <= 0 or rr < policy.min_reward_risk:
        reasons.append("REWARD_RISK_BELOW_MINIMUM")
    risk_budget = policy.equity * policy.risk_fraction
    allocation = min(cash, policy.equity * policy.max_allocation_fraction)
    max_by_risk = floor(risk_budget / unit_risk) if unit_risk > 0 else 0
    max_by_cash = floor(allocation / entry_cost)
    quantity = max(0, min(max_by_risk, max_by_cash))
    quantity = (quantity // lot_size) * lot_size
    if quantity == 0:
        reasons.append("INSUFFICIENT_CAPITAL_OR_RISK_BUDGET")
    return {
        "symbol": symbol.strip().upper(), "market": market,
        "currency": "MXN" if market == "MX" else "USD",
        "state": "WAIT" if reasons else "RESEARCH_READY",
        "actionable": False, "reasons": reasons or ["RESEARCH_ONLY_NO_BROKER_ORDER"],
        "entry": entry, "stop": stop, "target": target,
        "net_reward_risk_estimate": round(rr, 4),
        "quantity_research_only": quantity,
        "risk_budget": round(risk_budget, 2),
        "estimated_risk": round(quantity * unit_risk, 2),
        "estimated_cash_required": round(quantity * entry_cost, 2),
        "net_target_return_pct_estimate": round((target_proceeds / entry_cost - 1) * 100, 3),
    }


def _rejected(symbol: str, market: str, reasons: list[str]) -> dict:
    return {"symbol": symbol.strip().upper(), "market": market,
            "currency": "MXN" if market == "MX" else "USD",
            "state": "REJECT", "actionable": False, "reasons": reasons,
            "quantity_research_only": 0}
