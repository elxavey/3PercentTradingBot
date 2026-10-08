# One-shot scheduled watchlist research; independent of the existing market scanner.
param([int]$Limit = 50)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "data\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir "watchlist_scheduler.log"
Push-Location $root
try {
    "[$((Get-Date).ToString('o'))] START watchlist scheduler" | Out-File $log -Append -Encoding utf8
    & $python -m tradepilot.watchlist_scheduler --limit $Limit 2>&1 |
        Out-File $log -Append -Encoding utf8
    $code = $LASTEXITCODE
    "[$((Get-Date).ToString('o'))] EXIT code=$code" | Out-File $log -Append -Encoding utf8
    exit $code
} catch {
    "[$((Get-Date).ToString('o'))] ERROR $($_.Exception.GetType().Name)" |
        Out-File $log -Append -Encoding utf8
    exit 1
} finally {
    Pop-Location
}
