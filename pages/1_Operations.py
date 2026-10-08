"""Read-only Streamlit page for scheduled scanner operations."""
import pandas as pd
import streamlit as st

from tradepilot.monitoring import monitoring_snapshot

st.set_page_config(page_title="TradePilot Operations", page_icon="📊", layout="wide")
st.title("📊 TradePilot — Operations")
st.caption("Read-only monitoring from local SQLite. No scanner execution or job recovery.")

with st.sidebar:
    limit = st.slider("History rows", min_value=5, max_value=100, value=20, step=5)
    if st.button("Refresh monitoring"):
        st.rerun()

try:
    snapshot = monitoring_snapshot(limit=limit)
except Exception as exc:
    st.error(f"Unable to load monitoring: {type(exc).__name__}")
    st.stop()

latest_job = snapshot["latest_job"]
latest_scan = snapshot["latest_scan"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest job", latest_job["status"] if latest_job else "No jobs")
c2.metric("Heartbeat", latest_job["heartbeat_state"] if latest_job else "N/A")
c3.metric("Latest scan", latest_scan["status"] if latest_scan else "No scans")
c4.metric("Quality passed", latest_scan["quality_pass_count"] if latest_scan else "N/A")

if snapshot["warnings"]:
    for warning in snapshot["warnings"]:
        st.warning(warning)

st.subheader("Scheduled job history")
st.caption("RUNNING with stale heartbeat requires operator investigation; never auto-unlocked.")
if snapshot["jobs"]:
    columns = [
        "started_at_utc", "scheduled_for_utc", "status", "heartbeat_state",
        "universe_name", "elapsed_seconds", "discovered_count",
        "pre_screen_count", "quality_pass_count", "error_message", "job_id",
    ]
    st.dataframe(pd.DataFrame(snapshot["jobs"])[columns], use_container_width=True, hide_index=True)
else:
    st.info("No scheduled jobs recorded yet.")

st.subheader("Saved scans")
st.caption("Includes both manually initiated and scheduled scans.")
if snapshot["scans"]:
    st.dataframe(pd.DataFrame(snapshot["scans"]), use_container_width=True, hide_index=True)
else:
    st.info("No persisted scans yet.")

st.caption(f"Snapshot generated (UTC): {snapshot['generated_at_utc']}")
