# 打部署压缩包（不含密钥、缓存、Git；含 tests 与 automated_writing）
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
foreach ($f in @(
        "DEPLOY.md",
        "cron_task_monitor.md",
        "MIGRATION.md",
        "opencraw-monitor-schedule.pdf"
    )) {
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
    "register_monitor_scheduled_task.ps1",
    "server_diagnose.sh",
    "export_schedule_pdf.py",
    "query_elk_task_logs.py",
    "run_dispatcher_loop.sh",
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

# automated_writing（writing job 依赖）
$awSrc = Join-Path $RepoRoot "scripts\automated_writing"
$awDest = Join-Path $staging "scripts\automated_writing"
if (Test-Path $awSrc) {
    New-Item -ItemType Directory -Path $awDest -Force | Out-Null
    Copy-IfExists (Join-Path $awSrc "verify.py") (Join-Path $awDest "verify.py")
    Copy-IfExists (Join-Path $awSrc "README.md") (Join-Path $awDest "README.md")
    $verifySrc = Join-Path $awSrc "verify"
    $verifyDest = Join-Path $awDest "verify"
    if (Test-Path $verifySrc) {
        Copy-Item $verifySrc $verifyDest -Recurse -Force
        Get-ChildItem $verifyDest -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
    }
}

# tests（部署机可跑 pytest 做冒烟）
$testsSrc = Join-Path $RepoRoot "tests"
$testsDest = Join-Path $staging "tests"
if (Test-Path $testsSrc) {
    New-Item -ItemType Directory -Path $testsDest -Force | Out-Null
    Get-ChildItem $testsSrc -Filter "*.py" | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $testsDest $_.Name)
    }
}

# 根目录放置操作说明快捷入口
Copy-Item (Join-Path $staging "docs\DEPLOY.md") (Join-Path $staging "部署操作说明.md")

if (-not (Test-Path $distDir)) { New-Item -ItemType Directory -Path $distDir | Out-Null }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -CompressionLevel Optimal

Remove-Item $staging -Recurse -Force

Write-Host "OK: $zipPath"
Get-Item $zipPath | Select-Object FullName, Length, LastWriteTime
