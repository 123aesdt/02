param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'docker-cli.ps1')

$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot '.docker.env'
$containerName = 'countyflow-ai-neo4j-1'
$dataVolume = 'countyflow-ai_countyflow_neo4j'
$recoveryContainer = 'countyflow-neo4j-offline-recovery'
$recoveryNetwork = 'countyflow-neo4j-offline-recovery-net'
$recoveryHelper = Join-Path $PSScriptRoot 'neo4j-offline-recovery.sh'

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw '.docker.env is required. Run scripts/start-full.ps1 -PrepareOnly first.'
}
if (-not (Test-Path -LiteralPath $recoveryHelper -PathType Leaf)) {
    throw 'scripts/neo4j-offline-recovery.sh is required.'
}

$passwordLine = Get-Content -LiteralPath $envFile |
    Where-Object { $_ -match '^NEO4J_PASSWORD=' } |
    Select-Object -Last 1
if (-not $passwordLine) {
    throw 'NEO4J_PASSWORD is not configured in .docker.env.'
}
$neo4jPassword = $passwordLine.Substring('NEO4J_PASSWORD='.Length)
if ($neo4jPassword -notmatch '^[A-Za-z0-9_-]{16,128}$') {
    throw 'NEO4J_PASSWORD must contain 16-128 secret-safe alphanumeric, underscore, or hyphen characters.'
}

$dockerCommand = Resolve-DockerCommand
$env:CF_RECOVERY_PASSWORD = $neo4jPassword
$recoverySucceeded = $false
try {
    & $dockerCommand stop $containerName | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the CountyFlow Neo4j container.' }

    $staleRecoveryContainer = & $dockerCommand ps -aq --filter "name=^${recoveryContainer}$"
    if ($staleRecoveryContainer) {
        & $dockerCommand rm -f $recoveryContainer | Out-Null
    }
    $staleRecoveryNetwork = & $dockerCommand network ls -q --filter "name=^${recoveryNetwork}$"
    if ($staleRecoveryNetwork) {
        & $dockerCommand network rm $recoveryNetwork | Out-Null
    }
    & $dockerCommand network create --internal $recoveryNetwork | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated Neo4j recovery network.' }
    & $dockerCommand run --detach --rm --name $recoveryContainer `
        --network $recoveryNetwork `
        --volume "${dataVolume}:/data" `
        --volume "${recoveryHelper}:/recovery.sh:ro" `
        --env NEO4J_AUTH=none `
        --env NEO4J_dbms_security_auth__enabled=false `
        --env NEO4J_server_default__listen__address=127.0.0.1 `
        --env CF_RECOVERY_PASSWORD `
        neo4j:5.26-community | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the offline Neo4j recovery container.' }

    & $dockerCommand exec $recoveryContainer /bin/bash /recovery.sh
    if ($LASTEXITCODE -ne 0) { throw 'Offline Neo4j password recovery failed.' }
    $recoverySucceeded = $true
} finally {
    Remove-Item Env:CF_RECOVERY_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:NEO4J_AUTH_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:NEO4J_LISTEN_ADDRESS -ErrorAction SilentlyContinue
    $activeRecoveryContainer = & $dockerCommand ps -aq --filter "name=^${recoveryContainer}$"
    if ($activeRecoveryContainer) {
        & $dockerCommand stop $recoveryContainer | Out-Null
    }
    $activeRecoveryNetwork = & $dockerCommand network ls -q --filter "name=^${recoveryNetwork}$"
    if ($activeRecoveryNetwork) {
        & $dockerCommand network rm $recoveryNetwork | Out-Null
    }
    # Restore the authenticated service; equivalent to docker compose --env-file .docker.env up.
    & $dockerCommand compose --env-file $envFile up -d --no-deps neo4j | Out-Null
}

if (-not $recoverySucceeded) {
    throw 'Neo4j recovery did not complete.'
}

for ($attempt = 1; $attempt -le 60; $attempt++) {
    $health = & $dockerCommand inspect $containerName --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'
    if ($health -eq 'healthy') {
        Write-Host '[OK] Neo4j password recovered offline; authenticated service is healthy.' -ForegroundColor Green
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw 'Neo4j restarted with authentication enabled but did not become healthy.'
