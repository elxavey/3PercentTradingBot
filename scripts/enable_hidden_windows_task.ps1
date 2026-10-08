# Opt-in conversion of the EXISTING TradePilot task to an invisible WScript host.
# Retains the task's existing encoded command, schedule, principal and settings.
[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$TaskName = "TradePilot Market Scanner")
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Windows is required." }
$launcher = Join-Path $PSScriptRoot "run_hidden_scheduler.vbs"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Missing hidden launcher: $launcher"
}
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
if ($task.Actions.Count -ne 1) {
    throw "Expected exactly one existing task action; no changes made."
}
$existing = $task.Actions[0]
if ($existing.Execute -notmatch '(?i)(^|[\\/])powershell(?:\.exe)?$') {
    throw "Existing task is not a PowerShell action; no changes made."
}
$match = [regex]::Match($existing.Arguments, '(?i)(?:^|\s)-EncodedCommand\s+([A-Za-z0-9+/=]+)(?:\s|$)')
if (-not $match.Success) {
    throw "Existing action does not have an encoded PowerShell command; no changes made."
}
$encoded = $match.Groups[1].Value
# Validate the payload before touching the registered task.
try {
    $decoded = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($encoded))
} catch {
    throw "Existing encoded command is invalid; no changes made."
}
if ($decoded -notmatch 'run_scheduled_scan\.ps1') {
    throw "Existing action does not call TradePilot scheduler; no changes made."
}
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wscript.exe" -Argument (
    '//B //Nologo "' + $launcher + '" ' + $encoded
) -WorkingDirectory $root
if ($PSCmdlet.ShouldProcess($TaskName, "Replace console action with hidden launcher (retain schedule and settings)")) {
    Set-ScheduledTask -TaskName $TaskName -Action $action | Out-Null
    Write-Host "Hidden action installed for '$TaskName'. Existing triggers, user and settings preserved."
    Write-Host "Check next run in: data\logs\windows_scheduler.log"
}
