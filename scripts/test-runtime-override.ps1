$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $workspaceRoot 'backend'

if (-not $env:DATABASE_URL) { throw 'DATABASE_URL is required.' }

& $python (Join-Path $PSScriptRoot 'runtime_override_integration.py') `
    --database-url $env:DATABASE_URL `
    --redis-url 'redis://127.0.0.1:6380/0' `
    --output (Join-Path $workspaceRoot 'docs\verification\raw\v2-d1-runtime-override.json')
exit $LASTEXITCODE
