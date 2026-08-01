@echo off
setlocal

cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv\Scripts\python.exe was not found.
    exit /b 1
)

".venv\Scripts\python.exe" -m app.run_katana_service

exit /b %ERRORLEVEL%
