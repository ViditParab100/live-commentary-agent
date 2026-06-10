# start.ps1 — launch the live commentary pipeline (listener + commentary worker)
# Usage:  right-click → Run with PowerShell,  or in a terminal:  .\start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Kill any stale listener/worker so port 8766 is free and there is only one of each.
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like '*ws_listener*' -or $_.CommandLine -like '*commentary_worker*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 1

# Trim old data: keep only the previous race, so once this race starts there
# are exactly two on disk (current + previous).
python cleanup.py --keep 1

# Listener in its own window (captures the race, detects events)
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$PSScriptRoot'; python ws_listener.py"

# Give it a moment to bind port 8766, then start the commentary worker
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$PSScriptRoot'; python commentary_worker.py --min-priority 3 --interval 120 --from-start"

Write-Host "Launched listener + commentary worker in two windows."
Write-Host "Make sure the TamperMonkey pill shows on the Torn racing page, then race."
Write-Host "Stop everything with:  .\stop.ps1"
