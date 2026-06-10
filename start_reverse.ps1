# start_reverse.ps1 — launch the commentary pipeline in REVERSE RANK mode (KOSL scoring)
# Last place scores first; crashed drivers are always last.
# KOSL races are auto-reversed even without this script, but unnamed/other races need this.
# Usage:  right-click → Run with PowerShell,  or in a terminal:  .\start_reverse.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Kill any stale listener/worker so port 8766 is free and there is only one of each.
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like '*ws_listener*' -or $_.CommandLine -like '*commentary_worker*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 1

# Trim old data: keep only the previous race.
python cleanup.py --keep 1

# Listener in reverse-rank mode
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$PSScriptRoot'; python ws_listener.py --reverse-rank"

# Give it a moment to bind port 8766, then start the commentary worker in reverse-rank mode
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$PSScriptRoot'; python commentary_worker.py --min-priority 3 --interval 45 --from-start --reverse-rank"

Write-Host "Launched listener + commentary worker in REVERSE RANK mode."
Write-Host "(Last place scores first; crashed drivers are always last.)"
Write-Host "Make sure the TamperMonkey pill shows on the Torn racing page, then race."
Write-Host "Stop everything with:  .\stop.ps1"
