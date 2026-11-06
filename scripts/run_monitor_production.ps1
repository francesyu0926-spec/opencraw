# 生产监控调度（见 config/monitor_schedule.production.yaml）
# 调度器每 5 分钟；elk/写稿按子任务窗口触发，ws 10min，health 15min。
# 企微：notify_success_until / notify_success_trial(health,ws 整点) / notify_on_run_complete(elk,writing)
# 详见 docs/cron_task_monitor.md 或 python scripts/print_schedule.py
#
# 任务计划：每天重复，间隔 5 分钟触发调度器（dispatcher_interval_minutes: 5）。
# 程序：powershell.exe -ExecutionPolicy Bypass -File scripts\run_monitor_production.ps1

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoNotify,
    [switch]$Json,
    [switch]$DryRun,
    [switch]$Force,
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
if ($Job) { $params.Job = $Job }

& $forward @params
exit $LASTEXITCODE
