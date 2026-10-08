"""TradePilot Phase 2.1 watchlist explorer and explicit promotion controls."""
import pandas as pd
import streamlit as st

from tradepilot.monitoring_view import local_timestamp
from tradepilot.storage.scan_repository import list_scans
from tradepilot.watchlist import (
    list_watchlist, preview_watchlist, set_watchlist_state,
    update_watchlist, watchlist_history,
)

st.set_page_config(page_title="TradePilot | Watchlist", page_icon="👀", layout="wide")
st.title("👀 TradePilot — Dynamic Watchlist")
st.caption("Phase 2.2 · Audited research lifecycle · No broker orders or buy signals")

st.subheader("Current watchlist")
try:
    current = list_watchlist()
except Exception as exc:
    st.error(f"Cannot load watchlist: {type(exc).__name__}: {exc}")
    st.stop()

if current:
    display = [{
        "Ticker": row["symbol"],
        "Market": row["market"],
        "State": row["state"],
        "Opportunity score": row["opportunity_score"],
        "First seen (local)": local_timestamp(row["first_seen_at_utc"]),
        "Last seen (local)": local_timestamp(row["last_seen_at_utc"]),
        "Source scan": row["last_scan_run_id"],
    } for row in current]
    st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
    active = sum(row["state"] in ("WATCHING", "PROMOTED") for row in current)
    promoted = sum(row["state"] == "PROMOTED" for row in current)
    m1, m2, m3 = st.columns(3)
    m1.metric("Total tracked (all states)", len(current))
    m2.metric("Active", active)
    m3.metric("Promoted (score ≥ 70)", promoted)
    st.caption("PROMOTED means a research ranking threshold, not a trading recommendation.")
    st.subheader("Lifecycle history")
    choices = {(row["symbol"], row["market"]): row for row in current}
    selected_key = st.selectbox(
        "Symbol to inspect",
        list(choices),
        format_func=lambda key: f"{key[0]} ({key[1]}) — {choices[key]['state']}",
    )
    events = watchlist_history(*selected_key)
    if events:
        event_rows = [{
            "When (local)": local_timestamp(event["occurred_at_utc"]),
            "From": event["previous_state"] or "NEW",
            "To": event["new_state"],
            "Previous score": event["previous_score"],
            "New score": event["new_score"],
            "Score change": (
                round(event["new_score"] - event["previous_score"], 2)
                if event["new_score"] is not None and event["previous_score"] is not None
                else None
            ),
            "Reason": event["reason"],
            "Scan ID": event["scan_run_id"],
        } for event in events]
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No lifecycle events recorded yet for this symbol (pre-2.2 entry).")
    if choices[selected_key]["state"] in ("WATCHING", "PROMOTED"):
        st.caption("Terminal actions are manual and irreversible in this version.")
        confirm = st.checkbox("I confirm I want to retire this symbol from active tracking")
        action = st.selectbox("Retirement reason", ["EXPIRED", "REMOVED"])
        if st.button("Confirm retirement", disabled=not confirm):
            try:
                set_watchlist_state(*selected_key, action)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.rerun()
else:
    st.info("No symbols tracked yet. Preview a saved scan below.")

st.subheader("Promote from a saved scan")
st.caption("Preview does not change SQLite. Apply is an explicit write and retains existing symbols.")
scans = [s for s in list_scans(limit=100) if s["status"] == "SUCCEEDED"]
if not scans:
    st.info("Run and save a scanner analysis first.")
    st.stop()

by_id = {s["id"]: s for s in scans}
scan_id = st.selectbox(
    "Completed scan",
    list(by_id),
    format_func=lambda sid: (
        f"{local_timestamp(by_id[sid]['finished_at_utc'])} · "
        f"{by_id[sid]['universe_name']} · {sid[:8]}"
    ),
)
limit = st.slider("Top candidates", min_value=1, max_value=50, value=20)
try:
    preview = preview_watchlist(scan_id, limit=limit)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if preview["items"]:
    st.dataframe(pd.DataFrame(preview["items"]), use_container_width=True, hide_index=True)
else:
    st.info("No ranked Quality Gate PASS candidates in this scan.")

st.warning("Quality Gate PASS and Opportunity Score do not constitute a trading recommendation.")
if st.button("Apply selected scan to watchlist", type="primary", disabled=not preview["items"]):
    try:
        result = update_watchlist(scan_id, limit=limit)
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.success(f"Updated {result['promoted_or_refreshed']} entries. Older entries retained.")
        st.rerun()
