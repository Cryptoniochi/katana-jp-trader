@echo off
setlocal
cd /d "C:\projects\katana"
"C:\projects\katana\.venv\Scripts\python.exe" -m app.run_dashboard_resident --database-path "data\katana.db" --port 8000 --host-mode tailscale --tailscale-wait-attempts 60 --tailscale-wait-seconds 5 --max-restarts 100 --restart-delay-seconds 10 >> "C:\projects\katana\logs\dashboard\dashboard_resident.log" 2>&1
exit /b %ERRORLEVEL%
