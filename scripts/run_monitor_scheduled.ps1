# Windows 任务计划：每天 00:00 起，重复任务间隔 15 分钟，持续 5 小时。
# 操作：任务计划程序 → 触发器 → 每天 00:00 → 重复任务 every 15 minutes，持续 5 hours。
# 程序：powershell.exe -ExecutionPolicy Bypass -File D:\Document\CODE\opencraw\scripts\run_monitor_scheduled.ps1

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

Set-Location $RepoRoot

$now = Get-Date
$start = $now.Date
$end = $start.AddHours(5)

if ($now -lt $start -or $now -gt $end) {
    Write-Host "skip: outside 00:00-05:00 (now=$($now.ToString('yyyy-MM-dd HH:mm')))"
    exit 0
}

$env:PYTHONPATH = "."
python -m scripts.cron_task_monitor -c config/cron_tasks.yaml
exit $LASTEXITCODE
