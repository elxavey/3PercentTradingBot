"""Pure presentation helpers for monitoring, independent of Streamlit."""
from __future__ import annotations

from datetime import datetime, timezone


def local_timestamp(value: str | None) -> str:
    """Display UTC ISO-8601 timestamp in the PC's local timezone."""
    if not value:
        return "—"
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Monitoring timestamp must be timezone-aware")
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def elapsed_label(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 0:
        raise ValueError("elapsed seconds cannot be negative")
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.1f}s"


def status_label(status: str | None) -> str:
    return {
        "SUCCEEDED": "Completed",
        "RUNNING": "Running",
        "FAILED": "Failed",
        "INTERRUPTED": "Interrupted",
        "SKIPPED": "Skipped",
    }.get(status, status or "No jobs")


def heartbeat_label(state: str | None) -> str:
    return {
        "NOT_RUNNING": "Finished / inactive",
        "RECENT": "Active heartbeat",
        "STALE_UNVERIFIED": "Stale — investigate",
        "UNKNOWN": "Unknown — investigate",
    }.get(state, state or "N/A")


def filter_history(rows: list[dict], *, status: str = "All", universe: str = "All") -> list[dict]:
    return [
        row for row in rows
        if (status == "All" or row.get("status") == status)
        and (universe == "All" or row.get("universe_name") == universe)
    ]


def candidate_rows(results: list[dict], *, quality_only: bool = False) -> list[dict]:
    """Saved results only. Quality pass and ranking are not buy signals."""
    rows = []
    for result in results:
        gate = result.get("quality_gate") or {}
        passed = bool(gate.get("passed"))
        if quality_only and not passed:
            continue
        opportunity = result.get("opportunity") or {}
        rows.append({
            "Ticker": result.get("ticker", "—"),
            "Name": result.get("name", "—"),
            "Market": gate.get("market") or ("MX" if str(result.get("ticker", "")).endswith(".MX") else "US"),
            "Quality": "PASS" if passed else "FAIL",
            "Opportunity score": opportunity.get("score"),
            "Legacy score": result.get("score"),
            "Price": result.get("price"),
            "RSI": result.get("rsi"),
            "RVOL": result.get("rvol"),
            "ATR %": result.get("atr_pct"),
        })
    return sorted(
        rows,
        key=lambda row: (
            row["Quality"] != "PASS",
            row["Opportunity score"] is None,
            -(row["Opportunity score"] or 0),
            row["Ticker"],
        ),
    )
