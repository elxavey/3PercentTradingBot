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

## Automatic missing-session recovery (follow-up)

The CLI now retries up to **five** missing sessions per run using an explicit one-day Yahoo historical OHLCV request. Only a single bar matching the missing date with finite, coherent OHLCV is merged. No interpolation, prior-close carryforward or synthetic candle is permitted. The entire calendar/OHLCV validation runs again after recovery. Failed recovery leaves the backtest rejected and prints a `recovery` diagnostic. This applies to all symbols, not a hardcoded ALSEA exception.

The recovery is **in-memory for that CLI run**; it does not alter the history cache or SQLite. A future run can retry again if the primary provider still omits the date. Repeated provider omission is not evidence of an exchange holiday or permission to skip the date; independent official-session confirmation or a verified alternate data source is needed for persistent resolution.

## Optional second provider: EODHD

EODHD documents daily OHLCV by symbol and date; `ALSEA.MX` is listed on its Mexican exchange. The provider requires an account token and access entitlements; **availability of the 2026-04-22 bar is not yet verified**.

Set the key only in the current PowerShell session (never commit or paste it):
```powershell
$env:EODHD_API_TOKEN = Read-Host "EODHD API token"
.\.venv\Scripts\python.exe -m unittest tests.test_eodhd_source -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m tradepilot.backtest_cli --symbol ALSEA.MX --market MX --fee 0.0025 --slippage 0.001 --force-refresh
```

Flow: primary Yahoo two-year history -> targeted Yahoo recovery -> optional EODHD recovery for remaining missing dates -> full historical validation -> backtest. The EODHD adapter requests a single day at a time and verifies the two adjacent available dates' closing prices agree with Yahoo within 1.5% before accepting the missing bar. This is a **heuristic adjustment-basis check**, not a corporate-actions audit; an adjustment mismatch fails closed. All recovery remains in memory, without persistent cache writes or API token logging. When token is absent, secondary source is `NOT_CONFIGURED`.

This source is not a guarantee: free accounts may not have MX historical coverage, and a genuinely non-trading day may be absent from both vendors. Never fill missing prices with fabricated bars. Do not assume EODHD provides a trade on the missing date until the API confirms it.


### Adjusted-price EODHD recovery (October 2026)

Yahoo's default yfinance daily history uses adjusted OHLC, while EODHD provides both raw `close` and `adjusted_close`. For a missing exchange session, the optional secondary recovery checks the nearest available Yahoo sessions on both sides. If raw EODHD closes agree within 0.5%, raw OHLC is used; otherwise both EODHD adjusted closes must agree within 0.5%. Only then are the missing session's OHLC scaled by its own explicit `adjusted_close / close` factor. Volume is never scaled. If the adjustment field is absent, invalid, or neighboring closes do not agree, recovery fails closed and backtesting remains rejected. This is a local compatibility check, not an audit of all corporate actions or a guarantee of backtest validity.

Run `python -m unittest tests.test_eodhd_source -v` and the complete test suite before running `python -m tradepilot.backtest_cli --symbol ALSEA.MX --market MX --fee 0.0025 --slippage 0.001 --force-refresh`. The provider requests consume API quota and must not print the API token.
