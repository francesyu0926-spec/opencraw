# 生产监控调度（见 config/monitor_schedule.production.yaml）
# - 00:00–05:00  ELK 数据同步，每 15 分钟
# - 09:00–15:30  WebSocket，每 15 分钟
# - 09:00–23:39  HTTP health，每 15 分钟
#
# 任务计划：每天重复，间隔 15 分钟，持续 1 天。
# 程序：powershell.exe -ExecutionPolicy Bypass -File scripts\run_monitor_production.ps1

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoNotify,
    [switch]$Json,
    [switch]$DryRun,
    [switch]$Force,
    [switch]$NotifySuccess,
    [string[]]$Job
)

$forward = Join-Path $PSScriptRoot "run_scheduled_monitors.ps1"
$params = @{
    RepoRoot       = $RepoRoot
    ScheduleConfig = "config/monitor_schedule.production.yaml"
    NoNotify       = $NoNotify
    Json           = $Json
    DryRun         = $DryRun
    Force          = $Force
}
if ($NotifySuccess) { $params.NotifySuccess = $true }
if ($Job) { $params.Job = $Job }

& $forward @params
exit $LASTEXITCODE
