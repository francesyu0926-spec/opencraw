# 单独打包 config/elk.env、health.env、wecom.env（勿提交 Git、勿与程序包混发）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\pack_secrets.ps1

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$names = @("elk.env", "health.env", "wecom.env")
$configDir = Join-Path $RepoRoot "config"
$missing = @()

foreach ($n in $names) {
    if (-not (Test-Path (Join-Path $configDir $n))) { $missing += $n }
}
if ($missing.Count -gt 0) {
    Write-Error "缺少 config 下文件: $($missing -join ', ')。请先复制 *.env.example 并填写后再打包。"
}

$dateTag = Get-Date -Format "yyyyMMdd"
$bundleName = "opencraw-secrets-config-$dateTag"
$distDir = Join-Path $RepoRoot "dist"
$zipPath = Join-Path $distDir "$bundleName.zip"
$staging = Join-Path $env:TEMP $bundleName
$configStaging = Join-Path $staging "config"

if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $configStaging -Force | Out-Null

foreach ($n in $names) {
    Copy-Item (Join-Path $configDir $n) (Join-Path $configStaging $n)
}

@"
# 密钥配置包 — 解压说明

1. 解压到 opencraw 部署目录，使路径为：<部署根>/config/elk.env 等（覆盖或合并现有 config）。
2. 勿将此 zip 上传 Git、公网盘或与 opencraw-monitor-deploy-*.zip 混在同一公开渠道。
3. 解压后建议：chmod 600 config/*.env（Linux）；限制 Windows ACL 仅运维可读。
4. health 登录 Token 缓存仍由程序生成：config/health.token.cache.json（不在本包内）。

"@ | Set-Content -Path (Join-Path $staging "密钥解压说明.txt") -Encoding UTF8

if (-not (Test-Path $distDir)) { New-Item -ItemType Directory -Path $distDir | Out-Null }
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item $staging -Recurse -Force

Write-Host "OK: $zipPath"
Write-Host "WARN: 压缩包含明文密钥，请加密通道传输并限制访问。"
Get-Item $zipPath | Select-Object FullName, Length, LastWriteTime
