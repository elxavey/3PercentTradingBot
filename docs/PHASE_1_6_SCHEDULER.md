# TradePilot Phase 1.6 — Market-Aware Scheduler

## Scope and safety

The scheduler is an **opt-in local Python process**, not a Windows service.
It calls the existing one-shot Background Worker and persists scans in SQLite.
It does not place trades, generate GBM orders, use live quotes, or change the
v0.4.0 scoring logic.

**Combined MX + US universe policy:** a daily scan is scheduled only when
**both** exchanges are open. We use `exchange_calendars` with `XNYS`
(New York) and `XMEX` (Mexico). Holidays, early closes, and daylight-saving
transitions come from exchange sessions, not a hardcoded clock.

Default slot: **15 minutes after the later of the two exchange openings**,
with a **30-minute maximum start window**, capped at the earlier exchange
close. The job slot is stored in UTC and uniquely claimed in SQLite.
A closed exchange, weekend, expired window, or unknown calendar session
means **no scan**. A missed session is not replayed after the PC wakes up.
No per-exchange split scanning yet: on a US-only or MX-only session the
combined scan is intentionally skipped.

This is a scheduled **daily research scan**. It does not mean historical
Yahoo prices are real-time or validated intraday observations.

## Install and verify on Windows

```powershell
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Run a one-time decision check **without executing the scanner**:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.scheduler --dry-run
```

Run **one** check that will execute only if the slot is currently due:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.scheduler
```

Start the scheduler loop (PC must stay awake; Ctrl+C to stop):

```powershell
.\.venv\Scripts\python.exe -m tradepilot.scheduler --loop --universe "Test - 12 symbols"
```

For a larger scan, select an existing universe:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.scheduler --loop --universe "Dynamic MX + USA - 250 symbols"
```

The scheduler polls every 60 seconds by default (minimum 60).
`--delay-minutes`, `--max-lateness-minutes`, `--poll-seconds`,
`--db` and `--universe` are configurable. Each market day gets one
stable UTC slot; the worker's SQLite uniqueness constraint prevents a
second successful/failed attempt from silently repeating the same slot.
A still-RUNNING job blocks a new one; use the manual recovery procedure
in `docs/PHASE_1_5_WORKER.md` only after verifying the worker is stopped.

## Operational limits

- No Windows auto-start, OS Task Scheduler registration, PID heartbeat,
  self-healing service or catch-up after downtime.
- `exchange_calendars` is a maintained third-party schedule dataset;
  verify updates for future holiday changes or special closures.
- A combined-universe scan may take longer than its *start* window.
  The calendar gates when it starts, not whether every exchange remains
  open through completion.
- No exchange-specific quote freshness, order eligibility, live fills,
  intraday signal validation, or execution safeguards have been connected.
- A process terminated without clean shutdown may leave RUNNING in SQLite;
  manual intervention is required, and the same slot remains reserved.
