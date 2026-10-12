# TradePilot Strategy Validation v3 — Research only

Branch: `development`. No broker orders, Gmail automation, or EODHD calls.

## Delivered
1. Breakout trade plan keeps the **historical resistance trigger** as `technical_trigger_reference` but sets a **forward research entry** at least 0.1% above the last completed close. Targets and net reward/risk are recalculated from the forward reference, not the stale technical trigger. This does not imply a fill.
2. Historical simulation evaluates future sessions, gap-up entries, net 3% target, stop-first ambiguity, and per-signal outcomes.
3. The historical report includes `signal_events` with risk dispositions and a chronological **descriptive** development/holdout split. It is **not a genuine independent out-of-sample validation** because parameters and symbols were not chosen exclusively from the development period. No profitability claims.
4. BMV candidate cross-check against radar, with manual issuer/series verification required; no auto-additions.
5. Six new offline v3 regression tests.

## Windows validation
All PowerShell examples begin with `Clear-Host`. The Windows machine only pulls and runs tests.

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git fetch origin development
git merge --ff-only origin/development
.\.venv\Scripts\python.exe -m compileall -q tradepilot tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_strategy_validation*.py" -v
.\.venv\Scripts\python.exe -m tradepilot.strategy_validation_cli --symbols-file ".cache\strategy_symbols_100.txt" --lookback 180 --holding 10 --stride 15 --train-fraction 0.7 --max-symbols 100 --output ".cache\strategy_validation_v3.json"
.\.venv\Scripts\python.exe -m tradepilot.universe_quality_cli --input ".cache\morning_dual_radar_1000.json" --output ".cache\universe_quality_v3.json"
```

Optional BMV candidate cross-check if the CSV already exists:
```powershell
Clear-Host
.\.venv\Scripts\python.exe -m tradepilot.bmv_crosscheck_cli --bmv-file ".cache\mx_bmv_candidate_validation.csv" --radar ".cache\morning_dual_radar_1000.json" --output ".cache\bmv_crosscheck_v3.json"
```

## Limitations
- A chronological split is descriptive, **not** a statistically independent out-of-sample proof. Real walk-forward requires selecting parameters on training data alone and testing on future unseen dates, ideally with point-in-time ticker universes.
- OHLC intraday ordering is unknown; ambiguous bars use stop-first conservative assumptions.
- Historical signals can overlap; no portfolio-level position/cash management.
- Yahoo cached price history may be shorter than the requested period; rerun or refresh where needed.
- MX candidate list is incomplete and issuer mapping is not verified.
- This system remains research-only, no live executable quotes or guarantees.
