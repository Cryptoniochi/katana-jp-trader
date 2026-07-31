param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$ruleName = "Project KATANA Dashboard TCP $Port"

$existing = Get-NetFirewallRule `
  -DisplayName $ruleName `
  -ErrorAction SilentlyContinue

if ($null -eq $existing) {
    New-NetFirewallRule `
      -DisplayName $ruleName `
      -Direction Inbound `
      -Action Allow `
      -Protocol TCP `
      -LocalPort $Port `
      -Profile Private
}

Write-Host "Windows Firewall rule is ready:"
Write-Host $ruleName
