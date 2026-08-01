@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    exit /b 1
)

".venv\Scripts\python.exe" -m app.run_dashboard_resident ^
  --database-path data\katana.db ^
  --host-mode tailscale ^
  --port 8000 ^
  --tailscale-wait-attempts 60 ^
  --tailscale-wait-seconds 5 ^
  --max-restarts 100 ^
  --restart-delay-seconds 10

exit /b %ERRORLEVEL%
