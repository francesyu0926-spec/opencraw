# 统一监控调度：HTTP health / WebSocket / ELK 数据同步（见 config/monitor_schedule.yaml）
# 任务计划：每天重复，间隔 5 分钟（与各 job 的 5/10/15 分钟周期对齐）。
# 程序：powershell.exe -ExecutionPolicy Bypass -File D:\Document\CODE\opencraw\scripts\run_scheduled_monitors.ps1

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$NoNotify,
    [switch]$Json,
    [switch]$DryRun,
    [switch]$Force,
    [string[]]$Job
)

Set-Location $RepoRoot
$env:PYTHONPATH = "."

function Import-DotEnvFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $pair = $_ -split '=', 2
        if ($pair.Count -ne 2) { return }
        $name = $pair[0].Trim()
        $value = $pair[1].Trim()
        $existing = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($existing -and $existing.Trim()) { return }
        Set-Item -Path "Env:$name" -Value $value
    }
}

Import-DotEnvFile (Join-Path $RepoRoot "config\elk.env")
Import-DotEnvFile (Join-Path $RepoRoot "config\health.env")
Import-DotEnvFile (Join-Path $RepoRoot "config\wecom.env")

if (-not $env:SSL_CERT_FILE) {
    $defaultSsl = "C:\Program Files\Common Files\SSL\cert.pem"
    if (-not (Test-Path $defaultSsl)) {
        try {
            $certifi = python -c "import certifi; print(certifi.where())" 2>$null
            if ($certifi) { $env:SSL_CERT_FILE = $certifi.Trim() }
        } catch { }
    }
}

$argsList = @("-m", "scripts.cron_task_monitor", "--run-scheduled")
if ($Json) { $argsList += "--json" }
if ($NoNotify) { $argsList += "--no-notify" }
if ($DryRun) { $argsList += "--dry-run" }
if ($Force) { $argsList += "--force-scheduled" }
foreach ($j in $Job) {
    if ($j) { $argsList += @("--job", $j) }
}

python @argsList
exit $LASTEXITCODE
