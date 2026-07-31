param(
    [string]$DatabasePath = "data\katana.db",
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$arguments = @(
    "-m",
    "app.dashboard",
    "--host",
    "127.0.0.1",
    "--port",
    "$Port",
    "--database",
    $DatabasePath
)

if ($NoBrowser) {
    $arguments += "--no-browser"
}

python @arguments
exit $LASTEXITCODE
