$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw 'Missing .docker.env.' }
$dockerCommand = Resolve-DockerCommand
$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}

function Get-MySqlId([string]$Query) {
    $output = & $dockerCommand compose --env-file $envFile exec -T mysql mysql -N `
        ("-u{0}" -f $dockerEnv.MYSQL_USER) ("-p{0}" -f $dockerEnv.MYSQL_PASSWORD) `
        -D $dockerEnv.MYSQL_DATABASE -e $Query
    if ($LASTEXITCODE -ne 0) { throw 'MySQL seed lookup failed.' }
    return @($output | Where-Object { $_ -match '^\d+$' })[0]
}

$services = @(& $dockerCommand compose --env-file $envFile config --services)
if ($LASTEXITCODE -ne 0 -or $services.Count -ne 11) { throw 'The eleven-service Docker topology is required.' }
$runningServices = @(& $dockerCommand compose --env-file $envFile ps --services --status running)
if ($LASTEXITCODE -ne 0 -or $runningServices.Count -ne 10) { throw 'Ten long-running services must be running; migration is one-shot.' }
$migrationState = @(& $dockerCommand compose --env-file $envFile ps -a --format json migration) -join '' | ConvertFrom-Json
if ($migrationState.ExitCode -ne 0) { throw 'Migration service did not complete successfully.' }

$env:E2E_ORDER_ID = Get-MySqlId "SELECT id FROM orders WHERE order_no='ORDER-E2E-RAIN-001' LIMIT 1;"
$env:E2E_ANOMALY_ID = Get-MySqlId "SELECT id FROM anomalies WHERE anomaly_no='ANOM-E2E-RAIN-001' LIMIT 1;"
$env:E2E_PROJECT_ROOT = $projectRoot
$env:E2E_ENV_FILE = $envFile
$env:E2E_API_BASE_URL = 'http://localhost:8001'
$env:E2E_WEB_BASE_URL = 'http://localhost:5173'
$env:DOCKER_COMMAND = $dockerCommand
$env:E2E_JSON_REPORT = Join-Path $projectRoot 'docs\verification\v2-f\raw\browser-e2e.json'

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $env:E2E_JSON_REPORT) | Out-Null
Push-Location (Join-Path $projectRoot 'frontend')
try {
    & npm exec playwright test -- v2f-productization.spec.ts
    if ($LASTEXITCODE -ne 0) { throw 'V2-F productization browser flow failed.' }
} finally {
    Pop-Location
    try { & $dockerCommand compose --env-file $envFile unpause worker-1 2>$null | Out-Null } catch {}
    try { & $dockerCommand compose --env-file $envFile start worker-2 2>$null | Out-Null } catch {}
}

Write-Host '[OK] V2-F real productization browser flow passed; 12 screenshots created.' -ForegroundColor Green
