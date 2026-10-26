@echo off
setlocal EnableExtensions
cd /d "C:\projects\katana"
"C:\projects\katana\.venv\Scripts\python.exe" -m app.run_katana_service_watchdog >> "C:\projects\katana\logs\service\katana_service_watchdog_task.log" 2>&1
exit /b %ERRORLEVEL%
