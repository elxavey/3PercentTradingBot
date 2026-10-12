# Strategy Validation v2 — research-only

This module does not place orders, send emails, or use EODHD. All changes stay on `development` until tested.

## What's new
- Historical signal funnel: state counts, rejected reasons, confirmed signals, missing/invalid plans, reward/risk failures, trigger results.
- Per-symbol OHLCV coverage, missing/placeholder rows, and evaluated windows.
- Historical entry audits to distinguish technical triggers below completed close from future execution.
- Reproducible batch selection from the previous radar JSON, with separate MX/US limits.
- Dual-radar universe audit: states, risk, entry anomalies, Mexico representation and unverified BMV overlay.
- Conservative gap-up entry and stop-first OHLC assumptions remain.

## Windows test flow (run in repo root)

```powershell
Clear-Host
git switch development
git fetch origin development
git merge --ff-only origin/development
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_strategy_validation.py" -v
.\.venv\Scripts\python.exe -m tradepilot.strategy_batch_cli --input ".cache\morning_dual_radar_1000.json" --mx-limit 40 --us-limit 60 --output ".cache\strategy_symbols_100.txt" --metadata ".cache\strategy_symbols_100_metadata.json"
.\.venv\Scripts\python.exe -m tradepilot.strategy_validation_cli --symbols-file ".cache\strategy_symbols_100.txt" --lookback 180 --holding 10 --stride 15 --max-symbols 100 --output ".cache\strategy_validation_v2.json"
.\.venv\Scripts\python.exe -m tradepilot.universe_quality_cli --input ".cache\morning_dual_radar_1000.json" --output ".cache\universe_quality_v2.json"
```

## Interpretation
- A 0-trade run with state/rejection funnel is a diagnostic result, **not** proof of unprofitability.
- Historical research is **not** out-of-sample; the batch is chosen from a later radar snapshot (selection bias).
- No proof of a profitable edge, no broker execution, no verified live quotes.
- BMV mappings remain unverified and are **never** auto-approved.
- The 3% target is after modeled per-side fees and slippage, not a guarantee.
- A bar that both touches stop and target is conservatively counted as STOP; intra-bar ordering is unknown.
- More extensive backtesting requires out-of-sample walk-forward validation and correct exchange-session handling.
