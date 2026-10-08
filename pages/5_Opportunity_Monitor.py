"""Phase 3.5: manual read-only Opportunity Monitor."""
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_fetcher import get_price_history
from tradepilot.opportunity_monitor import classify_opportunity, opportunity_history
from tradepilot.breakout_confirmation import confirm_breakout, ConfirmationPolicy
from tradepilot.opportunity_ranking import rank_opportunity
from tradepilot.opportunity_categories import research_category, CATEGORY_ORDER
from tradepilot.opportunity_detail import explain_opportunity
from tradepilot.setup_view import completed_history
from tradepilot.watchlist import list_watchlist
from tradepilot.scan_monitor_source import scan_monitor_entries

st.set_page_config(page_title="TradePilot | Opportunity Monitor", page_icon="🔎", layout="wide")
st.title("🔎 TradePilot — Opportunity Monitor")
st.caption("Phases 3.5–3.7 · Manual refresh · Completed daily bars only · Research only")
st.warning(
    "APPROACHING and BREAKOUT_CANDIDATE are historical research classifications, "
    "NOT verified live breakouts, buy signals or broker orders. Historical "
    "adjustment/provenance is not independently verified."
)
source = st.radio(
    "Research source", ["Active Watchlist", "Saved scan (read-only)"],
    horizontal=True, key="opportunity_source",
)
scan_id = ""
scan_limit = 20
if source == "Saved scan (read-only)":
    scan_id = st.text_input(
        "Successful saved scan ID",
        value="534062a7-4de5-4ab3-8018-189d95e682d3",
        help="Read-only historical scan candidates; does not update Watchlist.",
    ).strip()
    scan_limit = st.slider("Candidates to inspect", 1, 50, 20)
try:
    if source == "Active Watchlist":
        entries = [x for x in list_watchlist() if x["state"] in ("WATCHING", "PROMOTED")]
    else:
        preview = scan_monitor_entries(scan_id, limit=scan_limit)
        entries = preview["entries"]
        st.caption(
            f"Saved scan: {preview['universe_name']} · "
            f"Finished UTC: {preview['finished_at_utc']} · "
            f"Selected: {len(entries)}. Historical scanner score is NOT "
            "the technical Opportunity Monitor ranking."
        )
except Exception as exc:
    st.error(f"Research source unavailable: {type(exc).__name__}: {exc}")
    st.stop()

if not entries:
    st.info("No candidates in selected research source.")
    st.stop()

source_key = (source, scan_id if source == "Saved scan (read-only)" else "",
              scan_limit if source == "Saved scan (read-only)" else 0,
              tuple((e["symbol"], e["market"]) for e in entries))

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
    rows, histories, detail_bars, detail_components = [], {}, {}, {}
    progress = st.progress(0)
    for i, item in enumerate(entries):
        symbol, market = item["symbol"], item["market"]
        row = {"Symbol": symbol, "Market": market,
               "Watchlist": item["state"], "Score": item.get("opportunity_score")}
        ranked = {"ranking_score": None, "ranking_tier": "EXCLUDED",
                  "ranking_reason": "UNVERIFIED_OR_INSUFFICIENT_DATA"}
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
                ranked = rank_opportunity(result, confirmation,
                                          history_evidence=evidence)
                if ranked["eligible"]:
                    detail_bars[(symbol, market)] = completed.tail(90).copy()
                    detail_components[(symbol, market)] = ranked["components"]
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
        row.update({"Ranking score": ranked["ranking_score"],
                    "Ranking tier": ranked["ranking_tier"],
                    "Ranking reason": ranked["ranking_reason"]})
        rows.append(row)
        progress.progress((i + 1) / len(entries))
    st.session_state["opportunity_source_key"] = source_key
    st.session_state["opportunity_rows"] = rows
    st.session_state["opportunity_histories"] = histories
    st.session_state["opportunity_detail_bars"] = detail_bars
    st.session_state["opportunity_detail_components"] = detail_components
    st.session_state["opportunity_settings"] = settings
    st.session_state["opportunity_as_of"] = now.isoformat()

rows = (st.session_state.get("opportunity_rows")
        if st.session_state.get("opportunity_source_key") == source_key else None)
if rows is None and st.session_state.get("opportunity_rows") is not None:
    st.info("Research source changed. Click Refresh to analyze this selection.")
