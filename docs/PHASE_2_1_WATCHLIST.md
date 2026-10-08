# Phase 2.1 — Dynamic Watchlist foundation

**Status:** implementation in development; Windows verification pending.

## Delivered

- SQLite-backed research watchlist using existing `watchlist_entries` table
  (no schema migration needed).
- Deterministic top 1–50 promotion from a **successful persisted scan**:
  Quality Gate PASS, finite Opportunity Score, descending score and symbol
  tie-breaker. Defaults to top 20.
- Explicit preview vs apply in `pages/2_Watchlist.py` and CLI.
- Deduplicated symbol/market, first/last seen UTC, source scan reference.
- Reject historical scans older than existing watchlist observations;
  replaying the same scan does not duplicate entries.
- **No automatic expiry or removals yet**: previously tracked symbols
  remain until a separately specified expiry policy is implemented.
- No market data fetching, live prices, automated trading, or changed
  scanner/Windows scheduler behavior.

## Windows validation (from project root)

```powershell
Clear-Host
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\watchlist.py pages\2_Watchlist.py tests\test_watchlist.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected **106 tests** (101 existing plus five new).

Read-only CLI:

```powershell
Clear-Host
.\.venv\Scripts\python.exe -m tradepilot.watchlist
```

Open Streamlit:

```powershell
Clear-Host
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Select **Watchlist**, choose a completed saved scan, preview its ranked
candidates, and click **Apply selected scan to watchlist** only when
ready to write the list. Refresh the page to confirm persistence.

CLI preview for a known saved scan:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.watchlist --scan-id "PASTE_SCAN_ID" --limit 20
```

CLI apply (explicit write):

```powershell
.\.venv\Scripts\python.exe -m tradepilot.watchlist --scan-id "PASTE_SCAN_ID" --limit 20 --apply
```

## Next subphases

- **2.2**: explicit lifecycle (promotion/retention/expiry) based on
  exchange sessions, with deterministic tests and audit history.
- **2.3**: incremental watchlist-only refresh using cached/completed
  observations and freshness validation, avoiding broad universe rescans.
- **2.4**: independent schedule, telemetry and real-session Windows
  verification. Do not assume that 5-minute OS task checks refresh
  watchlist until a watchlist-specific job is implemented.
