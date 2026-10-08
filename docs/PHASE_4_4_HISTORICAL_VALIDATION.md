# Phase 4.4 — Historical Backtest Validation

Scope: local, research-only, one-symbol historical backtest; initial case `ALSEA.MX`. No SQLite writes, orders, task changes, or automatic Watchlist promotion.

## Run on Windows

```powershell
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest tests.test_backtest_validation -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m tradepilot.backtest_cli --symbol ALSEA.MX --market MX --fee 0.0025 --slippage 0.001 --force-refresh
```

Fees 0.25% and slippage 0.10% **per side are illustrative research assumptions**, NOT verified GBM tariffs. Adjust after verifying actual conditions. The CLI fetches two years via existing `get_price_history`, filters incomplete sessions using `completed_history`, rejects malformed OHLCV or missing exchange sessions, and prints JSON to stdout. It does not save the report. Exit code 2 means rejected input.

Historical session continuity is checked between first and last observed dates; no assertion is made about the number of years covered or missing history *before* the first observed bar. Old provider placeholders may be dropped by existing `completed_history` logic, but missing sessions will then be rejected. Exchange calendar versions and corporate action adjustment methods must be recorded for formal reproducibility.

**Limitations:** this is in-sample research on currently selected symbols, not out-of-sample evidence of a profitable strategy. Yahoo historical data may be revised; no historical constituent list/delistings, split/dividend audit, bid/ask spreads, actual GBM fees/taxes, USD/MXN FX, portfolio allocation or intraday price path verification. Trade-level compounded return assumes sequential full reinvestment and is NOT portfolio equity. Drawdown is closed-trade-only. Do not compare MXN and USD returns as pooled portfolio performance.

Next: run ALSEA and inspect the JSON; then address any validation gaps, build out-of-sample partitions and realistic fee/FX models before extending to 62 symbols.
