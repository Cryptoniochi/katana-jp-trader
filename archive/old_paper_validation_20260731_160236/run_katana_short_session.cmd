@echo off
setlocal

if "%KABU_STATION_API_PASSWORD%"=="" (
  echo ERROR: KABU_STATION_API_PASSWORD is not set.
  exit /b 1
)

if not exist "watchlist_kabu_30.txt" (
  echo ERROR: watchlist_kabu_30.txt was not found.
  exit /b 1
)

if not exist "data" mkdir "data"
if not exist "logs\sprint91" mkdir "logs\sprint91"

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%I
set LOG_PATH=logs\sprint91\short_session_%STAMP%.log

echo Project KATANA Sprint91-2 Short Session
echo Watchlist: watchlist_kabu_30.txt
echo Database: data\katana_sprint91_validation.db
echo Maximum cycles: 20
echo Cycle interval seconds: 30
echo Log: %LOG_PATH%
echo No live orders will be submitted.
echo.

python -m app.run_paper_trading ^
  --market-data-mode kabu-station-realtime ^
  --watchlist watchlist_kabu_30.txt ^
  --database-path data\katana_sprint91_validation.db ^
  --maximum-cycles 20 ^
  --cycle-interval 30 > "%LOG_PATH%" 2>&1

set EXIT_CODE=%ERRORLEVEL%

type "%LOG_PATH%"

echo.
echo Exit code: %EXIT_CODE%
echo Saved log: %LOG_PATH%

exit /b %EXIT_CODE%
