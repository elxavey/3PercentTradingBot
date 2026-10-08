# Phase 2.4 — Watchlist Automation

Status: **code published on development, awaiting local Windows tests and explicit installation approval**.

## Design
- The existing `TradePilot Market Scanner` Windows task is **not modified**.
- The new optional `TradePilot Watchlist Refresh` task runs a hidden
  one-shot check every five minutes. It is **not installed by git pull**.
- The Python scheduler checks the actual XNYS and XMEX calendars. Only one
  combined-market refresh is eligible each day, **60 minutes after the later
  opening**, within a 30-minute start window. No holiday or missed-slot replay.
- SQLite `job_runs` reserves the UTC slot atomically with
  `job_name=watchlist_refresh`. Concurrent or repeated ticks skip. FAILED
  and RUNNING jobs are not automatically retried or cleared.
- The scanner examines only active Watchlist symbols (max 50) and saves a
  new research scan. It **does not update** Watchlist entries, promote/expire
  symbols, place orders, or claim live quote freshness.
- Logs: `data/logs/watchlist_scheduler.log`. Job history: `job_runs`;
  successful research scan: `scan_runs`.
- This schedule is a daily-history research refresh, **not** the original
  roadmap's 5-minute intraday bar-refresh cadence. Intraday provider and
  verified quote timestamps remain future work.

## Validate before installation

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m py_compile tradepilot\watchlist_scheduler.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m tradepilot.watchlist_scheduler --dry-run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_watchlist_task.ps1" -WhatIf
```

Dry-run will report NOT_DUE outside its window. The -WhatIf installation
must not create a task.

## Explicit opt-in install (only after reviewing tests)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_watchlist_task.ps1"
Get-ScheduledTask -TaskName "TradePilot Watchlist Refresh"
Get-ScheduledTaskInfo -TaskName "TradePilot Watchlist Refresh"
Get-Content ".\data\logs\watchlist_scheduler.log" -Tail 15
```

The existing hidden scanner task stays untouched. A Windows manual
`Start-ScheduledTask` outside the exchange window should log NOT_DUE,
not force a market-data refresh. Disable the new task with
`Disable-ScheduledTask -TaskName "TradePilot Watchlist Refresh"`.

**Operational limitations:** Windows must be running and the interactive
user signed in. No automatic recovery of a stuck RUNNING row; inspect the
process and use a deliberate recovery workflow. A one-shot task can be
missed during sleep. The scheduled refresh stores research observations,
but leaves human-reviewed lifecycle changes manual.
