param(
    [string]$DatabasePath = "data\katana.db",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$tailscale = Get-Command tailscale `
    -ErrorAction SilentlyContinue

if ($null -eq $tailscale) {
    throw "Tailscale CLI was not found. Install Tailscale for Windows and sign in first."
}

$tailscaleIp = (
    tailscale ip -4 |
    Select-Object -First 1
).Trim()

if ([string]::IsNullOrWhiteSpace($tailscaleIp)) {
    throw "Unable to obtain the Tailscale IPv4 address. Confirm that Tailscale is connected."
}

Write-Host "Project KATANA secure mobile dashboard"
Write-Host "URL: http://${tailscaleIp}:${Port}/mobile"
Write-Host "The server binds only to the Tailscale address."
Write-Host "Press Ctrl+C to stop."

python -m app.dashboard `
    --host $tailscaleIp `
    --port $Port `
    --database $DatabasePath `
    --no-browser

exit $LASTEXITCODE
