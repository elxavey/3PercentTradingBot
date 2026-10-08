# Phase 1.9 — Monitoring & Operational Dashboard (first iteration)

This iteration is **read-only** and adds no broker orders, no recovery
actions, no new migrations, and no scanner/scoring changes.

## Components

- `tradepilot/monitoring.py`: SQLite operational snapshot API and CLI.
- `pages/1_Operations.py`: Streamlit Operations page, separate from scanner execution.
- `tests/test_monitoring.py`: five tests of empty data, limits, joins, stale
  heartbeat and non-mutating behavior.

The page displays scheduled job history, heartbeat state, latest persisted
scan, quality-pass counts, elapsed scan time and failures. Saved scans
include manual UI runs as well as scheduled worker runs. A stale heartbeat
is diagnostic, **not** proof the worker is stopped.

Windows Task Scheduler's own `LastTaskResult` is **not** stored in SQLite.
For OS-level scheduling status use:
`Get-ScheduledTaskInfo -TaskName "TradePilot Market Scanner"`.

## Verify locally (from repo root)

```powershell
Clear-Host
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\monitoring.py pages\1_Operations.py tests\test_monitoring.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected **96 tests** (previously 91 plus five new monitoring tests).

Read the snapshot without opening Streamlit:

```powershell
Clear-Host
.\.venv\Scripts\python.exe -m tradepilot.monitoring --limit 5
```

Start the existing UI:

```powershell
Clear-Host
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **Operations** in Streamlit's page navigation. No scan is launched
by visiting Operations. If the page is empty, wait for a persisted run
or check that the app and scheduler use the same `data/tradepilot.db`.

## Remaining validation

- User confirms tests and page load on Windows.
- Real market-window scheduled scan and dashboard appearance remain
  unverified until a market session.
- Later iterations may add richer filters, time-series charts and
  diagnostics; they should stay read-only unless separately approved.
