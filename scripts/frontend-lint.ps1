$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $workspaceRoot 'frontend')
try {
    & npm.cmd run lint
}
finally {
    Pop-Location
}
