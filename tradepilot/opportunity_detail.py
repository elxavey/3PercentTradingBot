"""Phase 3.8: deterministic explanation of historical opportunity evidence.

Presentation only. Never turns ranking into a trade instruction.
"""
from __future__ import annotations


def explain_opportunity(row: dict, components: dict | None = None) -> dict:
    status = row.get("Status", "INSUFFICIENT_DATA")
    category = row.get("Research category", "Excluded — unverified data")
    confirmation = row.get("Confirmation")
    reasons = [part.strip() for part in str(row.get("Confirmation reasons") or "").split(",") if part.strip()]
    score = row.get("Ranking score")
    if status == "INSUFFICIENT_DATA" or score is None:
        return {"headline": "Not rankable — data verification incomplete",
                "reasons": [str(row.get("Reason") or "MISSING_VERIFIED_DATA")],
                "components": {}, "actionable": False}
    headline = {
        "BREAKOUT_CANDIDATE": "Historical close exceeded prior resistance; confirmation remains separate",
        "APPROACHING": "Historical close is near prior resistance",
        "MONITORING": "Historical setup remains under general monitoring",
    }.get(status, "Unverified opportunity status")
    if confirmation == "HISTORICAL_FILTERS_PASSED" and status == "BREAKOUT_CANDIDATE":
        headline = "Historical breakout filters passed; live entry NOT verified"
    if not reasons:
        reasons = ["HISTORICAL_RESEARCH_ONLY"]
    return {"headline": headline, "category": category,
            "reasons": reasons, "components": dict(components or {}),
            "actionable": False}
