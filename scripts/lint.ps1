$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Push-Location $workspaceRoot
try {
    & (Join-Path $workspaceRoot '.venv/Scripts/python.exe') -m ruff check backend
}
finally {
    Pop-Location
}
