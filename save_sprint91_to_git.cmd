@echo off
setlocal

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
  echo ERROR: This folder is not a Git repository.
  exit /b 1
)

echo Current Git status:
git status --short
echo.

git add ^
  app ^
  tests ^
  docs ^
  pyproject.toml ^
  watchlist_kabu_30.txt ^
  run_kabu_station_30_symbols_short.cmd ^
  run_kabu_station_30_symbols_full.cmd ^
  run_katana_full_session.cmd ^
  run_katana_short_session.cmd

if errorlevel 1 (
  echo ERROR: git add failed.
  exit /b 1
)

git diff --cached --quiet
if not errorlevel 1 (
  echo No staged changes. Nothing to commit.
  exit /b 0
)

git commit -m "Integrate kabu Station realtime paper trading and Sprint91 validation"

if errorlevel 1 (
  echo ERROR: git commit failed.
  exit /b 1
)

echo.
echo Local Git commit completed.
git log -1 --oneline
echo.
echo To save to GitHub, run:
echo git push

exit /b 0
