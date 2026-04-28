@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'app\.py') }); if ($procs.Count -eq 0) { Write-Host 'No process found running app.py.'; exit 0 }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId; Write-Host ('Stopped PID ' + $p.ProcessId) } }"
exit /b %ERRORLEVEL%
