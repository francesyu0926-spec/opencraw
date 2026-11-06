# Register Windows Task Scheduler: production monitor (every 5 minutes).
# Uses repo-relative script path + WorkingDirectory (no hardcoded drive letters in /TR).
#
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File scripts\register_monitor_scheduled_task.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\register_monitor_scheduled_task.ps1 -Unregister
#
# Re-register after moving the repo folder; WorkingDirectory is resolved at register time.

param(
    [string]$TaskName = "OpenCraw-Monitor-Unified",
    [int]$IntervalMinutes = 5,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$RunnerRelative = "scripts\run_monitor_production.ps1"
$RunnerFull = Join-Path $RepoRoot $RunnerRelative

if (-not (Test-Path -LiteralPath $RunnerFull)) {
    Write-Error "Missing runner: $RunnerRelative (repo=$RepoRoot)"
}

$user = "$env:USERDOMAIN\$env:USERNAME"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed task (if present): $TaskName"
    exit 0
}

$psArgs = @(
    "-NoProfile"
    "-WindowStyle", "Hidden"
    "-ExecutionPolicy", "Bypass"
    "-File", $RunnerRelative
    "-Json"
)

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ($psArgs -join " ") `
    -WorkingDirectory $RepoRoot

# RepetitionDuration 不能用 TimeSpan::MaxValue；用足够长的天数即可
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User $user `
    -RunLevel Limited `
    -Force | Out-Null

Write-Host "Registered: $TaskName"
Write-Host "  WorkingDirectory: $RepoRoot"
Write-Host "  Action (relative): powershell.exe ... -File $RunnerRelative -Json"
Write-Host "  Every $IntervalMinutes minute(s), run as $user"

Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo |
    Format-List TaskName, LastRunTime, NextRunTime, LastTaskResult

exit 0
