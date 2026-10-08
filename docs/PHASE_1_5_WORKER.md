# TradePilot Phase 1.5 — One-shot Background Worker

The worker runs independently of Streamlit. It uses the **existing v0.4.0**
discovery/pre-screen/scoring pipeline, then stores results in the same SQLite
database as the dashboard. It does **not** place trades, schedule itself,
run as a Windows service, or verify live quote freshness.

## PowerShell

From the repository root, after `git pull origin development`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m tradepilot.worker --universe "Test - 12 symbols"
.\.venv\Scripts\python.exe -c "from tradepilot.storage.scan_repository import list_scans; print(list_scans(limit=3))"
```

The default is the 12-symbol test universe. Other configured names are listed
in `config.py`. For example:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.worker --universe "Dynamic MX + USA - 250 symbols"
```

Use `--db "data/tradepilot.db"` to override the local database path.
`--slot "2026-10-08T14:00:00Z"` provides an explicit UTC job identity;
the same slot cannot be claimed twice. Without `--slot`, each invocation
uses a new UTC timestamp. Exit codes: **0** success, **1** failure, **2**
duplicate or already-running job.

## Safe recovery after a crash

A power loss or Ctrl+C can leave a `RUNNING` job in SQLite. New scans
will be blocked rather than guessing whether the old process is alive.

1. Confirm there is no worker process still running.
2. Find its job ID:

```powershell
.\.venv\Scripts\python.exe -c "from tradepilot.storage.database import database_connection; c=database_connection(); db=c.__enter__(); print(db.execute(\"SELECT id,started_at_utc FROM job_runs WHERE status='RUNNING'\").fetchall()); c.__exit__(None,None,None)"
```

3. Manually mark the abandoned job interrupted:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.worker --interrupt-job JOB_ID
```

4. Start a **new slot**. The old slot remains reserved and cannot be
replayed accidentally.

**Warning:** manual interruption is not a process kill. Never mark an
actually running job interrupted. The worker does not yet implement
heartbeats, PID validation, crash auto-recovery, scheduled jobs, or a
Windows Service. SQLite is local and the PC must remain on during scans.
