# 兼容旧任务计划：转发到 scripts/run_scheduled_monitors.ps1（统一 HTTP / WS / ELK 调度）。
# 新部署请直接使用 run_scheduled_monitors.ps1，触发器间隔 5 分钟、全天重复。

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoNotify,
    [switch]$Json
)

$forward = Join-Path $PSScriptRoot "run_scheduled_monitors.ps1"
& $forward -RepoRoot $RepoRoot -NoNotify:$NoNotify -Json:$Json -Job @("elk")
exit $LASTEXITCODE
