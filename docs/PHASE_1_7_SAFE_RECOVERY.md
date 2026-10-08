# TradePilot — Phase 1.7 Part 2: Safe Recovery

A stale heartbeat does **not** prove a Windows worker process has exited.
Recovery is manual and conservative. No auto-unlock or replay.

## Validate on Windows

```powershell
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m tradepilot.operations
```

Expected test count: **83** (76 prior + 7 new). These tests use temporary
databases and do not touch the real scheduler's job state.

## Only if a real RUNNING job is abandoned

1. Inspect `python -m tradepilot.operations`. Identify the exact job ID.
2. Verify in Windows Task Manager/PowerShell that the previous worker
   process is **not running**. If uncertain, **do not recover**.
3. Wait at least 180 seconds since the last heartbeat.
4. Only after confirming it is stopped, run:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.recovery --job-id "PASTE-EXACT-JOB-ID" --confirm-stopped
```

This changes RUNNING to INTERRUPTED only if the heartbeat is old enough
and the operator explicitly confirms shutdown. It never frees the same
scheduled slot for a retry. Another future slot may be claimed normally.

The existing worker CLI `--interrupt-job` now also requires
`--confirm-stopped` and uses the same safeguards.

## Remaining limits

- Manual process verification is required; the program does not yet
  validate a Windows PID, process creation time or machine boot identity.
- A heartbeat can be delayed by OS sleep or SQLite contention.
- A worker that is still alive must never be manually interrupted in DB.
- No automatic service restart, Windows Task Scheduler setup, or unattended
  recovery has been implemented.
- The real market-session scheduler test remains outstanding.
