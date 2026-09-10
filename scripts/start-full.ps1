param([switch]$PrepareOnly)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

function Stop-FullRuntime([string]$Message) {
    Write-Host "[错误] $Message" -ForegroundColor Red
    exit 1
}

function Test-DockerReady([string]$DockerCommand) {
    try {
        & $DockerCommand info *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Start-DockerDesktop([string]$DockerCommand) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe'),
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Docker\Docker Desktop.exe')
    )
    $dockerDesktop = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $dockerDesktop) {
        Stop-FullRuntime 'Docker Desktop 未运行，并且未找到安装程序。请先安装 Docker Desktop。'
    }

    Write-Host '[准备] Docker Desktop 未运行，正在自动启动……' -ForegroundColor Yellow
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    for ($attempt = 1; $attempt -le 120; $attempt++) {
        if (Test-DockerReady $DockerCommand) {
            Write-Host '[准备] Docker 引擎已就绪。' -ForegroundColor Green
            return
        }
        if ($attempt % 10 -eq 0) {
            Write-Host '[准备] 正在等待 Docker 引擎就绪……' -ForegroundColor Yellow
        }
        Start-Sleep -Seconds 1
    }
    Stop-FullRuntime 'Docker Desktop 启动超时，请检查 Docker Desktop 状态后重试。'
}

function Initialize-BuildImages([string]$DockerCommand) {
    $images = @(
        'python:3.12-slim',
        'node:22-alpine',
        'nginx:1.27-alpine',
        'qdrant/qdrant:v1.13.2',
        'mysql:8.4',
        'redis:8.2.9-alpine',
        'neo4j:5.26-community',
        'prom/prometheus:v3.5.0',
        'grafana/grafana:12.1.0'
    )
    Write-Host '[准备] 正在准备 Docker 基础镜像……' -ForegroundColor Yellow
    $preparer = Join-Path $PSScriptRoot 'ensure-docker-images.ps1'
    try {
        & $preparer -DockerCommand $DockerCommand -Images $images
    } catch {
        Stop-FullRuntime "基础镜像拉取失败：$($_.Exception.Message)"
    }
}

