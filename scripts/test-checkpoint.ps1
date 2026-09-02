$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $workspaceRoot '.docker.env'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw '.docker.env is required for the real checkpoint integration test.'
}

$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>[^=]+)=(?<value>.*)$') { $dockerEnv[$Matches.key] = $Matches.value }
}
foreach ($required in @('MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE', 'DEVELOPMENT_JWT_SECRET', 'AUTH_ISSUER', 'AUTH_AUDIENCE')) {
    if ([string]::IsNullOrWhiteSpace($dockerEnv[$required])) { throw "$required is required in the ignored Docker environment." }
}

$environmentNames = @(
    'PYTHONPATH', 'PROJECT_ROOT', 'DOCKER_COMMAND', 'DATABASE_URL', 'RUNTIME_PROFILE',
    'DEVELOPMENT_JWT_SECRET', 'AUTH_ISSUER', 'AUTH_AUDIENCE', 'E2E_ACCESS_TOKEN'
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name) }

try {
    $env:PYTHONPATH = Join-Path $workspaceRoot 'backend'
    $env:PROJECT_ROOT = $workspaceRoot
    $env:DOCKER_COMMAND = Resolve-DockerCommand
    $env:DATABASE_URL = "mysql+pymysql://$($dockerEnv.MYSQL_USER):$($dockerEnv.MYSQL_PASSWORD)@127.0.0.1:3306/$($dockerEnv.MYSQL_DATABASE)"
    $env:RUNTIME_PROFILE = 'docker-dev'
    $env:DEVELOPMENT_JWT_SECRET = $dockerEnv.DEVELOPMENT_JWT_SECRET
    $env:AUTH_ISSUER = $dockerEnv.AUTH_ISSUER
    $env:AUTH_AUDIENCE = $dockerEnv.AUTH_AUDIENCE
    $token = (& $python (Join-Path $PSScriptRoot 'create_dev_token.py') --role DISPATCHER).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        throw 'Unable to create the short-lived checkpoint test identity.'
    }
    $env:E2E_ACCESS_TOKEN = $token

    & $python (Join-Path $PSScriptRoot 'checkpoint_integration.py') `
        --redis-url 'redis://127.0.0.1:6380/0' `
        --output (Join-Path $workspaceRoot 'docs\verification\raw\v2-c-checkpoint-performance.json')
    if ($LASTEXITCODE -ne 0) { throw 'Checkpoint Redis integration failed.' }

    & $python (Join-Path $PSScriptRoot 'docker_checkpoint_recovery_e2e.py') `
        --runs 3 `
        --output (Join-Path $workspaceRoot 'docs\verification\raw\v2-c-checkpoint-recovery.json')
    if ($LASTEXITCODE -ne 0) { throw 'Docker checkpoint recovery E2E failed.' }
}
finally {
    foreach ($name in $environmentNames) {
        $value = $previousEnvironment[$name]
        if ($null -eq $value) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue } else { Set-Item "Env:$name" $value }
    }
}
