$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

function Stop-ObservabilityTest([string]$Message) {
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$rawDirectory = Join-Path $projectRoot 'docs\verification\v2-g1\raw'
if (-not (Test-Path -LiteralPath $envFile)) { Stop-ObservabilityTest 'Missing ignored .docker.env.' }
if (-not (Test-Path -LiteralPath $python)) { Stop-ObservabilityTest 'Missing project .venv.' }
try { $dockerCommand = Resolve-DockerCommand } catch { Stop-ObservabilityTest $_.Exception.Message }

$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}
foreach ($required in @(
    'GRAFANA_ADMIN_USER', 'GRAFANA_ADMIN_PASSWORD', 'DEVELOPMENT_JWT_SECRET', 'AUTH_ISSUER', 'AUTH_AUDIENCE'
)) {
    if (-not $dockerEnv[$required]) { Stop-ObservabilityTest "$required is not configured." }
}

$environmentNames = @(
    'DOCKER_COMMAND', 'COMPOSE_ENV_FILE', 'GRAFANA_ADMIN_USER', 'GRAFANA_ADMIN_PASSWORD', 'GRAFANA_PORT',
    'RUNTIME_PROFILE', 'DEVELOPMENT_JWT_SECRET', 'AUTH_ISSUER', 'AUTH_AUDIENCE', 'E2E_ACCESS_TOKEN'
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name) }

try {
    $env:DOCKER_COMMAND = $dockerCommand
    $env:COMPOSE_ENV_FILE = $envFile
    $env:GRAFANA_ADMIN_USER = $dockerEnv.GRAFANA_ADMIN_USER
    $env:GRAFANA_ADMIN_PASSWORD = $dockerEnv.GRAFANA_ADMIN_PASSWORD
    $env:GRAFANA_PORT = if ($dockerEnv.GRAFANA_PORT) { $dockerEnv.GRAFANA_PORT } else { '3000' }
    $env:RUNTIME_PROFILE = 'docker-dev'
    $env:DEVELOPMENT_JWT_SECRET = $dockerEnv.DEVELOPMENT_JWT_SECRET
    $env:AUTH_ISSUER = $dockerEnv.AUTH_ISSUER
    $env:AUTH_AUDIENCE = $dockerEnv.AUTH_AUDIENCE
    $token = (& $python (Join-Path $PSScriptRoot 'create_dev_token.py') --role SUPERVISOR).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        Stop-ObservabilityTest 'Unable to create the short-lived observability test identity.'
    }
    $env:E2E_ACCESS_TOKEN = $token
    New-Item -ItemType Directory -Force -Path $rawDirectory | Out-Null

& $dockerCommand compose --env-file $envFile config --quiet
if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Compose validation failed.' }
& $dockerCommand compose --env-file $envFile exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Prometheus config validation failed.' }
& $dockerCommand compose --env-file $envFile exec -T prometheus promtool check rules /etc/prometheus/rules/countyflow-recording.yml /etc/prometheus/rules/countyflow-alerts.yml
if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Prometheus rules validation failed.' }

& $python (Join-Path $PSScriptRoot 'observability_integration.py') --output (Join-Path $rawDirectory 'prometheus-targets.json')
if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Prometheus/Grafana integration failed.' }
& $python (Join-Path $PSScriptRoot 'observability_failure_e2e.py') --output (Join-Path $rawDirectory 'failure-e2e.json')
if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Failure isolation E2E failed.' }
& $python (Join-Path $PSScriptRoot 'observability_alert_e2e.py') --output (Join-Path $rawDirectory 'alert-e2e.json')
if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Alert lifecycle E2E failed.' }
& $python (Join-Path $PSScriptRoot 'observability_overhead.py') --output (Join-Path $rawDirectory 'overhead.json')
if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Observability overhead benchmark failed.' }

$env:E2E_JSON_REPORT = Join-Path $rawDirectory 'browser-e2e.json'
Push-Location (Join-Path $projectRoot 'frontend')
try {
    & npx playwright test e2e/observability-live.spec.ts e2e/observability-failures.spec.ts
    if ($LASTEXITCODE -ne 0) { Stop-ObservabilityTest 'Observability browser E2E failed.' }
} finally { Pop-Location }

    Write-Host '[OK] V2-G1 real observability acceptance passed.' -ForegroundColor Green
}
finally {
    foreach ($name in $environmentNames) {
        $value = $previousEnvironment[$name]
        if ($null -eq $value) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue } else { Set-Item "Env:$name" $value }
    }
}
