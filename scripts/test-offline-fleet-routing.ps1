$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

function Stop-Acceptance([string]$Message) {
    Write-Host "[BLOCKED BY ENVIRONMENT] $Message" -ForegroundColor Yellow
    exit 2
}

function Get-MySqlScalar([string]$Query) {
    $output = @(& $dockerCommand compose --env-file $envFile exec -T mysql mysql -N `
        ("-u{0}" -f $dockerEnv.MYSQL_USER) ("-p{0}" -f $dockerEnv.MYSQL_PASSWORD) `
        -D $dockerEnv.MYSQL_DATABASE -e $Query)
    if ($LASTEXITCODE -ne 0) { throw 'MySQL 验收查询失败。' }
    $values = @($output | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^\d+$' })
    if ($values.Count -ne 1) { throw 'MySQL 验收查询未返回唯一数字。' }
    return [int]$values[0]
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
if (-not (Test-Path -LiteralPath $envFile)) { Stop-Acceptance '缺少 .docker.env，无法启动真实依赖验收。' }
try { $dockerCommand = Resolve-DockerCommand } catch { Stop-Acceptance $_.Exception.Message }
& $dockerCommand version --format '{{.Server.Version}}' *> $null
if ($LASTEXITCODE -ne 0) { Stop-Acceptance 'Docker daemon 不可用，未执行真实 API/MySQL/Redis 验收。' }
& $dockerCommand compose --env-file $envFile ps *> $null
if ($LASTEXITCODE -ne 0) { Stop-Acceptance 'Docker Compose 服务不可用。' }

$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$previousProfile = $env:RUNTIME_PROFILE
$previousToken = $env:E2E_ACCESS_TOKEN
$previousSecret = $env:DEVELOPMENT_JWT_SECRET
$previousIssuer = $env:AUTH_ISSUER
$previousAudience = $env:AUTH_AUDIENCE
$resultPath = Join-Path ([System.IO.Path]::GetTempPath()) ("countyflow-task9-{0}.json" -f [guid]::NewGuid().ToString('N'))
try {
    $env:RUNTIME_PROFILE = 'docker-dev'
    $env:DEVELOPMENT_JWT_SECRET = $dockerEnv.DEVELOPMENT_JWT_SECRET
    $env:AUTH_ISSUER = $dockerEnv.AUTH_ISSUER
    $env:AUTH_AUDIENCE = $dockerEnv.AUTH_AUDIENCE
    $env:E2E_ACCESS_TOKEN = (& $python (Join-Path $projectRoot 'scripts\create_dev_token.py') --role DISPATCHER).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $env:E2E_ACCESS_TOKEN) { throw '无法创建短期验收身份。' }
    & $python (Join-Path $projectRoot 'scripts\offline_fleet_routing_acceptance.py') --base-url 'http://localhost:8001' --output $resultPath
    if ($LASTEXITCODE -ne 0) { throw '公开 API 双场景验收失败。' }
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    foreach ($taskId in @($result.breakdown.task_id, $result.road_blocked.task_id)) {
        $dispatchCount = Get-MySqlScalar "SELECT COUNT(*) FROM dispatches d JOIN dispatch_tasks t ON t.id=d.task_id WHERE t.task_id='$taskId';"
        $evidenceCount = Get-MySqlScalar "SELECT COUNT(*) FROM dispatch_evidence e JOIN dispatches d ON d.id=e.dispatch_id JOIN dispatch_tasks t ON t.id=d.task_id WHERE t.task_id='$taskId';"
        if ($dispatchCount -ne 1 -or $evidenceCount -ne 2) { throw "任务 $taskId 的 dispatch/evidence 数量不是 1/2。" }
    }
    $reserved = Get-MySqlScalar "SELECT COUNT(*) FROM fleet_vehicles WHERE vehicle_id='V-005' AND status='RESERVED';"
    $selected = Get-MySqlScalar "SELECT COUNT(*) FROM dispatches d JOIN dispatch_tasks t ON t.id=d.task_id WHERE t.task_id='$($result.breakdown.task_id)' AND d.target_vehicle_id='V-005';"
    if ($reserved -ne 1 -or $selected -ne 1) { throw 'V-005 未形成唯一预留与唯一入选调度。' }
    $pendingOutput = @(& $dockerCommand compose --env-file $envFile exec -T redis redis-cli XPENDING countyflow:dispatch:tasks countyflow-workers)
    if ($LASTEXITCODE -ne 0) { throw 'Redis XPENDING 查询失败。' }
    $pending = @($pendingOutput | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^\d+$' })
    if ($pending.Count -lt 1 -or [int]$pending[0] -ne 0) { throw 'Redis 任务流仍有未确认消息。' }
    Write-Host '[OK] 公开 API 双场景、MySQL 1/2 证据、V-005 唯一预留与 Redis Pending=0 均通过。' -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $resultPath) { Remove-Item -LiteralPath $resultPath -Force }
    if ($null -eq $previousProfile) { Remove-Item Env:RUNTIME_PROFILE -ErrorAction SilentlyContinue } else { $env:RUNTIME_PROFILE = $previousProfile }
    if ($null -eq $previousToken) { Remove-Item Env:E2E_ACCESS_TOKEN -ErrorAction SilentlyContinue } else { $env:E2E_ACCESS_TOKEN = $previousToken }
    if ($null -eq $previousSecret) { Remove-Item Env:DEVELOPMENT_JWT_SECRET -ErrorAction SilentlyContinue } else { $env:DEVELOPMENT_JWT_SECRET = $previousSecret }
    if ($null -eq $previousIssuer) { Remove-Item Env:AUTH_ISSUER -ErrorAction SilentlyContinue } else { $env:AUTH_ISSUER = $previousIssuer }
    if ($null -eq $previousAudience) { Remove-Item Env:AUTH_AUDIENCE -ErrorAction SilentlyContinue } else { $env:AUTH_AUDIENCE = $previousAudience }
}
