$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $workspaceRoot 'frontend')
try {
    & npm.cmd run build
}
finally {
    Pop-Location
}
