"""Presentation-only research categories for Phase 3.7.

Keep ranking scores separate from confirmation and opportunity states.
"""


def research_category(status: str, confirmation: str | None) -> str:
    if status == "INSUFFICIENT_DATA":
        return "Excluded — unverified data"
    if status == "BREAKOUT_CANDIDATE":
        if confirmation == "HISTORICAL_FILTERS_PASSED":
            return "Historical confirmed"
        return "Breakout watch"
    if status == "APPROACHING":
        return "Near resistance"
    if status == "MONITORING":
        return "General monitoring"
    return "Excluded — unverified data"


CATEGORY_ORDER = (
    "Historical confirmed",
    "Breakout watch",
    "Near resistance",
    "General monitoring",
    "Excluded — unverified data",
)
