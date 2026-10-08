"""Phase 2.3 manual incremental watchlist refresh."""
import pandas as pd
import streamlit as st

from tradepilot.watchlist_refresh import preview_refresh, refresh

st.set_page_config(page_title="TradePilot | Incremental Refresh", page_icon="🔄", layout="wide")
st.title("🔄 Incremental Watchlist Refresh")
st.caption("Phase 2.3 · Research only · No automated broker orders")
st.warning(
    "The legacy scanner does not guarantee timestamp-verified live quotes. "
    "Results are research observations, not live trading signals."
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
                st.info("Review the saved scan on Watchlist before applying promotions.")
else:
    st.info("No active watchlist symbols. Nothing to refresh.")
