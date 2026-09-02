$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $workspaceRoot '.docker.env'

if (-not (Test-Path -LiteralPath $envFile)) {
    throw '.docker.env is required for the real Neo4j integration test.'
}

Get-Content -LiteralPath $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    $parts = $line.Split('=', 2)
    if ($parts.Length -eq 2) {
        [Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
    }
}

$env:NEO4J_URI = 'bolt://localhost:7687'
if (-not $env:NEO4J_USER) { $env:NEO4J_USER = 'neo4j' }
if ([string]::IsNullOrWhiteSpace($env:NEO4J_PASSWORD)) {
    throw 'NEO4J_PASSWORD is required for the real Neo4j integration test.'
}
if (-not $env:NEO4J_DATABASE) { $env:NEO4J_DATABASE = 'neo4j' }
$python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
& $python (Join-Path $PSScriptRoot 'graph_memory_integration.py') --warm-queries 20
exit $LASTEXITCODE
