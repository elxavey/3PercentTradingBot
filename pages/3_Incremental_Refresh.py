"""Phase 2.3 manual incremental watchlist refresh."""
import pandas as pd
import streamlit as st

from tradepilot.watchlist_refresh import compare_refresh, preview_refresh, refresh
from tradepilot.storage.scan_repository import list_scans

st.set_page_config(page_title="TradePilot | Incremental Refresh", page_icon="🔄", layout="wide")
st.title("🔄 Incremental Watchlist Refresh")
st.caption("Phase 2.3 · Research only · No automated broker orders")
st.warning(
    "Daily-history session dates can be checked against the last completed "
    "exchange session. This is NOT verified intraday quote freshness and "
    "does not produce live trading signals."
)
limit = st.slider("Maximum active symbols", min_value=1, max_value=50, value=50)
try:
    plan = preview_refresh(limit=limit)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.metric("Active symbols to scan", len(plan["symbols"]))
st.caption(f"Excluded terminal entries: {plan['excluded_terminal']}")
if plan["symbols"]:
    st.dataframe(pd.DataFrame({"Symbol": plan["symbols"]}), hide_index=True)
    confirm = st.checkbox("Run research scan on these active symbols")
    if st.button("Run incremental research refresh", disabled=not confirm):
        with st.spinner("Running scanner and saving a new research scan..."):
            try:
                result = refresh(limit=limit)
            except Exception as exc:
                st.error(f"Refresh failed: {type(exc).__name__}: {exc}")
            else:
                st.success(f"Saved scan {result['scan_id']} — evaluated {result['evaluated']} symbols.")
                st.json(result)
                st.info("Review score changes below before applying promotions on Watchlist.")
                st.session_state["latest_incremental_scan_id"] = result["scan_id"]
else:
    st.info("No active watchlist symbols. Nothing to refresh.")

st.divider()
st.subheader("Historical score comparison")
st.caption("Read-only comparison with each symbol's last applied Watchlist score.")
saved = [
    row for row in list_scans(limit=100)
    if row["status"] == "SUCCEEDED"
    and row["universe_name"] == "Watchlist incremental research"
]
if saved:
    scan_ids = [row["id"] for row in saved]
    preferred = st.session_state.get("latest_incremental_scan_id")
    selected = st.selectbox(
        "Incremental scan to compare", scan_ids,
        index=scan_ids.index(preferred) if preferred in scan_ids else 0,
    )
    try:
        comparison = compare_refresh(selected)
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.caption(f"Completed UTC: {comparison['finished_at_utc']} · "
                   f"Scan duration: {comparison['elapsed_seconds']:.1f}s")
        st.warning(comparison["freshness_note"])
        st.caption("Older saved scans without session-date evidence remain UNKNOWN.")
        st.dataframe(pd.DataFrame(comparison["items"]), hide_index=True,
                     use_container_width=True)
        st.caption("NOT_EVALUATED means no candidate row; it is not a Quality Gate failure. "
                   "Score delta is relative to the last applied Watchlist observation.")
else:
    st.info("No saved incremental scans yet.")
