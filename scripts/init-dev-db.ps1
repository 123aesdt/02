$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'

if (-not $env:DATABASE_URL) {
    $databasePath = (Join-Path $workspaceRoot 'backend\countyflow.db').Replace('\', '/')
    $env:DATABASE_URL = "sqlite+pysqlite:///$databasePath"
}

Push-Location (Join-Path $workspaceRoot 'backend')
try {
    & $python -m alembic -c alembic.ini upgrade head
} finally {
    Pop-Location
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
