$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$rawDirectory = Join-Path $projectRoot 'docs\verification\v2-g2\raw'
$statsPrefix = Join-Path $rawDirectory 'security-on'
$statsFile = Join-Path $rawDirectory 'security-on_stats.csv'
$baseline = Join-Path $projectRoot 'docs\verification\raw\locust-results.json'
$output = Join-Path $rawDirectory 'v2-g2-security-performance.json'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw 'Missing ignored .docker.env.' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project .venv Python is unavailable.' }
if (-not (Test-Path -LiteralPath $baseline -PathType Leaf)) { throw 'Verified pre-V2-G2 load baseline is unavailable.' }
$dockerCommand = Resolve-DockerCommand
$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}

$services = @(& $dockerCommand compose --env-file $envFile config --services)
if ($LASTEXITCODE -ne 0 -or $services.Count -ne 11) { throw 'The eleven-service Docker topology is required.' }
$running = @(& $dockerCommand compose --env-file $envFile ps --services --status running)
foreach ($required in @('mysql', 'redis', 'qdrant', 'neo4j', 'backend', 'worker-1', 'worker-2')) {
    if ($required -notin $running) { throw "Required Docker service is not running: $required" }
}
if ((Invoke-WebRequest -Uri 'http://localhost:8001/health' -UseBasicParsing -TimeoutSec 5).StatusCode -ne 200) {
    throw 'Backend health check failed.'
}

$taskQuery = "SELECT task_id FROM dispatch_tasks WHERE status IN ('COMPLETED','REVIEW_REQUIRED') ORDER BY id DESC LIMIT 1;"
$taskOutput = @(& $dockerCommand compose --env-file $envFile exec -T mysql mysql -N `
    ("-u{0}" -f $dockerEnv.MYSQL_USER) ("-p{0}" -f $dockerEnv.MYSQL_PASSWORD) `
    -D $dockerEnv.MYSQL_DATABASE -e $taskQuery)
if ($LASTEXITCODE -ne 0) { throw 'Could not locate a terminal load-test task.' }
$taskIds = @($taskOutput | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^TASK-[A-Za-z0-9-]+$' })
if ($taskIds.Count -ne 1) { throw 'A single terminal load-test task is required.' }

$environmentNames = @('PYTHONPATH', 'LOCUST_TASK_ID', 'RUNTIME_PROFILE', 'DEVELOPMENT_JWT_SECRET', 'AUTH_ISSUER', 'AUTH_AUDIENCE')
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
    $env:PYTHONPATH = Join-Path $projectRoot 'backend'
    $env:LOCUST_TASK_ID = $taskIds[0]
    $env:RUNTIME_PROFILE = 'docker-dev'
    $env:DEVELOPMENT_JWT_SECRET = $dockerEnv.DEVELOPMENT_JWT_SECRET
    $env:AUTH_ISSUER = $dockerEnv.AUTH_ISSUER
    $env:AUTH_AUDIENCE = $dockerEnv.AUTH_AUDIENCE
    if (-not (Test-Path -LiteralPath $rawDirectory)) { New-Item -ItemType Directory -Path $rawDirectory | Out-Null }
    Push-Location $projectRoot
    try {
        & $python -m locust -f 'loadtests\locustfile.py' --host 'http://localhost:8001' --headless `
            --users 50 --spawn-rate 25 --run-time 60s --stop-timeout 10 --only-summary --csv $statsPrefix
        if ($LASTEXITCODE -ne 0) { throw 'Authenticated security-ON Locust run failed.' }
    } finally { Pop-Location }
    & $python (Join-Path $PSScriptRoot 'summarize_security_performance.py') `
        --stats $statsFile --baseline $baseline --output $output
    if ($LASTEXITCODE -ne 0) { throw 'Security performance gates failed.' }
} finally {
    foreach ($name in $environmentNames) {
        $value = $previousEnvironment[$name]
        if ($null -eq $value) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue } else { Set-Item "Env:$name" $value }
    }
}

Write-Host '[OK] Authenticated security-ON performance gates passed; current authentication and rate limiting remained enabled.' -ForegroundColor Green
