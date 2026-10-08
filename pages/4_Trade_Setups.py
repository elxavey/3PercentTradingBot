"""Phase 3.4: read-only Visual Trade Setup; no broker actions."""
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tradepilot.setup_view import analyze_watchlist_symbol
from tradepilot.setup_visual import hypothetical_outcomes
from tradepilot.trade_setup import RiskPolicy
from tradepilot.watchlist import list_watchlist


def candlestick_figure(bars: pd.DataFrame, result: dict, currency: str):
    """Completed-session candles and clearly hypothetical future levels."""
    fig = go.Figure(data=[go.Candlestick(
        x=bars.index, open=bars["Open"], high=bars["High"],
        low=bars["Low"], close=bars["Close"], name="Completed daily bars"
    )])
    levels = (
        ("Support", "support", "#718096", "dot"),
        ("Resistance", "resistance", "#d69e2e", "dash"),
        ("Future entry (unconfirmed)", "entry_trigger", "#3182ce", "dash"),
        ("Hypothetical stop", "structural_stop", "#e53e3e", "dot"),
        ("Hypothetical target", "target", "#38a169", "dot"),
    )
    for label, key, color, dash in levels:
        if key in result:
            fig.add_hline(y=float(result[key]), line_color=color,
                          line_dash=dash, line_width=1.6,
                          annotation_text=f"{label}: {result[key]:.2f}",
                          annotation_position="top left")
    fig.update_layout(
        height=520, title=f"Historical completed sessions · {currency} · NOT a live quote",
        xaxis_title="Completed trading sessions", yaxis_title=f"Price ({currency})",
        xaxis_rangeslider_visible=False, margin=dict(l=25, r=30, t=65, b=30),
        showlegend=False,
    )
    return fig


st.set_page_config(page_title="TradePilot | Visual Trade Setups", page_icon="📈", layout="wide")
st.title("📈 TradePilot — Visual Trade Setup")
st.caption("Phase 3.4 · Completed daily candles · Research only · No broker orders")
st.warning(
    "Hypothetical FUTURE breakout levels, NOT buy signals or executable prices. "
    "The unfinished session is excluded. Yahoo/cached historical adjustment and "
    "provenance are not independently verified; no live quote is verified."
)

try:
    entries = [row for row in list_watchlist()
               if row["state"] in ("WATCHING", "PROMOTED")]
except Exception as exc:
    st.error(f"Watchlist unavailable: {type(exc).__name__}: {exc}")
    st.stop()

if not entries:
    st.info("No active Watchlist entries.")
    st.stop()

st.metric("Active research symbols", len(entries))
with st.expander("Research assumptions", expanded=False):
    equity = st.number_input("Research capital in symbol currency (MXN for MX, USD for US)",
                             min_value=100.0, value=10000.0, step=500.0)
    risk_pct = st.number_input("Risk budget (%)", min_value=0.1, max_value=10.0,
                               value=0.5, step=0.1)
    allocation_pct = st.number_input("Maximum allocation (%)", min_value=1.0,
                                     max_value=100.0, value=33.0, step=1.0)
    fee_pct = st.number_input("Fee per side (%)", min_value=0.0,
                              max_value=5.0, value=0.0, step=0.05)
    slippage_pct = st.number_input("Slippage per side (%)", min_value=0.0,
                                   max_value=5.0, value=0.0, step=0.05)
    st.caption("Zero transaction costs are placeholders, not verified GBM costs. "
               "For US symbols, enter USD capital, not MXN. No automatic FX.")

options = {(row["symbol"], row["market"]): row for row in entries}
selected = st.selectbox("Watchlist symbol", list(options),
                        format_func=lambda k: f"{k[0]} ({k[1]}) · {options[k]['state']}")