if rows is not None:
    if st.session_state.get("opportunity_settings") != settings:
        st.info("Threshold changed. Click Refresh to recalculate.")
    else:
        st.caption(f"Last manual analysis (UTC): {st.session_state['opportunity_as_of']}")
        df = pd.DataFrame(rows)
        order = {"BREAKOUT_CANDIDATE": 0, "APPROACHING": 1,
                 "MONITORING": 2, "INSUFFICIENT_DATA": 3}
        df["Research category"] = df.apply(
            lambda x: research_category(x["Status"], x.get("Confirmation")), axis=1)
        df["_rank"] = df["Status"].map(order)
        df = df.sort_values(["Ranking score", "Symbol"], ascending=[False, True],
                            na_position="last")
        counts = df["Status"].value_counts()
        cols = st.columns(4)
        for col, status in zip(cols, order):
            col.metric(status.replace("_", " ").title(), int(counts.get(status, 0)))
        for column in ("Confirmation", "Volume ratio", "Persistence", "Confirmation reasons"):
            if column not in df.columns:
                df[column] = None
        st.caption("Phase 3.7 · Ranking score 0–100: proximity 30, volume 20, "
                   "trend 20, persistence 20, freshness 10. "
                   "Unverified data have no score. Ranking is NOT a buy signal.")
        st.subheader("Research categories")
        category_cols = st.columns(4)
        for col, category in zip(category_cols, CATEGORY_ORDER[:4]):
            col.metric(category, int((df["Research category"] == category).sum()))
        st.caption("Categories describe historical evidence, not purchase readiness. "
                   "A high ranking score never overrides missing breakout confirmation.")
        st.dataframe(df.drop(columns=["_rank"]), hide_index=True,
                     use_container_width=True)
        st.subheader("Grouped research view")
        for category in CATEGORY_ORDER:
            group = df.loc[df["Research category"] == category]
            if not group.empty:
                with st.expander(f"{category} ({len(group)})", expanded=category != "General monitoring"):
                    st.dataframe(group[["Symbol", "Market", "Ranking score", "Distance %",
                                        "Volume ratio", "Confirmation", "Last session"]],
                                 hide_index=True, use_container_width=True)
        st.subheader("Phase 3.8 · Opportunity detail & decision explanation")
        eligible = df.loc[df["Ranking score"].notna()]
        if not eligible.empty:
            choices = [(r["Symbol"], r["Market"]) for _, r in eligible.iterrows()]
            chosen = st.selectbox("Inspect ranked symbol", choices,
                                  format_func=lambda key: f"{key[0]} ({key[1]})",
                                  key="opportunity_detail_selection")
            item = df.loc[(df["Symbol"] == chosen[0]) &
                          (df["Market"] == chosen[1])].iloc[0].to_dict()
            parts = st.session_state.get("opportunity_detail_components", {}).get(chosen, {})
            explanation = explain_opportunity(item, parts)
            st.markdown(f"**{explanation['headline']}**")
            st.caption(f"Category: {item['Research category']} · Historical ranking: "
                       f"{item['Ranking score']:.2f}/100 · Last completed session: "
                       f"{item['Last session']} · Research only")
            metrics = st.columns(4)
            currency = "MXN" if chosen[1] == "MX" else "USD"
            metrics[0].metric("Last completed close", f"{item['Last close']:.2f} {currency}")
            metrics[1].metric("Prior resistance", f"{item['Prior resistance']:.2f} {currency}")
            metrics[2].metric("Distance to resistance", f"{item['Distance %']:.3f}%")
            metrics[3].metric("Relative volume", f"{item['Volume ratio']:.3f}x")
            bars = st.session_state.get("opportunity_detail_bars", {}).get(chosen)
            if isinstance(bars, pd.DataFrame) and not bars.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=bars.index, open=bars["Open"], high=bars["High"],
                    low=bars["Low"], close=bars["Close"],
                    name="Completed daily bars")])
                fig.add_hline(y=float(item["Prior resistance"]),
                              line_dash="dash", line_color="#d69e2e",
                              annotation_text="Prior resistance (research)")
                fig.update_layout(height=440, xaxis_rangeslider_visible=False,
                                  title="Completed daily candles · NOT live prices",
                                  yaxis_title=f"Price ({currency})")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Reference resistance excludes the latest completed candle. "
                           "Historical OHLCV adjustment/provenance is not independently verified.")
            if parts:
                breakdown = pd.DataFrame([
                    {"Component": name.title(), "Points": points, "Maximum": maximum}
                    for name, points, maximum in (
                        ("proximity", parts.get("proximity", 0), 30),
                        ("volume", parts.get("volume", 0), 20),
                        ("trend", parts.get("trend", 0), 20),
                        ("persistence", parts.get("persistence", 0), 20),
                        ("freshness", parts.get("freshness", 0), 10))
                ])
                st.markdown("**Ranking breakdown (heuristic, not probability)**")
                st.dataframe(breakdown, hide_index=True, use_container_width=True)
            st.markdown("**Historical confirmation checks**")
            st.write("Confirmation:", item.get("Confirmation"))
            st.write("Persistence:", item.get("Persistence"))
            st.write("Reasons:", explanation["reasons"])
            st.info("Decision: RESEARCH / WAIT. No verified live quote, "
                    "instrument tradability, broker order, or expected profitability. "
                    "Ranking and historical confirmation are NOT buy signals.")
        else:
            st.info("No verified ranked opportunities available for detailed analysis.")
        missing = df.loc[df["Status"] == "INSUFFICIENT_DATA", ["Symbol", "Market", "Reason"]]
        if not missing.empty:
            st.warning(f"{len(missing)} symbols lack verified completed data; exclude from ranking.")
            st.dataframe(missing, hide_index=True, use_container_width=True)
        unconfirmed = df.loc[(df["Status"] == "BREAKOUT_CANDIDATE") & (df["Confirmation"] != "HISTORICAL_FILTERS_PASSED")]
        if not unconfirmed.empty:
            st.info(f"{len(unconfirmed)} breakout candidates have NOT passed historical confirmation filters.")
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
