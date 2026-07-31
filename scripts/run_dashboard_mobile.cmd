@echo off
setlocal

cd /d "%~dp0\.."

python -m app.dashboard ^
  --host 127.0.0.1 ^
  --port 8000 ^
  --database data\katana.db ^
  --no-browser

exit /b %ERRORLEVEL%
