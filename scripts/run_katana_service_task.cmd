@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    exit /b 1
)

if not exist "logs\service" (
    mkdir "logs\service"
)

".venv\Scripts\python.exe" -m app.run_operational_maintenance ^
  --project-directory "%CD%" ^
  --maximum-megabytes 5 ^
  --backup-count 5

echo ==================================================>> "logs\service\katana_service.log"
echo Project KATANA Service task started at %DATE% %TIME%>> "logs\service\katana_service.log"

".venv\Scripts\python.exe" -m app.run_katana_service ^
  --database-path data\katana.db ^
  --dashboard-port 8000 ^
  --enable-dynamic-watchlist-schedule ^
  --enable-morning-preflight-schedule ^
  --enable-daily-report-schedule ^
  --enable-paper-trading-schedule ^
  --tailscale-wait-attempts 60 ^
  --tailscale-wait-seconds 5 ^
  >> "logs\service\katana_service.log" 2>&1

set "EXIT_CODE=%ERRORLEVEL%"

echo Project KATANA Service task stopped with exit code %EXIT_CODE% at %DATE% %TIME%>> "logs\service\katana_service.log"

exit /b %EXIT_CODE%
