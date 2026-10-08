# TradePilot Phase 1.7 — Operational Reliability (part 1)

This increment adds a **30-second background worker heartbeat**, SQLite
schema v3 and a read-only operational status command. It preserves the
scanner v0.4.0 rules, does not change the scheduler's market windows, and
does not place orders.

## Windows validation

```powershell
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe -m tradepilot.operations
.\.venv\Scripts\python.exe -m tradepilot.worker --universe "Test - 12 symbols"
.\.venv\Scripts\python.exe -m tradepilot.operations
```

Expected test count: **76** (69 prior + 7 new).

The status command prints recent job rows as JSON. For RUNNING jobs:
`RECENT` means the last heartbeat is within 180 seconds;
`STALE_UNVERIFIED` means heartbeat is missing/old/future.
For terminal jobs it reports `NOT_RUNNING`.

**Safety:** a stale heartbeat is NOT proof that the worker died.
Neither the status command nor scheduler releases locks or replays a slot.
Before manual interruption, verify that no worker process remains active.
See `docs/PHASE_1_5_WORKER.md` for explicit recovery.

## Boundaries and follow-up

- Heartbeat runs in a daemon thread, independent of long network calls;
  worker errors still record FAILED and the scan remains protected by SQLite.
- No PID/process identity verification, Windows auto-start, process watchdog,
  durable audit/event log, or unattended crash recovery is implemented yet.
- Do not run concurrent workers against separate database paths expecting
  cross-database locking.
- The real scheduled-market-window test remains pending; this increment
  does not substitute for that operational test.
