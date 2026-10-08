"""Phase 3.3: read-only Trade Setups research dashboard."""
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from tradepilot.setup_view import analyze_watchlist_symbol
from tradepilot.trade_setup import RiskPolicy
from tradepilot.watchlist import list_watchlist

st.set_page_config(page_title="TradePilot | Trade Setups", page_icon="📐", layout="wide")
st.title("📐 TradePilot — Trade Setups")
st.caption("Phase 3.3 · Completed daily candles · Research only · No broker orders")
st.warning(
    "These are hypothetical FUTURE breakout levels, NOT live signals or executable "
    "prices. Today's incomplete candle is excluded. Yahoo/cached history is not "
    "independently verified for adjustment, provenance or intraday quote freshness."
)

try:
    entries = [row for row in list_watchlist()
               if row["state"] in ("WATCHING", "PROMOTED")]
except Exception as exc:
    st.error(f"Watchlist unavailable: {type(exc).__name__}: {exc}")
    st.stop()

if not entries:
    st.info("No active watchlist entries. Populate Watchlist first.")
    st.stop()

st.metric("Active research symbols", len(entries))
st.caption("History is requested only when you click Analyze. No SQLite changes.")
with st.expander("Research risk assumptions", expanded=True):
    equity = st.number_input("Research equity (per-symbol market currency)", min_value=100.0,
                             value=10000.0, step=500.0)
    risk_pct = st.number_input("Risk budget (%)", min_value=0.1, max_value=10.0,
                               value=0.5, step=0.1)
    allocation_pct = st.number_input("Max allocation (%)", min_value=1.0,
                                     max_value=100.0, value=33.0, step=1.0)
    fee_pct = st.number_input("Fee per side (%)", min_value=0.0,
                              max_value=5.0, value=0.0, step=0.05)
    slippage_pct = st.number_input("Slippage per side (%)", min_value=0.0,
                                   max_value=5.0, value=0.0, step=0.05)
    st.caption("MX values are MXN; US values are USD. No FX conversion is performed. "
               "Zero fees/slippage are placeholders, not verified broker costs.")

options = {(row["symbol"], row["market"]): row for row in entries}
selected = st.selectbox("Watchlist symbol", list(options),
                        format_func=lambda key: f"{key[0]} ({key[1]}) — {options[key]['state']}")
if st.button("Analyze completed daily bars", type="primary"):
    try:
        policy = RiskPolicy(equity=float(equity), risk_fraction=float(risk_pct) / 100,
                            max_allocation_fraction=float(allocation_pct) / 100,
                            fee_rate_per_side=float(fee_pct) / 100,
                            slippage_rate_per_side=float(slippage_pct) / 100)
        with st.spinner(f"Reading daily history for {selected[0]}..."):
            result = analyze_watchlist_symbol(
                symbol=selected[0], market=selected[1],
                policy=policy, as_of_utc=datetime.now(timezone.utc)
            )
        st.session_state["trade_setup_result"] = result
        st.session_state["trade_setup_key"] = selected
    except Exception as exc:
        st.session_state.pop("trade_setup_result", None)
        st.error(f"Cannot analyze: {type(exc).__name__}: {exc}")

result = st.session_state.get("trade_setup_result")
if result is not None and st.session_state.get("trade_setup_key") == selected:
    st.subheader(f"{selected[0]} — {result['state']}")
    st.caption(f"Daily history evidence: {result.get('history_evidence', 'UNKNOWN')} · "
               f"Last completed bar: {result.get('last_completed_bar', 'N/A')}")
    if "entry_trigger" in result:
        currency = "MXN" if selected[1] == "MX" else "USD"
        cols = st.columns(4)
        for col, title, key in zip(
            cols, ("Future entry trigger", "Structural stop", "Research target", "Resistance"),
            ("entry_trigger", "structural_stop", "target", "resistance")
        ):
            col.metric(title, f"{result[key]:,.2f} {currency}")
        st.dataframe(pd.DataFrame([{
            "Support": result["support"],
            "Resistance": result["resistance"],
            "Entry (hypothetical)": result["entry_trigger"],
            "Stop (hypothetical)": result["structural_stop"],
            "Target (hypothetical)": result["target"],
            "Lookback bars": result["lookback_bars"],
            "Stop lookback": result["stop_lookback_bars"],
        }]), hide_index=True, use_container_width=True)
        risk = result.get("risk", {})
        if risk:
            st.subheader("Risk estimate (research only)")
            st.dataframe(pd.DataFrame([{
                "Currency": risk.get("currency"),
                "Net reward/risk estimate": risk.get("net_reward_risk_estimate"),
                "Hypothetical units": risk.get("quantity_research_only"),
                "Risk budget": risk.get("risk_budget"),
                "Estimated risk": risk.get("estimated_risk"),
                "Status": risk.get("state"),
            }]), hide_index=True, use_container_width=True)
            st.caption("Hypothetical units are NOT an order size recommendation. "
                       "For US symbols, policy equity must be entered in USD.")
    else:
        st.info("Levels unavailable: " + ", ".join(result.get("reasons", [])))
    st.info("Status: WAIT · Breakout unconfirmed · No verified live quote or instrument. "
            "No trades or watchlist changes are made.")
