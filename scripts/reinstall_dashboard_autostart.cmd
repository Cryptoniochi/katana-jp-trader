@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    exit /b 1
)

".venv\Scripts\python.exe" -m app.dashboard_autostart remove
".venv\Scripts\python.exe" -m app.dashboard_autostart install ^
  --project-directory "%CD%" ^
  --database-path data\katana.db ^
  --host-mode tailscale ^
  --port 8000

exit /b %ERRORLEVEL%
