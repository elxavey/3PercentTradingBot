# TradePilot v5: expanded historical validation

Run only on `development`. Historical research, not orders or investment advice.

## Scope
- Fetch up to five years of daily candles and evaluate the most recent 1,000 completed-session signal windows by default. Availability varies by symbol.
- Preserve existing BREAKOUT and REBOUND confirmation logic, turnover floors and 3% **net** target.
- For each confirmed signal, simulate entry at the first later opening/high crossing the trigger; gap-ups enter at the opening price plus slippage.
- Compare NO_STOP, FIXED_3PCT (price stop 3% below filled entry, **not** net loss capped at 3%), STRUCTURAL (existing plan stop). Same fees and slippage across all three.
- On post-entry bars, when both stop and target are inside one OHLC bar, pessimistically count STOP. An entry-bar low may predate the entry and is therefore excluded from stop execution; entry-day targets only count when the opening price itself reaches target. This convention can undercount rapid targets and undercount entry-day stops.
- Right-censored positions are OPEN_AT_LAST_BAR, **not losses**; their net return is hypothetical if liquidated on the last bar.
- Output contains grouped policy comparisons by MX/US and strategy and year, plus a descriptive signal de-duplication. De-duplication uses the no-stop target date/last available date as an occupancy proxy, not a real portfolio simulator.
- No point-in-time historical universe: today's selected tickers may introduce survivorship/selection bias. Overlapping entries remain in the raw report. This is not out-of-sample validation.
- Results require external local Build/Run testing.

## Example
```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git fetch origin development
git merge --ff-only origin/development
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_historical_v5.py" -v
.\.venv\Scripts\python.exe -m tradepilot.no_stop_validation_cli --symbols-file ".cache\strategy_symbols_100.txt" --max-symbols 100 --lookback 1000 --stride 15 --output ".cache\historical_v5.json"
```

For a longer 5-year candidate search, use `--lookback 1200`. For denser signal detection, lower `--stride` (slower). Increasing symbol count requires a larger symbols file; `--max-symbols` does not create symbols.

## Outputs
- `summary`: original no-stop outcomes by strategy/market.
- `v5_comparison`: policy comparisons for all confirmed signal events.
- `v5_nonoverlapping_comparison`: descriptive nonoverlapping subset.
- `signals[].exit_comparison`: each policy's result and session count.
- `errors`: failures; check this before interpreting percentages.

**Do not interpret percentages as prospective win rates.** Validate with an independent historical ticker universe, non-overlapping portfolios, and a forward holdout before considering live trading.
