"""Phase 3.5: manual read-only Opportunity Monitor."""
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from data_fetcher import get_price_history
from tradepilot.opportunity_monitor import classify_opportunity, opportunity_history
from tradepilot.breakout_confirmation import confirm_breakout, ConfirmationPolicy
from tradepilot.setup_view import completed_history
from tradepilot.watchlist import list_watchlist

st.set_page_config(page_title="TradePilot | Opportunity Monitor", page_icon="🔎", layout="wide")
st.title("🔎 TradePilot — Opportunity Monitor")
st.caption("Phases 3.5–3.6 · Manual refresh · Completed daily bars only · Research only")
st.warning(
    "APPROACHING and BREAKOUT_CANDIDATE are historical research classifications, "
    "NOT verified live breakouts, buy signals or broker orders. Historical "
    "adjustment/provenance is not independently verified."
)
try:
    entries = [x for x in list_watchlist() if x["state"] in ("WATCHING", "PROMOTED")]
except Exception as exc:
    st.error(f"Watchlist unavailable: {type(exc).__name__}: {exc}")
    st.stop()

if not entries:
    st.info("No active Watchlist entries.")
    st.stop()

near = st.slider("Near resistance threshold (%)", min_value=0.5, max_value=10.0,
                 value=3.0, step=0.5)
st.caption(f"{len(entries)} active symbols. Analysis runs only on click. "
           "No changes to SQLite, Windows tasks, or Watchlist.")
with st.expander("Phase 3.6 · Historical breakout confirmation filters"):
    volume_ratio = st.slider("Minimum latest-session volume / prior 20-session average", 1.0, 3.0, 1.2, 0.1)
    persistence = st.slider("Required consecutive completed closes above prior resistance", 2, 4, 2)
    breakout_pct = st.slider("Minimum close above resistance (%)", 0.0, 3.0, 0.1, 0.1)
settings = (near, volume_ratio, persistence, breakout_pct)
if st.button("Refresh opportunity monitor", type="primary"):
    now = datetime.now(timezone.utc)
    rows, histories = [], {}
    progress = st.progress(0)
    for i, item in enumerate(entries):
        symbol, market = item["symbol"], item["market"]
        row = {"Symbol": symbol, "Market": market,
               "Watchlist": item["state"], "Score": item.get("opportunity_score")}
        try:
            raw = get_price_history(symbol)
            completed, evidence = completed_history(
                raw, market=market, as_of_utc=now
            )
            if completed is None:
                result = {"state": "INSUFFICIENT_DATA", "distance_pct": None,
                          "close": None, "resistance": None,
                          "session": None, "reason": evidence}
            elif evidence != "LATEST_COMPLETED_SESSION":
                result = {"state": "INSUFFICIENT_DATA", "distance_pct": None,
                          "close": None, "resistance": None,
                          "session": None, "reason": "STALE_COMPLETED_HISTORY"}
            else:
                result = classify_opportunity(completed, near_pct=near)
                confirmation = confirm_breakout(completed, policy=ConfirmationPolicy(
                    persistence_sessions=persistence,
                    minimum_volume_ratio=volume_ratio,
                    minimum_breakout_pct=breakout_pct))
                row.update({
                    "Confirmation": confirmation["state"],
                    "Volume ratio": confirmation.get("volume_ratio"),
                    "Persistence": f"{confirmation.get('confirmed_closes', 0)}/{persistence}",
                    "Confirmation reasons": ", ".join(confirmation["reasons"]),
                })
                histories[(symbol, market)] = opportunity_history(
                    completed, near_pct=near
                )
            row.update({
                "Status": result["state"], "Last close": result["close"],
                "Prior resistance": result["resistance"],
                "Distance %": result["distance_pct"],
                "Last session": result["session"], "Reason": result["reason"],
            })
        except Exception as exc:
            row.update({
                "Status": "INSUFFICIENT_DATA", "Last close": None,
                "Prior resistance": None, "Distance %": None,
                "Last session": None,
                "Reason": f"FETCH_OR_VALIDATION_ERROR:{type(exc).__name__}",
            })
        rows.append(row)
        progress.progress((i + 1) / len(entries))
    st.session_state["opportunity_rows"] = rows
    st.session_state["opportunity_histories"] = histories
    st.session_state["opportunity_settings"] = settings
    st.session_state["opportunity_as_of"] = now.isoformat()

rows = st.session_state.get("opportunity_rows")
if rows is not None:
    if st.session_state.get("opportunity_settings") != settings:
        st.info("Threshold changed. Click Refresh to recalculate.")
    else:
        st.caption(f"Last manual analysis (UTC): {st.session_state['opportunity_as_of']}")
        df = pd.DataFrame(rows)
        order = {"BREAKOUT_CANDIDATE": 0, "APPROACHING": 1,
                 "MONITORING": 2, "INSUFFICIENT_DATA": 3}
        df["_rank"] = df["Status"].map(order)
        df = df.sort_values(["_rank", "Distance %", "Symbol"], na_position="last")
        counts = df["Status"].value_counts()
        cols = st.columns(4)
        for col, status in zip(cols, order):
            col.metric(status.replace("_", " ").title(), int(counts.get(status, 0)))
        for column in ("Confirmation", "Volume ratio", "Persistence", "Confirmation reasons"):
            if column not in df.columns:
                df[column] = None
        st.dataframe(df.drop(columns=["_rank"]), hide_index=True,
                     use_container_width=True)
        st.caption("Distance = (prior 20-session resistance − latest completed close) "
                   "/ resistance × 100. Negative values mean the completed close "
                   "exceeded prior resistance, NOT a verified intraday trigger.")
        keys = list(st.session_state.get("opportunity_histories", {}))
        if keys:
            selected = st.selectbox("Historical proximity (rolling, no future candles)",
                                    keys, format_func=lambda x: f"{x[0]} ({x[1]})")
            points = st.session_state["opportunity_histories"][selected]
            usable = [p for p in points if p["distance_pct"] is not None]
            if usable:
                timeline = pd.DataFrame(usable)
                timeline["session"] = pd.to_datetime(timeline["session"])
                st.line_chart(timeline.set_index("session")["distance_pct"],
                              y_label="Distance to prior resistance (%)")
                st.dataframe(timeline[["session", "close", "resistance",
                                      "distance_pct", "state"]],
                             hide_index=True, use_container_width=True)
            else:
                st.info("Insufficient historical observations.")
        st.info("Historical filters passing does NOT verify a live quote, trade entry, or profitability. No alerts are sent, no orders placed, "
                "and no automatic scheduler jobs have been modified.")
