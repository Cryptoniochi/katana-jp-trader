@echo off
setlocal

if "%KABU_STATION_API_PASSWORD%"=="" (
  echo ERROR: KABU_STATION_API_PASSWORD is not set.
  exit /b 1
)

echo Project KATANA Risk Validation
echo No live orders will be submitted.
echo.

python -m app.run_paper_trading ^
  --market-data-mode kabu-station-realtime ^
  --code 7203 ^
  --database-path data\katana_risk_validation.db ^
  --maximum-cycles 20 ^
  --cycle-interval 30 ^
  --max-position-count 1 ^
  --max-position-value 100000 ^
  --max-total-exposure 100000 ^
  --minimum-cash-balance 9900000 ^
  --max-daily-loss 1000 ^
  --max-daily-entries 1

exit /b %ERRORLEVEL%