function Wait-Http([string]$Url, [int]$Attempts = 60) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            if ((Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200) {
                return $true
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    return $false
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
try {
    $dockerCommand = Resolve-DockerCommand
} catch {
    Stop-FullRuntime $_.Exception.Message
}
if (-not (Test-DockerReady $dockerCommand)) {
    Start-DockerDesktop $dockerCommand
}
if (-not (Test-Path -LiteralPath $envFile)) {
    @(
        'MYSQL_DATABASE=countyflow',
        'MYSQL_USER=countyflow',
        "MYSQL_PASSWORD=$([guid]::NewGuid().ToString('N'))",
        "MYSQL_ROOT_PASSWORD=$([guid]::NewGuid().ToString('N'))"
        'GRAFANA_PORT=3000'
        'GRAFANA_ADMIN_USER=countyflow-admin'
        "GRAFANA_ADMIN_PASSWORD=$([guid]::NewGuid().ToString('N'))"
        'AUTHENTICATION_PROVIDER=development_jwt'
        "DEVELOPMENT_JWT_SECRET=$([guid]::NewGuid().ToString('N'))$([guid]::NewGuid().ToString('N'))"
        'AUTH_ISSUER=countyflow-dev'
        'AUTH_AUDIENCE=countyflow-api'
        'NEO4J_USER=neo4j'
        "NEO4J_PASSWORD=$([guid]::NewGuid().ToString('N'))"
    ) | Set-Content -LiteralPath $envFile -Encoding utf8
}

$envText = Get-Content -LiteralPath $envFile -Raw
if ($envText -notmatch '(?m)^GRAFANA_ADMIN_USER=') {
    Add-Content -LiteralPath $envFile -Value "`nGRAFANA_PORT=3000`nGRAFANA_ADMIN_USER=countyflow-admin`nGRAFANA_ADMIN_PASSWORD=$([guid]::NewGuid().ToString('N'))" -Encoding utf8
}
if ($envText -notmatch '(?m)^AUTHENTICATION_PROVIDER=') {
    Add-Content -LiteralPath $envFile -Value "`nAUTHENTICATION_PROVIDER=development_jwt" -Encoding utf8
}
if ($envText -notmatch '(?m)^DEVELOPMENT_JWT_SECRET=') {
    Add-Content -LiteralPath $envFile -Value "`nDEVELOPMENT_JWT_SECRET=$([guid]::NewGuid().ToString('N'))$([guid]::NewGuid().ToString('N'))" -Encoding utf8
}
if ($envText -notmatch '(?m)^AUTH_ISSUER=') {
    Add-Content -LiteralPath $envFile -Value "`nAUTH_ISSUER=countyflow-dev" -Encoding utf8
}
if ($envText -notmatch '(?m)^AUTH_AUDIENCE=') {
    Add-Content -LiteralPath $envFile -Value "`nAUTH_AUDIENCE=countyflow-api" -Encoding utf8
}
if ($envText -notmatch '(?m)^NEO4J_USER=') {
    Add-Content -LiteralPath $envFile -Value "`nNEO4J_USER=neo4j" -Encoding utf8
}
if ($envText -notmatch '(?m)^NEO4J_PASSWORD=') {
    Add-Content -LiteralPath $envFile -Value "`nNEO4J_PASSWORD=$([guid]::NewGuid().ToString('N'))" -Encoding utf8
}

if ($PrepareOnly) {
    Write-Host '[成功] 已配置被忽略的 Docker 环境文件；未输出任何密钥值。' -ForegroundColor Green
    exit 0
}

Write-Host '[1/4] 正在构建已验证镜像并启动完整运行环境……' -ForegroundColor Cyan
$builder = Join-Path $PSScriptRoot 'build-full-runtime-images.ps1'
Initialize-BuildImages $dockerCommand
try {
    & $builder -ProjectRoot $projectRoot -DockerCommand $dockerCommand
} catch {
    Stop-FullRuntime "已验证 Docker 镜像构建失败：$($_.Exception.Message)"
}
& $dockerCommand compose --env-file $envFile up -d --no-build
if ($LASTEXITCODE -ne 0) { Stop-FullRuntime 'Docker Compose 启动失败。' }

Write-Host '[2/4] 正在等待后端、前端和监控服务……' -ForegroundColor Cyan
if (-not (Wait-Http 'http://localhost:8001/health')) { Stop-FullRuntime '后端健康检查超时。' }
if (-not (Wait-Http 'http://localhost:5173')) { Stop-FullRuntime '前端就绪检查超时。' }
if (-not (Wait-Http 'http://localhost:3000/api/health')) { Stop-FullRuntime 'Grafana 就绪检查超时。' }

Write-Host '[3/4] 所有服务已就绪。' -ForegroundColor Cyan
Write-Host '[4/4] 正在打开浏览器……' -ForegroundColor Cyan
Start-Process 'http://localhost:5173'
Write-Host ''
Write-Host '===================================='
Write-Host ' CountyFlow AI - 完整运行环境'
Write-Host '===================================='
Write-Host '前端         已就绪'
Write-Host '后端         已就绪'
Write-Host 'Worker-1     已就绪'
Write-Host 'Worker-2     已就绪'
Write-Host 'Redis        已就绪'
Write-Host 'MySQL        已就绪'
Write-Host 'Qdrant       已就绪'
Write-Host 'Prometheus   已就绪'
Write-Host 'Grafana      已就绪'
Write-Host ''
Write-Host '前端：'
Write-Host 'http://localhost:5173'
Write-Host ''
Write-Host '后端：'
Write-Host 'http://localhost:8001'
Write-Host ''
Write-Host 'API 文档：'
Write-Host 'http://localhost:8001/docs'
Write-Host ''
Write-Host 'Grafana:'
Write-Host 'http://localhost:3000'
Write-Host ''
Write-Host '开发认证：'
Write-Host '请在前端右上角选择演示员工；五个角色均为免密演示账号。'
Write-Host 'scripts/create-dev-token.ps1 仅用于明确的角色或安全测试。'
Write-Host '===================================='
