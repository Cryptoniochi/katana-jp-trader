@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    exit /b 1
)

echo Stopping any process listening on TCP 8000...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
    echo Stopping PID %%P
    taskkill /PID %%P /T /F >nul 2>&1
)

echo Migrating Windows scheduled task...
".venv\Scripts\python.exe" -m app.katana_service_autostart migrate ^
  --project-directory "%CD%" ^
  --task-command scripts\run_katana_service_task.cmd

if errorlevel 1 exit /b %ERRORLEVEL%

echo Migration completed.
echo Start the new task with:
echo schtasks /Run /TN "Project KATANA Service"
exit /b 0
