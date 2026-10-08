# TradePilot — Invisible Windows Task Scheduler console

Existing task: `TradePilot Market Scanner`. This change affects **only**
how Windows launches the existing scheduler tick. It does not alter
triggers, user, task settings, Python scanner, or scan universe.

The optional script `scripts/enable_hidden_windows_task.ps1` reads the
existing PowerShell `-EncodedCommand` and replaces the task **action**
with `wscript.exe` running `scripts/run_hidden_scheduler.vbs`.
The VBScript runs the same PowerShell command with window style 0,
waits for completion, and propagates its exit code. The original
`run_scheduled_scan.ps1` still writes `data/logs/windows_scheduler.log`.

## Install / verify on the Windows host

Run from PowerShell under the same Windows account that owns the task:

```powershell
Clear-Host
cd "C:\Python Projects\3PercentTradingBot"
git switch development
git pull origin development
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\scripts\enable_hidden_windows_task.ps1 -WhatIf
```

Inspect the preview. Then, **only after approving**:

```powershell
.\scripts\enable_hidden_windows_task.ps1
Get-ScheduledTask -TaskName "TradePilot Market Scanner" | Select-Object -ExpandProperty Actions
Start-ScheduledTask -TaskName "TradePilot Market Scanner"
Start-Sleep -Seconds 12
Get-ScheduledTaskInfo -TaskName "TradePilot Market Scanner" | Select-Object LastRunTime,LastTaskResult
Get-Content ".\data\logs\windows_scheduler.log" -Tail 12
```

`NOT DUE` outside the exchange session is expected, not an error.
A scheduled market-hours scan remains to be observed on the live Windows host.
If `Set-ScheduledTask` fails due to Windows permissions, do not remove
or recreate the task; run under the task owner's permitted session or
seek approval for elevation. The new launcher is not active until
`Set-ScheduledTask` succeeds.

**Rollback**: Use Task Scheduler GUI → TradePilot Market Scanner →
Properties → Actions → Edit, set Program/script back to
`powershell.exe` and restore the previous `-EncodedCommand` from
a saved task export (export the task XML before converting if you
want an easy rollback).
