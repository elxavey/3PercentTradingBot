# Universe expansion acceptance — 12 to 62

This is a **validation checkpoint** before Phase 4 backtesting, not a trading signal or strategy optimization.

## Step 1: Inspect existing data, without scanning
```powershell
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest tests.test_expansion_validation -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m tradepilot.expansion_validation
```

- `NO_SCAN`: no matching 62-symbol scan persisted yet; this is not an error.
- `NEEDS_REVIEW`: latest matching scan failed or has inconsistent counts.
- `READY_FOR_REVIEW`: persisted summary/counts internally consistent; **not** proof that all 62 symbols have complete data.

## Step 2: Controlled expansion
After examining the report and confirming the intended scanner entry point, run **one** 62-symbol scan manually, not by changing existing Windows scheduled tasks. Capture elapsed time, discovered/pre-screen/quality-pass counts, error categories and timestamps. Avoid concurrent scans. Do not auto-update or expire the current 12-symbol watchlist during this validation.

## Step 3: Gate to Phase 4
Compare scanner metrics and data-quality exclusions against 12-symbol baseline; verify watchlist preview before any explicit update; assess monitor runtime and eligibility for a larger shortlist. Do not treat the current watchlist as a representative historical universe for backtesting. Record survivorship and data-source limitations.

No GBM orders, automated live trading or database migrations are included.
