# Opt-in separate hidden task; never modifies TradePilot Market Scanner.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "TradePilot Watchlist Refresh",
    [int]$IntervalMinutes = 5,
    [int]$Limit = 50
)
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Windows required" }
if ($IntervalMinutes -lt 1 -or $IntervalMinutes -gt 30) { throw "Invalid interval" }
if ($Limit -lt 1 -or $Limit -gt 50) { throw "Invalid symbol limit" }
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$launcher = Join-Path $PSScriptRoot "run_scheduled_watchlist.ps1"
$hidden = Join-Path $PSScriptRoot "run_hidden_scheduler.vbs"
foreach ($file in @($python, $launcher, $hidden)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing: $file" }
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw "Task already exists: $TaskName. No changes made."
}
$command = "& '$($launcher.Replace("'", "''"))' -Limit $Limit"
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wscript.exe" -Argument (
    '//B //Nologo "' + $hidden + '" ' + $encoded
) -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable:$false -WakeToRun:$false
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited
if ($PSCmdlet.ShouldProcess($TaskName, "Register separate hidden Watchlist Refresh task")) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal | Out-Null
    Write-Host "Installed: $TaskName (existing market scanner unchanged)"
    Write-Host "Log: data\logs\watchlist_scheduler.log"
}
