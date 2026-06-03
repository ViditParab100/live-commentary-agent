# stop.ps1 — stop the listener and commentary worker, free port 8766.
Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -like '*ws_listener*' -or $_.CommandLine -like '*commentary_worker*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "stopped PID $($_.ProcessId)" }

if (netstat -ano | Select-String ":8766.*LISTENING") { "port 8766 still held" } else { "port 8766 free" }
