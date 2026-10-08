# Phase 1.9.2 — Operations dashboard improvements

Implemented on `development`, leaving `master` and scanner scoring unchanged.

- Scanner main title and browser title now say **TradePilot**.
- Operations shows readable status, heartbeat and duration labels.
- Timestamps display in the PC's local timezone, including the scan selector.
- Filters for job status and universe apply to the loaded history.
- A historical line chart shows Quality Gate pass counts per scheduled run.
- Saved scan selection loads persisted candidates via `get_scan`, sorted
  Quality Gate PASS first, then Opportunity Score descending.
- The PASS-only checkbox is enabled by default; this is not a buy signal.
- No new SQLite schema, no broker orders, no job recovery or automatic scans.

## Windows verification

```powershell
Clear-Host
git pull origin development
.\.venv\Scripts\python.exe -m py_compile app.py pages\1_Operations.py tradepilot\monitoring_view.py tests\test_monitoring_view.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected **101 tests** (previous 96 plus five view-helper tests).

```powershell
Clear-Host
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Visit **Operations** and verify local dates, filters, historical chart and
saved scan detail. The existing Windows Task Scheduler task is unchanged;
there is no need to reinstall it.

Limitations: filters cover only the latest configured N rows. The trend is
Quality Gate pass count, not price performance or realized returns. A
persisted scan's prices may be stale. Windows Task Scheduler's own execution
history is not represented in the SQLite job history.
