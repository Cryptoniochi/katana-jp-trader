@echo off

setlocal EnableExtensions

cd /d "C:\projects\katana"

if not exist "C:\projects\katana\.venv\Scripts\python.exe" (
    echo ERROR: Python executable was not found.
    exit /b 1
)

if not exist "C:\projects\katana\logs\service" mkdir "C:\projects\katana\logs\service"

"C:\projects\katana\.venv\Scripts\python.exe" -m app.run_operational_maintenance --project-directory "C:\projects\katana"

if errorlevel 1 (
    echo ERROR: Operational log maintenance failed.
    exit /b 1
)

"C:\projects\katana\.venv\Scripts\python.exe" -m app.run_katana_service_resilient ^
    --database-path "data\katana.db" ^
    --dashboard-port 8000 ^
    --enable-dynamic-watchlist-schedule ^
    --enable-universe-daily-schedule ^
    --enable-high-breakout-schedule ^
    --enable-morning-preflight-schedule ^
    --enable-daily-report-schedule ^
    --enable-paper-trading-schedule ^
    --tailscale-wait-attempts 60 ^
    --tailscale-wait-seconds 5 ^
    >> "C:\projects\katana\logs\service\katana_service.log" 2>&1

exit /b %ERRORLEVEL%
