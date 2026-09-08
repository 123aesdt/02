$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

function Stop-DockerTest([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

function Get-MySqlScalar([string]$Query) {
    $rawOutput = @(& $dockerCommand compose --env-file $envFile exec -T mysql mysql -N `
        ("-u{0}" -f $dockerEnv.MYSQL_USER) ("-p{0}" -f $dockerEnv.MYSQL_PASSWORD) `
        -D $dockerEnv.MYSQL_DATABASE -e $Query)
    if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'MySQL query failed。' }

    $values = @($rawOutput | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^\d+$' })
    if ($values.Count -ne 1) { Stop-DockerTest 'MySQL scalar query returned an unexpected result。' }
    return $values[0]
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
if (-not (Test-Path -LiteralPath $envFile)) { Stop-DockerTest '缺少 .docker.env。请先运行 一键启动完整版.bat。' }
try {
    $dockerCommand = Resolve-DockerCommand
} catch {
    Stop-DockerTest $_.Exception.Message
}

$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$previousProfile = $env:RUNTIME_PROFILE
$previousSecret = $env:DEVELOPMENT_JWT_SECRET
$previousIssuer = $env:AUTH_ISSUER
$previousAudience = $env:AUTH_AUDIENCE
try {
    $env:RUNTIME_PROFILE = 'docker-dev'
    $env:DEVELOPMENT_JWT_SECRET = $dockerEnv.DEVELOPMENT_JWT_SECRET
    $env:AUTH_ISSUER = $dockerEnv.AUTH_ISSUER
    $env:AUTH_AUDIENCE = $dockerEnv.AUTH_AUDIENCE
    $dispatcherToken = (& $python (Join-Path $projectRoot 'scripts\create_dev_token.py') --role DISPATCHER).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $dispatcherToken) { Stop-DockerTest 'Unable to create the short-lived Docker test identity.' }
} finally {
    if ($null -eq $previousProfile) { Remove-Item Env:RUNTIME_PROFILE -ErrorAction SilentlyContinue } else { $env:RUNTIME_PROFILE = $previousProfile }
    if ($null -eq $previousSecret) { Remove-Item Env:DEVELOPMENT_JWT_SECRET -ErrorAction SilentlyContinue } else { $env:DEVELOPMENT_JWT_SECRET = $previousSecret }
    if ($null -eq $previousIssuer) { Remove-Item Env:AUTH_ISSUER -ErrorAction SilentlyContinue } else { $env:AUTH_ISSUER = $previousIssuer }
    if ($null -eq $previousAudience) { Remove-Item Env:AUTH_AUDIENCE -ErrorAction SilentlyContinue } else { $env:AUTH_AUDIENCE = $previousAudience }
}
$authorizationHeaders = @{ Authorization = "Bearer $dispatcherToken" }

& $dockerCommand compose --env-file $envFile ps
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Docker Compose services are unavailable。' }

$health = Invoke-RestMethod -Uri 'http://localhost:8001/health' -TimeoutSec 5
if ($health.status -ne 'ok') { Stop-DockerTest 'Backend health is not ok。' }
if ((Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 5).StatusCode -ne 200) { Stop-DockerTest 'Frontend is not reachable。' }

& $dockerCommand compose --env-file $envFile exec -T redis redis-cli PING
& $dockerCommand compose --env-file $envFile exec -T redis redis-cli XADD countyflow:docker:smoke '*' data smoke
& $dockerCommand compose --env-file $envFile exec -T redis redis-cli XGROUP CREATE countyflow:docker:smoke countyflow-docker-smoke 0 MKSTREAM *> $null
& $dockerCommand compose --env-file $envFile exec -T redis redis-cli XREADGROUP GROUP countyflow-docker-smoke verifier COUNT 1 STREAMS countyflow:docker:smoke '>'

$orderId = Get-MySqlScalar "SELECT id FROM orders WHERE order_no='ORDER-E2E-RAIN-001' LIMIT 1;"
$anomalyId = Get-MySqlScalar "SELECT id FROM anomalies WHERE anomaly_no='ANOM-E2E-RAIN-001' LIMIT 1;"
if (-not $orderId -or -not $anomalyId) { Stop-DockerTest 'MySQL E2E seed data is missing。' }

$key = "docker-e2e-$([guid]::NewGuid().ToString('N'))"
$body = @{
    order_id = [int]$orderId
    anomaly_id = [int]$anomalyId
    driver_id = 'driver-li'
    vehicle_id = 'vehicle-001'
    route_id = 'xinping-road'
    anomaly_type = 'rain_slippery'
    anomaly_description = '李师傅在雨天经过新平路，道路出现湿滑风险。'
    idempotency_key = $key
} | ConvertTo-Json
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$acceptedResponse = Invoke-WebRequest -Method Post -Uri 'http://localhost:8001/api/v1/dispatch-tasks' -Headers $authorizationHeaders -ContentType 'application/json; charset=utf-8' -Body $bodyBytes -TimeoutSec 10 -UseBasicParsing
if ($acceptedResponse.StatusCode -ne 202) { Stop-DockerTest 'Dispatch task did not return HTTP 202。' }
$accepted = $acceptedResponse.Content | ConvertFrom-Json
if (-not $accepted.accepted) { Stop-DockerTest 'Dispatch task was not accepted。' }

$status = $null
for ($attempt = 1; $attempt -le 60; $attempt++) {
    $status = Invoke-RestMethod -Uri "http://localhost:8001/api/v1/dispatch-tasks/$($accepted.task_id)" -Headers $authorizationHeaders -TimeoutSec 5
    if ($status.ready) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $status.ready) { Stop-DockerTest 'Worker did not reach a terminal state。' }
$result = Invoke-RestMethod -Uri "http://localhost:8001/api/v1/dispatch-tasks/$($accepted.task_id)/result" -Headers $authorizationHeaders -TimeoutSec 5
if (
    $result.dispatch.target_route_id -ne 'national-102' -or
    $result.dispatch.status -ne 'REROUTED' -or
    $result.dispatch.decision_reason -notmatch 'memory-rain-li' -or
    $result.audit.result -ne 'APPROVED'
) { Stop-DockerTest 'E2E result did not preserve memory-rain-li -> national-102 -> REROUTE -> APPROVED。' }

$dispatchCount = Get-MySqlScalar "SELECT COUNT(*) FROM dispatches d JOIN dispatch_tasks t ON t.id=d.task_id WHERE t.task_id='$($accepted.task_id)';"
$auditCount = Get-MySqlScalar "SELECT COUNT(*) FROM audit_records a JOIN dispatch_tasks t ON t.id=a.task_id WHERE t.task_id='$($accepted.task_id)';"
if ($dispatchCount -ne '1' -or $auditCount -ne '1') { Stop-DockerTest 'MySQL duplicate side-effect check failed。' }

$collections = Invoke-RestMethod -Uri 'http://localhost:6333/collections' -TimeoutSec 5
if ($collections.result.collections.name -notcontains 'entity_resolution_memory') { Stop-DockerTest 'Qdrant entity memory collection is missing。' }
$env:E2E_ACCESS_TOKEN = $dispatcherToken
try {
    & $python (Join-Path $projectRoot 'scripts\docker_ws_e2e.py') --order-id $orderId --anomaly-id $anomalyId
} finally {
    Remove-Item Env:E2E_ACCESS_TOKEN -ErrorAction SilentlyContinue
}
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Docker WebSocket E2E failed。' }
& (Join-Path $projectRoot 'scripts\test-shared-memory.ps1')
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Docker shared-memory E2E failed。' }
$env:PYTHONPATH = Join-Path $projectRoot 'backend'
$env:PROJECT_ROOT = $projectRoot
$env:DOCKER_COMMAND = $dockerCommand
$env:DATABASE_URL = "mysql+pymysql://$($dockerEnv.MYSQL_USER):$($dockerEnv.MYSQL_PASSWORD)@127.0.0.1:3306/$($dockerEnv.MYSQL_DATABASE)"
& (Join-Path $projectRoot 'scripts\test-checkpoint.ps1')
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Docker checkpoint and worker resume E2E failed。' }
& (Join-Path $projectRoot 'scripts\test-runtime-override.ps1')
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Docker runtime override E2E failed。' }
& (Join-Path $projectRoot 'scripts\test-browser-e2e.ps1')
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Docker browser E2E failed。' }
& (Join-Path $projectRoot 'scripts\test-observability.ps1')
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Docker observability E2E failed。' }
$pendingOutput = @(& $dockerCommand compose --env-file $envFile exec -T redis redis-cli XPENDING countyflow:dispatch:tasks countyflow-workers)
if ($LASTEXITCODE -ne 0) { Stop-DockerTest 'Redis pending inspection failed。' }
$pendingValues = @($pendingOutput | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^\d+$' })
if ($pendingValues.Count -lt 1 -or $pendingValues[0] -ne '0') { Stop-DockerTest 'Redis task stream still contains pending messages。' }
& (Join-Path $projectRoot 'scripts\test-offline-fleet-routing.ps1')
if ($LASTEXITCODE -ne 0) { Stop-DockerTest '离线车辆接替与道路绕行双场景验收失败。' }
Write-Host '[OK] Docker Redis/MySQL/Qdrant/Neo4j/eight-agent/worker E2E passed with Pending=0.' -ForegroundColor Green
