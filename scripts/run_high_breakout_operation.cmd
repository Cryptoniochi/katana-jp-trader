@echo off
setlocal

cd /d "%~dp0\.."

python -m app.run_high_breakout_operation ^
  --database-path data\katana.db ^
  --watchlist-path config\watchlist.txt

exit /b %ERRORLEVEL%
