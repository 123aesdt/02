param(
    [int]$LocustUsers = 50,
    [int]$LocustSpawnRate = 25,
    [string]$LocustDuration = '60s'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
$rawDirectory = Join-Path $projectRoot 'docs\verification\raw'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$ruff = Join-Path $projectRoot '.venv\Scripts\ruff.exe'

function Stop-Acceptance([string]$Name, [int]$Code = 1) {
    Write-Host "[FAILED] $Name (exit $Code)" -ForegroundColor Red
    exit $Code
}

function Invoke-Checked([string]$Name, [scriptblock]$Action) {
    Write-Host "[ACCEPTANCE] $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { Stop-Acceptance $Name $LASTEXITCODE }
}

if (-not (Test-Path -LiteralPath $envFile)) { Stop-Acceptance 'Missing .docker.env' }
if (-not (Test-Path -LiteralPath $python)) { Stop-Acceptance 'Missing project Python environment' }
$dockerCommand = Resolve-DockerCommand
$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^#=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}

$env:PYTHONPATH = Join-Path $projectRoot 'backend'
$env:DOCKER_COMMAND = $dockerCommand
$env:PROJECT_ROOT = $projectRoot
$env:DATABASE_URL = "mysql+pymysql://$($dockerEnv.MYSQL_USER):$($dockerEnv.MYSQL_PASSWORD)@localhost:3306/$($dockerEnv.MYSQL_DATABASE)"
New-Item -ItemType Directory -Force -Path $rawDirectory | Out-Null

Push-Location $projectRoot
try {
    Invoke-Checked 'Docker readiness and functional E2E' { & (Join-Path $PSScriptRoot 'test-docker.ps1') }
    Invoke-Checked 'Worker recovery: 5 real kill trials' {
        & $python scripts\docker_worker_recovery_e2e.py --runs 5 --output docs\verification\raw\worker-recovery-results.json
    }
    Invoke-Checked 'Redis reliability' {
        & $python scripts\docker_redis_acceptance.py --recovery-results docs\verification\raw\worker-recovery-results.json --output docs\verification\raw\redis-reliability-results.json
    }
    Invoke-Checked 'Fallback: 10 real timeout trials' {
        & $python scripts\docker_fallback_acceptance.py --runs 10 --output docs\verification\raw\fallback-results.json
    }
    Invoke-Checked 'MySQL concurrency: 20 conflict trials' {
        & $python scripts\docker_concurrency_acceptance.py --runs 20 --output docs\verification\raw\concurrency-results.json
    }
    Invoke-Checked 'Memory benchmark and adoption' {
        & $python scripts\run_memory_benchmark.py --output docs\verification\raw\memory-benchmark-results.json
    }

    $loadSeedBody = @{
        order_id = 1
        anomaly_id = 1
        driver_id = 'driver-li'
        vehicle_id = 'vehicle-001'
        route_id = 'xinping-road'
        anomaly_type = 'rain_slippery'
        anomaly_description = 'Phase 5B Locust query seed'
        idempotency_key = "phase5b-locust-seed-$([guid]::NewGuid().ToString('N'))"
    } | ConvertTo-Json
    $loadSeed = Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/api/v1/dispatch-tasks' `
        -ContentType 'application/json' -Body $loadSeedBody -TimeoutSec 10
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $loadSeedStatus = Invoke-RestMethod -Uri "http://localhost:8001/api/v1/dispatch-tasks/$($loadSeed.task_id)" -TimeoutSec 5
        if ($loadSeedStatus.ready) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $loadSeedStatus.ready) { Stop-Acceptance 'Locust seed task did not become terminal' }
    $env:LOCUST_TASK_ID = $loadSeed.task_id
    for ($run = 1; $run -le 3; $run++) {
        Invoke-Checked "Locust formal run $run" {
            & $python -m locust -f loadtests\locustfile.py --host http://localhost:8001 --headless `
                -u $LocustUsers -r $LocustSpawnRate -t $LocustDuration --only-summary `
                --csv "docs\verification\raw\locust-run-$run" --html "docs\verification\raw\locust-run-$run.html"
        }
    }
    Invoke-Checked 'Locust result validation' {
        & $python scripts\summarize_locust_results.py --output docs\verification\raw\locust-results.json
    }
    Invoke-Checked 'Business workload' {
        & $python scripts\docker_business_acceptance.py --output docs\verification\raw\business-acceptance-results.json
    }
    Invoke-Checked 'Acceptance script Ruff' {
        & $ruff check scripts backend
    }
} finally {
    Pop-Location
}

Write-Host '[OK] Phase 5B executable acceptance sequence passed; inspect memory credential_status for formal embedding status.' -ForegroundColor Green
exit 0
