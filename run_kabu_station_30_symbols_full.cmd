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

echo Project KATANA Sprint91-1A Full Session
echo Watchlist: watchlist_kabu_30.txt
echo Database: data\katana_sprint91_validation.db
echo Maximum cycles: 780
echo Cycle interval seconds: 30
echo No live orders will be submitted.
echo.

python -m app.run_paper_trading ^
  --market-data-mode kabu-station-realtime ^
  --watchlist watchlist_kabu_30.txt ^
  --database-path data\katana_sprint91_validation.db ^
  --maximum-cycles 780 ^
  --cycle-interval 30

set EXIT_CODE=%ERRORLEVEL%
echo.
echo Exit code: %EXIT_CODE%
exit /b %EXIT_CODE%
