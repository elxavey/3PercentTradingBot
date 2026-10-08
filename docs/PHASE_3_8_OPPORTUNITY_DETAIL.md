# Phase 3.8 — Opportunity Detail & Decision Explanation

## Purpose
Read-only, on-demand inspection of an eligible symbol from the Phase 3.7 historical ranking. The detail panel reuses the **same manual-refresh snapshot** rather than fetching another session mid-analysis.

## What is displayed
- Symbol, market, historical category and score
- Last completed close, prior 20-session resistance, distance and relative volume
- Last 90 verified completed daily candles and historical resistance reference
- Five score components (proximity, volume, trend, persistence, freshness)
- Historical confirmation state, persistence count and explicit reasons
- Permanent **RESEARCH / WAIT** disclaimer: no live quote, verified instrument, fill, or buy signal

## Exclusions and safeguards
Symbols lacking verified latest completed sessions or valid ranking evidence are not selectable. The detail uses the historical dataset already vetted by `completed_history` and ranked by Phase 3.7. No orders, alerts, SQLite writes, scheduler modifications or GBM connectivity. Ranking is a heuristic, not a probability or forecast.

## Acceptance on Windows
1. Pull `development`.
2. Compile `tradepilot/opportunity_detail.py` and `pages/5_Opportunity_Monitor.py`.
3. Run `tests.test_opportunity_detail` and all unit tests.
4. Refresh Opportunity Monitor; choose AMZN, ALSEA, then another symbol in the detail dropdown.
5. Verify candle chart, resistance, score breakdown and explanations change consistently, with no live-trade language.
