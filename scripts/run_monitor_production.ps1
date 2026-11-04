# 生产监控调度（见 config/monitor_schedule.production.yaml）
# - 00:00–05:00  ELK 数据同步，每 15 分钟
# - 09:00–15:30  WebSocket，每 10 分钟
# - 09:00–23:39  HTTP health，每 15 分钟
# - 07:00–20:30  自动化写稿验证，每 5 分钟（到期任务才执行 verify run --due）
#
# 任务计划：每天重复，间隔 5 分钟触发调度器（见 dispatcher_interval_minutes）。
# 至 2026-11-11：整点 (:00) 执行且成功的 job 会发企微（notify_success_trial，无需 -NotifySuccess）。
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
