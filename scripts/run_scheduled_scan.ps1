# Invoked by the Windows Task Scheduler. Runs ONE scheduler tick, never --loop.
param([string]$Universe = "Test - 12 symbols")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "data\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$logFile = Join-Path $logs "windows_scheduler.log"
$timestamp = (Get-Date).ToString("o")
try {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Virtualenv Python not found: $python"
    }
    Push-Location $root
    try {
        "[$timestamp] START scheduler check universe=$Universe" | Out-File -FilePath $logFile -Append -Encoding utf8
        & $python -m tradepilot.scheduler --universe $Universe 2>&1 |
            Out-File -FilePath $logFile -Append -Encoding utf8
        $code = $LASTEXITCODE
        "[$((Get-Date).ToString('o'))] EXIT code=$code" | Out-File -FilePath $logFile -Append -Encoding utf8
        exit $code
    } finally {
        Pop-Location
    }
} catch {
    "[$((Get-Date).ToString('o'))] ERROR $($_.Exception.GetType().Name): $($_.Exception.Message)" |
        Out-File -FilePath $logFile -Append -Encoding utf8
    exit 1
}
