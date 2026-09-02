$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw 'Missing .docker.env.' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project .venv Python is unavailable.' }
$dockerCommand = Resolve-DockerCommand
$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}

function Invoke-Compose([string[]]$Arguments) {
    & $dockerCommand compose --env-file $envFile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed: $($Arguments -join ' ')" }
}

function Get-MySqlId([string]$Query) {
    $output = & $dockerCommand compose --env-file $envFile exec -T mysql mysql -N `
        ("-u{0}" -f $dockerEnv.MYSQL_USER) ("-p{0}" -f $dockerEnv.MYSQL_PASSWORD) `
        -D $dockerEnv.MYSQL_DATABASE -e $Query
    if ($LASTEXITCODE -ne 0) { throw 'MySQL seed lookup failed.' }
    $ids = @($output | Where-Object { $_ -match '^\d+$' })
    if ($ids.Count -ne 1) { throw 'MySQL seed lookup returned an unexpected result.' }
    return $ids[0]
}

$services = @(& $dockerCommand compose --env-file $envFile config --services)
if ($LASTEXITCODE -ne 0 -or $services.Count -ne 11) { throw 'The eleven-service Docker topology is required.' }
$runningServices = @(& $dockerCommand compose --env-file $envFile ps --services --status running)
foreach ($required in @('mysql', 'redis', 'qdrant', 'neo4j', 'backend', 'worker-1', 'worker-2', 'prometheus', 'grafana')) {
    if ($required -notin $runningServices) { throw "Required Docker service is not running: $required" }
}
$migrationState = @(& $dockerCommand compose --env-file $envFile ps -a --format json migration) -join '' | ConvertFrom-Json
if ($migrationState.ExitCode -ne 0) { throw 'Migration service did not complete successfully.' }
if ((Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 5).StatusCode -ne 200) {
    throw 'The existing frontend is not reachable.'
}

$environmentNames = @(
    'RUNTIME_PROFILE', 'DEVELOPMENT_JWT_SECRET', 'AUTH_ISSUER', 'AUTH_AUDIENCE', 'E2E_ACCESS_TOKEN',
    'E2E_ORDER_ID', 'E2E_ANOMALY_ID', 'E2E_PROJECT_ROOT', 'E2E_ENV_FILE', 'E2E_API_BASE_URL',
    'E2E_WEB_BASE_URL', 'DOCKER_COMMAND', 'E2E_PYTHON', 'E2E_DATABASE_URL', 'MYSQL_PASSWORD',
    'NEO4J_PASSWORD', 'E2E_JSON_REPORT'
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name) }

try {
    $env:RUNTIME_PROFILE = 'docker-dev'
    $env:DEVELOPMENT_JWT_SECRET = $dockerEnv.DEVELOPMENT_JWT_SECRET
    $env:AUTH_ISSUER = $dockerEnv.AUTH_ISSUER
    $env:AUTH_AUDIENCE = $dockerEnv.AUTH_AUDIENCE
    $supervisorToken = (& $python (Join-Path $projectRoot 'scripts\create_dev_token.py') --role SUPERVISOR --ttl-seconds 900).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $supervisorToken) { throw 'Could not create a short-lived Supervisor browser identity.' }

    $env:E2E_ACCESS_TOKEN = $supervisorToken
    $env:E2E_ORDER_ID = Get-MySqlId "SELECT id FROM orders WHERE order_no='ORDER-E2E-RAIN-001' LIMIT 1;"
    $env:E2E_ANOMALY_ID = Get-MySqlId "SELECT id FROM anomalies WHERE anomaly_no='ANOM-E2E-RAIN-001' LIMIT 1;"
    $env:E2E_PROJECT_ROOT = $projectRoot
    $env:E2E_ENV_FILE = $envFile
    $env:E2E_API_BASE_URL = 'http://localhost:8001'
    $env:E2E_WEB_BASE_URL = 'http://localhost:5173'
    $env:DOCKER_COMMAND = $dockerCommand
    $env:E2E_PYTHON = $python
    $env:E2E_DATABASE_URL = "mysql+pymysql://$($dockerEnv.MYSQL_USER):$($dockerEnv.MYSQL_PASSWORD)@127.0.0.1:3306/$($dockerEnv.MYSQL_DATABASE)"
    $env:MYSQL_PASSWORD = $dockerEnv.MYSQL_PASSWORD
    $env:NEO4J_PASSWORD = $dockerEnv.NEO4J_PASSWORD
    $env:E2E_JSON_REPORT = Join-Path $projectRoot 'docs\verification\v2-g2\raw\browser-authenticated-regression.json'

    $reportDirectory = Split-Path -Parent $env:E2E_JSON_REPORT
    if (-not (Test-Path -LiteralPath $reportDirectory)) { New-Item -ItemType Directory -Path $reportDirectory | Out-Null }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & npm exec playwright test -- `
            v2e-normal-routing.spec.ts `
            v2e-memory-reconcile.spec.ts `
            runtime-override-success.spec.ts `
            runtime-override-stale.spec.ts `
            runtime-override-concurrent.spec.ts `
            runtime-override-terminal.spec.ts `
            runtime-override-forbidden.spec.ts
        if ($LASTEXITCODE -ne 0) { throw 'Authenticated browser regression scenarios failed.' }
    } finally { Pop-Location }
} finally {
    try { & $dockerCommand unpause countyflow-ai-worker-1-1 *> $null } catch {}
    try { & $dockerCommand start countyflow-ai-worker-2-1 *> $null } catch {}
    try { & $dockerCommand unpause countyflow-ai-qdrant-1 *> $null } catch {}
    try { & $dockerCommand start countyflow-ai-qdrant-1 *> $null } catch {}
    foreach ($name in $environmentNames) {
        $value = $previousEnvironment[$name]
        if ($null -eq $value) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue } else { Set-Item "Env:$name" $value }
    }
}

$pending = @(& $dockerCommand compose --env-file $envFile exec -T redis redis-cli XPENDING countyflow:dispatch:tasks countyflow-workers)
if ($LASTEXITCODE -ne 0 -or @($pending | Where-Object { $_ -match '^\d+$' })[0] -ne '0') {
    throw 'Redis Pending is not zero.'
}
Write-Host '[OK] Seven authenticated real browser scenarios passed; eleven-service topology preserved; Pending=0.' -ForegroundColor Green
