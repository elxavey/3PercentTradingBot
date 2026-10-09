"""Read-only breakout radar with explicit manual refresh (research only)."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from config import BREAKOUT_TEST_SYMBOLS, UNIVERSES
from tradepilot.breakout_shortlist_cli import shortlist

st.set_page_config(page_title="TradePilot | Breakout Radar", page_icon="📡", layout="wide")
st.title("📡 Breakout Opportunity Radar")
st.caption("Research only · completed daily candles · no live quotes or orders. Score is not a win probability.")
output = Path(__file__).resolve().parents[1] / "breakout_shortlist.json"
morning_output = Path(__file__).resolve().parents[1] / "morning_radar_report.json"

with st.sidebar:
    st.subheader("Breakout universe")
    choices = {"Breakout test - 20 equities": BREAKOUT_TEST_SYMBOLS,
               "Broad MX + USA - 62 symbols": UNIVERSES["Broad MX + USA - 62 symbols"]}
    selected = st.selectbox("Universe", list(choices))
    st.caption("Only static, validated universes for now; dynamic 250/500/1000 needs rate-limit testing.")
    run = st.button("Run breakout research scan", type="primary", use_container_width=True)
    st.caption("Morning report is generated separately by the CLI; no background job is running.")

if run:
    with st.spinner("Scanning completed daily bars..."):
        report = shortlist(choices[selected])
    # No automatic email or background job from Streamlit.
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    st.success("Research report saved.")
else:
    if not output.exists():
        st.info("No report yet. Run a manual scan here or execute the breakout CLI.")
        st.stop()
    try:
        report = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        st.error(f"Could not load report: {exc}")
        st.stop()

top = report.get("top", [])
all_rows = report.get("results", [])
m1, m2, m3, m4 = st.columns(4)
m1.metric("Reviewed", len(all_rows))
m2.metric("Candidates", len(top))
m3.metric("Research-confirmed", sum(x.get("state") == "CONFIRMED_RESEARCH" for x in top))
m4.metric("Pending breakouts", sum(x.get("state") == "BREAKOUT_PENDING_CONFIRMATION" for x in top))
st.caption(f"Generated: {report.get('as_of_utc', 'unknown')} · Showing up to 10 candidates · No broker execution")
if top:
    table = pd.DataFrame([{
        "Symbol": r.get("symbol"), "State": r.get("state"),
        "Score / 100": r.get("quality_score"),
        "Close": r.get("reference_close"), "Trigger": round(r["breakout_trigger"], 2) if r.get("breakout_trigger") is not None else None,
        "Distance %": r.get("distance_to_trigger_pct"),
        "Relative volume": r.get("relative_volume"),
        "Bar date": r.get("session"),
        "Market": "MXN" if r.get("symbol", "").endswith(".MX") else "USD",
    } for r in top])
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.download_button("Export candidates CSV", table.to_csv(index=False),
                       "breakout_candidates.csv", "text/csv")
    for r in top:
        with st.expander(f"{r.get('symbol')} · {r.get('state')} · score {r.get('quality_score')}"):
            st.write("Confirmation checks:", r.get("confirmation_checks", {}))
            st.write("Session quality:", r.get("session_quality", {}))
            st.write("Structural stop reference:", r.get("structural_stop_reference"))
else:
    st.info("No qualified candidates in this report.")
with st.expander(f"All reviewed symbols and exclusions ({len(all_rows)})"):
    st.dataframe(pd.DataFrame([{
        "Symbol": r.get("symbol"), "State": r.get("state"),
        "Reason": r.get("reason", ""), "Data quality": (r.get("session_quality") or {}).get("state", ""),
        "Last bar": r.get("session", (r.get("session_quality") or {}).get("last_bar", "")),
        "Historical gaps": (r.get("session_quality") or {}).get("historical_missing_sessions_count", 0),
    } for r in all_rows]), use_container_width=True, hide_index=True)
st.warning("This is not an intraday opening scan. The latest complete daily candle can be yesterday's.")

st.divider()
st.subheader("🌅 Daily Radar — Mexico + United States")
st.caption("Separate confirmed and watch tiers. Morning report uses last completed daily close, not a live quote.")
if morning_output.exists():
    try:
        morning = json.loads(morning_output.read_text(encoding="utf-8"))
        st.caption(f"Report generated: {morning.get('as_of_utc')} | analyzed {morning.get('completed')} / {morning.get('requested')} | elapsed {morning.get('elapsed_seconds')}s")
        for market, label in (("MX", "🇲🇽 Mexico (MXN)"), ("US", "🇺🇸 United States (USD)")):
            st.markdown(f"#### {label}")
            section = morning.get("markets", {}).get(market, {})
            st.caption(f"Reviewed {section.get('reviewed', 0)} | current daily data {section.get('current', 0)} | rejected/error {section.get('rejected_or_error', 0)} | risk-filtered {section.get('risk_filtered', 0)}")
            for tier, heading in (("primary", "Confirmed research (max 10)"), ("watch", "Watch candidates (max 3)")):
                st.markdown(f"**{heading}**")
                records = []
                for r in section.get(tier, []):
                    plan = r.get("trade_plan") or {}
                    records.append({
                        "Symbol": r.get("symbol"), "State": {"APPROACHING": "Near breakout", "BREAKOUT_PENDING_CONFIRMATION": "Pending confirmation", "CONFIRMED_RESEARCH": "Research confirmed"}.get(r.get("state"), r.get("state")),
                        "Risk assessment": r.get("risk_assessment", "N/A"),
                        "Last daily close": round(r["reference_close"], 2) if r.get("reference_close") is not None else None,
                        "Daily bar date": r.get("session"),
                        "Breakout trigger": round(r["breakout_trigger"], 2) if r.get("breakout_trigger") is not None else None,
                        "Illustrative entry": round(plan["entry_reference"], 2) if plan.get("entry_reference") is not None else None,
                        "Illustrative target": round(plan["target_exit_reference"], 2) if plan.get("target_exit_reference") is not None else None,
                        "Structural stop": round(plan["stop_reference"], 2) if plan.get("stop_reference") is not None else None,
                        "Net target % (assumed)": plan.get("estimated_net_target_pct"),
                        "Reward/risk (assumed)": plan.get("reward_risk_net"),
                        "Score (not probability)": r.get("quality_score"),
                        "Relative volume": r.get("relative_volume"),
                    })
                if records:
                    st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
                else:
                    st.caption("No candidates in this category.")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.warning(f"Morning report unavailable: {exc}")
else:
    st.info("Generate the first daily report with: python -m tradepilot.morning_report_cli --universe test20")
