# 行情 API health：Token 默认缓存 12 小时，再 POST health，全部 status 须为 UP。
# 优先 QUOTES_LOGIN_CODE / QUOTES_LOGIN_PASSWORD；否则回退 QUOTES_HEALTH_TOKEN。
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
            $name = $pair[0].Trim()
            $value = $pair[1].Trim()
            $existing = [Environment]::GetEnvironmentVariable($name, "Process")
            if ($existing -and $existing.Trim()) { return }
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

$wecomEnv = Join-Path $RepoRoot "config\wecom.env"
if (Test-Path $wecomEnv) {
    Get-Content $wecomEnv | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $pair = $_ -split '=', 2
        if ($pair.Count -eq 2) {
            $name = $pair[0].Trim()
            $value = $pair[1].Trim()
            $existing = [Environment]::GetEnvironmentVariable($name, "Process")
            if ($existing -and $existing.Trim()) { return }
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

$argsList = @("-m", "scripts.cron_task_monitor", "--health-monitor")
if ($Json) { $argsList += "--json" }
if ($NoNotify) { $argsList += "--no-notify" }

python @argsList
exit $LASTEXITCODE
