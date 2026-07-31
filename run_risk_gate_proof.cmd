@echo off
setlocal

echo Project KATANA deterministic Risk Gate proof
echo No market connection. No live orders. No database writes.
echo.

python -m app.run_risk_gate_proof

set EXIT_CODE=%ERRORLEVEL%
echo.
echo Exit code: %EXIT_CODE%
exit /b %EXIT_CODE%
