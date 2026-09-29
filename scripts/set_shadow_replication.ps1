param(
    [string]$RepositoryPath = "C:\projects\katana",
    [switch]$Disable,
    [switch]$RestartService
)

$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath($RepositoryPath)
$taskCommandPath = Join-Path `
    $repositoryRoot `
    "scripts\run_katana_service_task.cmd"

if (-not (Test-Path -LiteralPath $taskCommandPath -PathType Leaf)) {
    throw "Service task command was not found: $taskCommandPath"
}

$now = Get-Date
$weekday = $now.DayOfWeek -notin @(
    [System.DayOfWeek]::Saturday,
    [System.DayOfWeek]::Sunday
)
$time = $now.TimeOfDay
$protectedStart = [TimeSpan]::Parse("08:30:00")
$protectedEnd = [TimeSpan]::Parse("15:40:00")

if (
    $weekday -and
    $time -ge $protectedStart -and
    $time -lt $protectedEnd
) {
    throw (
        "Paper Trading保護時間中は設定を変更できません。 " +
        "15:40以降に再実行してください。 now=$now"
    )
}

$encoding = [System.Text.UTF8Encoding]::new($false)
$lines = [System.IO.File]::ReadAllLines($taskCommandPath)
$flagPattern = "--enable-shadow-replication"
$hasFlag = @(
    $lines | Where-Object { $_ -match [regex]::Escape($flagPattern) }
).Count -gt 0

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    "run_katana_service_task_before_shadow_$stamp.cmd"

[System.IO.File]::Copy(
    $taskCommandPath,
    $backupPath,
    $false
)

if ($Disable) {
    $updated = @(
        $lines | Where-Object {
            $_ -notmatch [regex]::Escape($flagPattern)
        }
    )
    $targetState = "disabled"
}
elseif ($hasFlag) {
    $updated = $lines
    $targetState = "enabled"
}
else {
    $anchorIndex = -1

    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "--enable-paper-trading-schedule") {
            $anchorIndex = $index
            break
        }
    }

    if ($anchorIndex -lt 0) {
        throw (
            "Paper Trading schedule flag was not found. " +
            "No changes were written."
        )
    }

    $updatedList = [System.Collections.Generic.List[string]]::new()

    for ($index = 0; $index -lt $lines.Count; $index++) {
        $updatedList.Add($lines[$index])

        if ($index -eq $anchorIndex) {
            $updatedList.Add(
                "  --enable-shadow-replication ^"
            )
        }
    }

    $updated = $updatedList.ToArray()
    $targetState = "enabled"
}

[System.IO.File]::WriteAllLines(
    $taskCommandPath,
    $updated,
    $encoding
)

Write-Host "Shadow replication configuration: $targetState"
Write-Host "Backup: $backupPath"
Write-Host "Task command: $taskCommandPath"

if ($RestartService) {
    schtasks /End /TN "\Project KATANA Service"
    Start-Sleep -Seconds 5
    schtasks /Run /TN "\Project KATANA Service"

    if ($LASTEXITCODE -ne 0) {
        throw "Project KATANA Service could not be started."
    }

    Write-Host "Project KATANA Service was restarted."
}
else {
    Write-Host "Resident service was not restarted."
}
