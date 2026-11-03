# 行情 API health：POST + Token 头，全部 status 须为 UP。
# 任务计划示例：每 5 分钟执行一次（全天）。
# 程序：powershell.exe -ExecutionPolicy Bypass -File D:\Document\CODE\opencraw\scripts\run_health_monitor.ps1

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoNotify,
    [switch]$Json
)

Set-Location $RepoRoot
$env:PYTHONPATH = "."

$healthEnv = Join-Path $RepoRoot "config\health.env"
if (Test-Path $healthEnv) {
    Get-Content $healthEnv | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $pair = $_ -split '=', 2
        if ($pair.Count -eq 2) {
            Set-Item -Path "Env:$($pair[0].Trim())" -Value $pair[1].Trim()
        }
    }
}

$wecomEnv = Join-Path $RepoRoot "config\wecom.env"
if (Test-Path $wecomEnv) {
    Get-Content $wecomEnv | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $pair = $_ -split '=', 2
        if ($pair.Count -eq 2) {
            Set-Item -Path "Env:$($pair[0].Trim())" -Value $pair[1].Trim()
        }
    }
}

$argsList = @("-m", "scripts.cron_task_monitor", "--health-monitor")
if ($Json) { $argsList += "--json" }
if ($NoNotify) { $argsList += "--no-notify" }

python @argsList
exit $LASTEXITCODE