if st.button("Analyze completed daily bars", type="primary"):
    try:
        policy = RiskPolicy(
            equity=float(equity), risk_fraction=float(risk_pct) / 100,
            max_allocation_fraction=float(allocation_pct) / 100,
            fee_rate_per_side=float(fee_pct) / 100,
            slippage_rate_per_side=float(slippage_pct) / 100,
        )
        with st.spinner(f"Loading completed daily history for {selected[0]}..."):
            result = analyze_watchlist_symbol(
                symbol=selected[0], market=selected[1],
                policy=policy, as_of_utc=datetime.now(timezone.utc)
            )
        st.session_state["visual_setup_result"] = result
        st.session_state["visual_setup_key"] = selected
        st.session_state["visual_setup_assumptions"] = (
            equity, risk_pct, allocation_pct, fee_pct, slippage_pct
        )
    except Exception as exc:
        st.session_state.pop("visual_setup_result", None)
        st.error(f"Analysis unavailable: {type(exc).__name__}: {exc}")

result = st.session_state.get("visual_setup_result")
if result is not None and st.session_state.get("visual_setup_key") == selected:
    if st.session_state.get("visual_setup_assumptions") != (
        equity, risk_pct, allocation_pct, fee_pct, slippage_pct
    ):
        st.info("Assumptions changed. Click Analyze to recalculate.")
    else:
        currency = "MXN" if selected[1] == "MX" else "USD"
        st.subheader(f"{selected[0]} · {result['state']} · Research only")
        st.caption(
            f"Daily session evidence: {result.get('history_evidence', 'UNKNOWN')} · "
            f"Last completed bar: {result.get('last_completed_bar', 'N/A')}"
        )
        if "entry_trigger" in result:
            cols = st.columns(4)
            for col, title, key in zip(
                cols, ("Future entry (unconfirmed)", "Structural stop",
                       "Hypothetical target", "Resistance"),
                ("entry_trigger", "structural_stop", "target", "resistance")
            ):
                col.metric(title, f"{result[key]:,.2f} {currency}")
            bars = result.get("chart_history")
            if isinstance(bars, pd.DataFrame) and not bars.empty:
                st.plotly_chart(candlestick_figure(bars, result, currency),
                                use_container_width=True)
                st.caption("All plotted candles are completed sessions. "
                           "Horizontal levels describe a future scenario, not a fill.")
            else:
                st.info("Validated chart history unavailable; levels are research-only.")
            risk = result.get("risk", {})
            outcomes = hypothetical_outcomes(risk)
            st.subheader("Hypothetical position and outcomes")
            if outcomes["available"]:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Units (research only)", outcomes["quantity"])
                c2.metric("Estimated capital", f"{outcomes['cash_required']:,.2f} {currency}")
                c3.metric("Loss at stop (estimated)", f"{outcomes['risk']:,.2f} {currency}")
                c4.metric("Gain at target (estimated)", f"{outcomes['target_gain']:,.2f} {currency}")
                st.caption(
                    f"Net reward/risk estimate: {outcomes['net_rr']} · "
                    f"Research risk budget: {risk.get('risk_budget')} {currency} · "
                    "Includes entered fee/slippage assumptions, not gaps, taxes, "
                    "liquidity effects or guaranteed fills."
                )
            else:
                st.info("Not enough validated risk data to estimate outcomes.")
            with st.expander("Technical details and verification reasons"):
                st.dataframe(pd.DataFrame([{
                    "Support": result["support"], "Resistance": result["resistance"],
                    "Entry": result["entry_trigger"], "Stop": result["structural_stop"],
                    "Target": result["target"],
                    "Lookback": result["lookback_bars"],
                    "Stop lookback": result["stop_lookback_bars"],
                }]), hide_index=True, use_container_width=True)
                st.write("Reasons:", result.get("reasons", []))
                st.write("Risk reasons:", risk.get("reasons", []))
        else:
            st.info("Levels unavailable: " + ", ".join(result.get("reasons", [])))
        st.info("WAIT · No verified live breakout, quote or instrument. "
                "This page never places orders or changes the Watchlist.")
