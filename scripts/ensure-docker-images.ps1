param(
    [string]$DockerCommand = 'docker',
    [string[]]$Images = @(
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
)

$ErrorActionPreference = 'Stop'

foreach ($image in $Images) {
    & $DockerCommand image inspect $image *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[准备] 使用本地已有镜像：$image" -ForegroundColor Green
        continue
    }

    Write-Host "[准备] 本地缺少镜像，正在拉取：$image" -ForegroundColor Yellow
    & $DockerCommand pull $image
    if ($LASTEXITCODE -ne 0) {
        throw "基础镜像拉取失败（$image）。请检查网络或代理后重试。"
    }
}

Write-Host '[准备] Docker 基础镜像已就绪。' -ForegroundColor Green
