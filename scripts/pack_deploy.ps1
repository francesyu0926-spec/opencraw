# 打部署压缩包（不含密钥、缓存、Git、测试）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\pack_deploy.ps1

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$dateTag = Get-Date -Format "yyyyMMdd"
$bundleName = "opencraw-monitor-deploy-$dateTag"
$distDir = Join-Path $RepoRoot "dist"
$zipPath = Join-Path $distDir "$bundleName.zip"
$staging = Join-Path $env:TEMP $bundleName

if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging | Out-Null
New-Item -ItemType Directory -Path (Join-Path $staging "config") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $staging "docs") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $staging "scripts") -Force | Out-Null

function Copy-IfExists {
    param([string]$From, [string]$To)
    if (Test-Path $From) { Copy-Item $From $To -Force }
}

# 根目录
foreach ($f in @(
    "README.md",
    "requirements-monitor.txt",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore"
)) {
    Copy-IfExists (Join-Path $RepoRoot $f) (Join-Path $staging $f)
}

# 文档
foreach ($f in @("DEPLOY.md", "cron_task_monitor.md", "MIGRATION.md")) {
    Copy-IfExists (Join-Path $RepoRoot "docs\$f") (Join-Path $staging "docs\$f")
}

# 配置（仅 YAML / example / cron 示例）
$configRoot = Join-Path $RepoRoot "config"
$configDest = Join-Path $staging "config"
Get-ChildItem $configRoot -File | Where-Object {
    $_.Extension -in @(".yaml", ".yml", ".example", ".cron") -or $_.Name -eq "schedule.example.cron"
} | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $configDest $_.Name)
}

# scripts：入口脚本 + cron_task_monitor 源码（无 __pycache__）
$scriptNames = @(
    "run_scheduled_monitors.ps1",
    "run_scheduled_monitors.sh",
    "run_monitor_production.ps1",
    "run_monitor_production.sh",
    "run_health_monitor.ps1",
    "run_monitor_scheduled.ps1",
    "__init__.py"
)
foreach ($s in $scriptNames) {
    Copy-IfExists (Join-Path $RepoRoot "scripts\$s") (Join-Path $staging "scripts\$s")
}

$pkgDest = Join-Path $staging "scripts\cron_task_monitor"
New-Item -ItemType Directory -Path $pkgDest -Force | Out-Null
Get-ChildItem (Join-Path $RepoRoot "scripts\cron_task_monitor") -Filter "*.py" | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $pkgDest $_.Name)
}

# 根目录放置操作说明快捷入口
Copy-Item (Join-Path $staging "docs\DEPLOY.md") (Join-Path $staging "部署操作说明.md")

if (-not (Test-Path $distDir)) { New-Item -ItemType Directory -Path $distDir | Out-Null }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -CompressionLevel Optimal

Remove-Item $staging -Recurse -Force

Write-Host "OK: $zipPath"
Get-Item $zipPath | Select-Object FullName, Length, LastWriteTime
