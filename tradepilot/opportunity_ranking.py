"""Phase 3.7: deterministic, research-only ranking of completed-session setups.

The ranking is a heuristic, NOT a probability, recommendation, or live signal.
Missing or stale evidence is never assigned a numerical score.
"""
from __future__ import annotations

from math import isfinite


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def rank_opportunity(opportunity: dict, confirmation: dict | None,
                     *, history_evidence: str) -> dict:
    """Score five historical components, without turning candidates into signals.

    Proximity 30, relative volume 20, trend 20, persistence 20,
    completed-session freshness 10. Only eligible observations get a score.
    """
    excluded = {"eligible": False, "ranking_score": None, "actionable": False,
                "ranking_tier": "EXCLUDED", "components": {},
                "ranking_reason": "UNVERIFIED_OR_INSUFFICIENT_DATA"}
    if not isinstance(opportunity, dict) or not isinstance(confirmation, dict):
        return excluded
    if history_evidence != "LATEST_COMPLETED_SESSION":
        return {**excluded, "ranking_reason": "STALE_OR_UNVERIFIED_HISTORY"}
    if opportunity.get("state") not in ("APPROACHING", "BREAKOUT_CANDIDATE", "MONITORING"):
        return excluded
    if confirmation.get("state") not in ("FILTERS_NOT_MET", "HISTORICAL_FILTERS_PASSED"):
        return {**excluded, "ranking_reason": "UNVERIFIED_CONFIRMATION"}
    distance = _finite_number(opportunity.get("distance_pct"))
    ratio = _finite_number(confirmation.get("volume_ratio"))
    confirmed = confirmation.get("confirmed_closes")
    required = confirmation.get("required_closes")
    checks = confirmation.get("checks")
    if (distance is None or ratio is None or ratio < 0
            or not isinstance(confirmed, int) or isinstance(confirmed, bool)
            or not isinstance(required, int) or isinstance(required, bool)
            or required < 2 or not 0 <= confirmed <= required
            or not isinstance(checks, dict)
            or any(type(checks.get(k)) is not bool for k in ("trend", "volume", "persistence"))):
        return {**excluded, "ranking_reason": "INVALID_RANKING_INPUT"}
    # No bonus merely for crossing resistance: an unconfirmed candidate
    # must still earn points through independently measured evidence.
    proximity = round(30 * max(0.0, 1 - abs(distance) / 10), 2)
    volume = round(20 * min(ratio / 1.5, 1), 2)
    trend = 20 if checks["trend"] else 0
    persistence = round(20 * confirmed / required, 2)
    freshness = 10
    components = {"proximity": proximity, "volume": volume,
                  "trend": trend, "persistence": persistence,
                  "freshness": freshness}
    score = round(sum(components.values()), 2)
    confirmed_historical = (opportunity["state"] == "BREAKOUT_CANDIDATE"
                            and confirmation["state"] == "HISTORICAL_FILTERS_PASSED")
    tier = ("HISTORICAL_FILTERS_PASSED" if confirmed_historical
            else "UNCONFIRMED_BREAKOUT" if opportunity["state"] == "BREAKOUT_CANDIDATE"
            else "WATCH_ONLY")
    return {"eligible": True, "ranking_score": score, "actionable": False,
            "ranking_tier": tier, "components": components,
            "ranking_reason": "HISTORICAL_RESEARCH_ONLY"}


def rank_watchlist(rows: list[dict]) -> list[dict]:
    """Sort eligible research entries first, then excluded, with stable ties."""
    return sorted(rows, key=lambda row: (
        row.get("ranking_score") is None,
        -(row["ranking_score"] if row.get("ranking_score") is not None else 0),
        str(row.get("symbol", "")),
    ))
