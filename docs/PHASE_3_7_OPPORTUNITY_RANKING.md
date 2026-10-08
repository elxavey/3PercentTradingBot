# Phase 3.7 — Opportunity Ranking (initial implementation)

## Scope
Pure, deterministic, manual, read-only ranking of **completed daily bars** for active Watchlist entries. No orders, broker connectivity, SQLite writes, scheduler modifications, or alerts. Score is a heuristic, not a probability of a gain, calibrated signal, or investment recommendation.

## Inputs
Existing Phase 3.5 `classify_opportunity`, Phase 3.6 `confirm_breakout`, and Phase 3.3 `completed_history` with `LATEST_COMPLETED_SESSION`. No additional data fetching.

## Score (0–100)
- Proximity (30): `30 * max(0, 1 - abs(distance_pct)/10)`; does not automatically reward a close above resistance.
- Relative volume (20): `20 * min(volume_ratio/1.5, 1)`.
- Historical trend (20): Phase 3.6 trend check.
- Persistence (20): `20 * confirmed_closes / required_closes`.
- Freshness (10): only when latest completed exchange session is verified.

Missing, stale, invalid, or unverified confirmation inputs are **excluded** (no numerical score). An unconfirmed `BREAKOUT_CANDIDATE` stays `UNCONFIRMED_BREAKOUT` regardless of score. `HISTORICAL_FILTERS_PASSED` is still **not actionable**.

## UI
Opportunity Monitor displays ranking score, tier, reason; descending numerical score with excluded rows last and symbol tie-break. Refresh remains manual. Existing scan opportunity score is a separate metric and must not be confused with this historical ranking.

## Windows acceptance
1. `git switch development` and `git pull origin development`.
2. `python -m py_compile tradepilot/opportunity_ranking.py pages/5_Opportunity_Monitor.py`.
3. `python -m unittest tests.test_opportunity_ranking -v`.
4. `python -m unittest discover -s tests -p "test_*.py"`.
5. In Streamlit Opportunity Monitor click Refresh; verify score, tier, excluded rows and no automatic actions.
