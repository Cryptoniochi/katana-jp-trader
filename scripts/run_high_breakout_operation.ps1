param(
    [string]$DatabasePath = "data\katana.db",
    [string]$WatchlistPath = "config\watchlist.txt",
    [switch]$StartPaperTrading,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$arguments = @(
    "-m",
    "app.run_high_breakout_operation",
    "--database-path",
    $DatabasePath,
    "--watchlist-path",
    $WatchlistPath
)

if ($StartPaperTrading) {
    $arguments += "--start-paper-trading"
}

if ($DryRun) {
    $arguments += "--paper-trading-dry-run"
}

python @arguments
exit $LASTEXITCODE
