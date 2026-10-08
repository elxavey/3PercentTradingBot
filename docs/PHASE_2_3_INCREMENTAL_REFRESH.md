# Phase 2.3 — Incremental Watchlist Refresh (initial manual implementation)

Status: **implemented on development; awaiting Windows user tests and UI validation**.

The new `tradepilot/watchlist_refresh.py` selects only entries in
`WATCHING` or `PROMOTED`, with a fail-closed maximum of 50 active symbols.
It reuses `tradepilot.core.scanner_service.run_scan` without dynamic universe
discovery, and saves a new scan through the existing SQLite repository.
Terminal states are excluded. The watchlist itself is not modified;
promotions and expiry remain explicit actions in Watchlist.

Run preview:

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m tradepilot.watchlist_refresh
```

To run an actual research refresh, open Streamlit and select
**Incremental Refresh**; review symbols and confirm. Alternatively:
`python -m tradepilot.watchlist_refresh --run`.

**Limitations before 2.3 can be considered complete:** the legacy scanner
does not expose a verified bar/quote timestamp for every result, so
`freshness_verified=False` is explicitly stored and displayed. No live
signal claims. The UI currently reports run counts and scan ID, but
per-symbol refresh errors and fully verified freshness are not yet
implemented. Historical score deltas are now available through a read-only
comparison of the saved incremental scan with each symbol's last applied
Watchlist scan. Missing symbols are NOT_EVALUATED, never automatically failed.
The UI explicitly labels freshness UNKNOWN: database ingestion timestamps
must never be represented as verified market quote timestamps. No scheduled worker integration (2.4).
A candidate excluded by the scanner pre-screen is not interpreted as a
Quality Gate failure. Never infer expiry from absence.

No real orders are placed. The Windows Task Scheduler task is unchanged.


## Compare a saved incremental scan

Open Streamlit → **Incremental Refresh** → **Historical score comparison**.
Select the saved scan. Score delta is new Opportunity Score minus the last
**applied** Watchlist score; it does not modify the watchlist or orders.
The selected scan must have universe name `Watchlist incremental research`.

Run validation:

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\watchlist_refresh.py pages\3_Incremental_Refresh.py tests\test_watchlist_refresh.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected 127 tests (previous 125 + 2). Do not update the Windows task.
