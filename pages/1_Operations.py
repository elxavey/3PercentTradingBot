"""Read-only TradePilot operations and persisted-scan explorer."""
import pandas as pd
import streamlit as st

from tradepilot.monitoring import monitoring_snapshot
from tradepilot.monitoring_view import (
    candidate_rows, elapsed_label, filter_history, heartbeat_label,
    local_timestamp, status_label,
)
from tradepilot.storage.scan_repository import get_scan

st.set_page_config(page_title="TradePilot | Operations", page_icon="📊", layout="wide")
st.title("📊 TradePilot — Operations")
st.caption("Local SQLite monitoring · Read-only · No orders or job recovery")

with st.sidebar:
    limit = st.slider("History rows", min_value=5, max_value=100, value=20, step=5)
    if st.button("Refresh monitoring"):
        st.rerun()

try:
    snapshot = monitoring_snapshot(limit=limit)
except Exception as exc:
    st.error(f"Unable to load monitoring: {type(exc).__name__}")
    st.stop()

jobs = snapshot["jobs"]
scans = snapshot["scans"]
latest_job = snapshot["latest_job"]
latest_scan = snapshot["latest_scan"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest job", status_label(latest_job["status"]) if latest_job else "No jobs")
c2.metric("Worker heartbeat", heartbeat_label(latest_job["heartbeat_state"]) if latest_job else "N/A")
c3.metric("Latest scan", status_label(latest_scan["status"]) if latest_scan else "No scans")
c4.metric("Quality passed", latest_scan["quality_pass_count"] if latest_scan else "N/A")
st.caption("Worker heartbeat 'Finished / inactive' is normal for a completed job.")
for warning in snapshot["warnings"]:
    st.warning(warning)

st.subheader("Execution history")
st.caption("Filter the loaded history. All displayed dates are converted to this computer's local timezone.")
f1, f2 = st.columns(2)
statuses = ["All"] + sorted({row["status"] for row in jobs})
universes = ["All"] + sorted({row["universe_name"] for row in jobs if row["universe_name"]})
with f1:
    status_filter = st.selectbox("Job status", statuses)
with f2:
    universe_filter = st.selectbox("Job universe", universes)
filtered_jobs = filter_history(jobs, status=status_filter, universe=universe_filter)
if filtered_jobs:
    display_jobs = []
    for job in filtered_jobs:
        display_jobs.append({
            "Started (local)": local_timestamp(job["started_at_utc"]),
            "Status": status_label(job["status"]),
            "Heartbeat": heartbeat_label(job["heartbeat_state"]),
            "Universe": job["universe_name"] or "—",
            "Duration": elapsed_label(job["elapsed_seconds"]),
            "Discovered": job["discovered_count"],
            "Pre-screen": job["pre_screen_count"],
            "Quality passed": job["quality_pass_count"],
            "Error": job["error_message"] or "",
            "Job ID": job["job_id"],
        })
    st.dataframe(pd.DataFrame(display_jobs), use_container_width=True, hide_index=True)
    trend = pd.DataFrame([
        {
            "Time": pd.to_datetime(job["started_at_utc"], utc=True).tz_convert(
                datetime_local_tz
            ) if False else pd.to_datetime(job["started_at_utc"], utc=True).tz_convert(
                __import__("datetime").datetime.now().astimezone().tzinfo
            ),
            "Quality passed": job["quality_pass_count"],
            "Duration (s)": job["elapsed_seconds"],
        }
        for job in reversed(filtered_jobs) if job["quality_pass_count"] is not None
    ])
    if not trend.empty:
        st.caption("Historical Quality Gate pass counts (not trading signals)")
        st.line_chart(trend.set_index("Time")[["Quality passed"]])
else:
    st.info("No scheduled jobs match the filters.")

st.subheader("Saved scans")
st.caption("Includes manual and scheduled runs. Selecting a scan reads its stored results; no rescan.")
if scans:
    scan_options = {scan["id"]: scan for scan in scans}
    options = list(scan_options)
    selected = st.selectbox(
        "Inspect saved scan",
        options,
        format_func=lambda sid: (
            f"{local_timestamp(scan_options[sid]['finished_at_utc'])} · "
            f"{scan_options[sid]['universe_name']} · {sid[:8]}"
        ),
    )
    scan_rows = [{
        "Finished (local)": local_timestamp(s["finished_at_utc"]),
        "Universe": s["universe_name"],
        "Status": status_label(s["status"]),
        "Discovered": s["discovered_count"],
        "Pre-screen": s["pre_screen_count"],
        "Quality passed": s["quality_pass_count"],
        "Duration": elapsed_label(s["elapsed_seconds"]),
        "Scan ID": s["id"],
    } for s in scans]
    st.dataframe(pd.DataFrame(scan_rows), use_container_width=True, hide_index=True)
    try:
        selected_scan = get_scan(selected)
    except Exception as exc:
        st.error(f"Could not load saved scan: {type(exc).__name__}")
        selected_scan = None
    if selected_scan:
        st.markdown(f"**Saved candidates — {selected_scan.universe_name}**")
        quality_only = st.checkbox("Show Quality Gate PASS only", value=True)
        rows = candidate_rows(selected_scan.results, quality_only=quality_only)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No stored candidates match this selection.")
        st.caption(
            "Opportunity Score is a research ranking, not a buy signal or "
            "calibrated probability. Saved prices may be stale."
        )
else:
    st.info("No persisted scans yet.")

st.caption(f"Snapshot generated (local): {local_timestamp(snapshot['generated_at_utc'])}")
