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
historical score deltas, per-symbol refresh errors and fully verified
freshness are not yet implemented. No scheduled worker integration (2.4).
A candidate excluded by the scanner pre-screen is not interpreted as a
Quality Gate failure. Never infer expiry from absence.

No real orders are placed. The Windows Task Scheduler task is unchanged.
