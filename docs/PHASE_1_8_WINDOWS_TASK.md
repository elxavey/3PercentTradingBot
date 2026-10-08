# TradePilot Phase 1.8 — Windows Task Scheduler Integration

This phase adds **opt-in** local Windows Task Scheduler integration.
Nothing is registered or enabled merely by pulling the repository.
The existing scanner, score rules, worker, SQLite persistence and
exchange-calendar gate remain unchanged.

## How it works

The Windows task starts a **one-shot** Python scheduler check every 5
minutes (not a continuously running Python loop). The scheduler itself
decides whether both `XNYS` and `XMEX` are open and the daily slot is
within its 15-minute-after-later-open / 30-minute-start window.
Outside the window it logs `NOT DUE` and exits without scanning.
Within the window, the existing SQLite worker slot prevents duplicates.

Windows task settings: **IgnoreNew** for overlapping instances,
**StartWhenAvailable false** (no OS-level catch-up), no wake from sleep,
3-hour maximum task duration, runs only when the current user is logged in,
with limited privileges. The PC must be powered on, awake and signed in.
The task's repetition trigger lasts ten years, after which it must be
re-registered. The scheduler itself has no guaranteed real-time feed.

## Step 1: update and run tests (safe)

```powershell
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Expected: **91 tests** (83 previous + 8 static integration tests).
The eight new tests do not prove Windows Task Scheduler registration works;
that requires the next steps on the actual Windows machine.

## Step 2: preview installation (NO task created)

```powershell
.\scripts\install_windows_task.ps1 -WhatIf
```

Review the proposed task. The installer checks that `.venv` exists.
It will not overwrite a task of the same name silently.

## Step 3: explicitly opt in to installation

Only after reviewing the settings:

```powershell
.\scripts\install_windows_task.ps1
Get-ScheduledTask -TaskName "TradePilot Market Scanner"
```

The default universe is `Test - 12 symbols` and the poll interval is
5 minutes. Do not switch to a larger dynamic universe until the small
test is operationally verified. To inspect recent logs:

```powershell
Get-Content .\data\logs\windows_scheduler.log -Tail 30
```

If you are outside the market slot, `NOT DUE` is the expected output.
During the slot, check SQLite status:

```powershell
.\.venv\Scripts\python.exe -m tradepilot.operations
```

You can also manually run the **one-shot launcher** without installing
any task:

```powershell
.\scripts\run_scheduled_scan.ps1
```

This still obeys market hours and SQLite duplicate protection.

## Pause or remove

```powershell
Disable-ScheduledTask -TaskName "TradePilot Market Scanner"
Enable-ScheduledTask -TaskName "TradePilot Market Scanner"
Unregister-ScheduledTask -TaskName "TradePilot Market Scanner" -Confirm:$false
```

Use `Get-ScheduledTaskInfo -TaskName "TradePilot Market Scanner"` for
Task Scheduler's last run and exit result.

## Limitations

- The installer is designed for **Windows PowerShell** and needs the
  ScheduledTasks module. Registration may be blocked by corporate policy.
- It does not install a Windows service, run while signed out, wake the PC,
  recover a crashed job, or execute missed market sessions later.
- The SQLite job may remain RUNNING after a forced shutdown; use the
  documented operator-confirmed recovery process, never auto-unlock.
- Scheduled runs use the same local Python environment and working folder
  as the manual runs. Logs are local and may grow over time.
- No live brokerage orders, trade signals, GBM recommendations or
  intraday execution guarantees are added by this integration.
