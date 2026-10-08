# TradePilot Phase 1.8 — install an opt-in Windows scheduled task.
# Run interactively in PowerShell on Windows. No task is created by git pull.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "TradePilot Market Scanner",
    [string]$Universe = "Test - 12 symbols",
    [int]$IntervalMinutes = 5
)
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Windows is required." }
if ($IntervalMinutes -lt 1 -or $IntervalMinutes -gt 30) {
    throw "IntervalMinutes must be between 1 and 30."
}
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = Join-Path $PSScriptRoot "run_scheduled_scan.ps1"
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Missing virtualenv Python: $python. Install dependencies first."
}
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Missing launcher: $launcher"
}
# Task action uses encoded PowerShell command to safely handle paths and
# universe names with spaces/quotes. Never invokes a shell to construct Python args.
$command = "& '$($launcher.Replace("'", "''"))' -Universe '$($Universe.Replace("'", "''"))'"
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
    "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded"
) -WorkingDirectory $root
# Run every N minutes for ten years; local clock trigger is not the exchange
# calendar. The Python scheduler gates the actual market-session start.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -StartWhenAvailable:$false -WakeToRun:$false
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited
if ($PSCmdlet.ShouldProcess($TaskName, "Register TradePilot scheduled task")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal | Out-Null
    Write-Host "Installed '$TaskName' for current signed-in user."
    Write-Host "Task checks every $IntervalMinutes minute(s); Python enforces MX+US market sessions."
    Write-Host "Inspect with: Get-ScheduledTask -TaskName '$TaskName'"
    Write-Host "Disable with: Disable-ScheduledTask -TaskName '$TaskName'"
    Write-Host "Remove with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:$false"
}
