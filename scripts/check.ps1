$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot

function Invoke-CheckedStep([string]$Name, [string]$ScriptPath) {
    Write-Host "[CHECK] $Name" -ForegroundColor Cyan
    & $ScriptPath
    $stepExitCode = $LASTEXITCODE
    if ($stepExitCode -ne 0) {
        Write-Host "[FAILED] $Name (exit $stepExitCode)" -ForegroundColor Red
        exit $stepExitCode
    }
}

$steps = @(
    @{ Name = 'Backend Ruff'; Script = 'lint.ps1' },
    @{ Name = 'Backend Pytest'; Script = 'test.ps1' },
    @{ Name = 'Frontend lint'; Script = 'frontend-lint.ps1' },
    @{ Name = 'Frontend tests'; Script = 'frontend-test.ps1' },
    @{ Name = 'Frontend build'; Script = 'frontend-build.ps1' }
)

foreach ($step in $steps) {
    Invoke-CheckedStep $step.Name (Join-Path $PSScriptRoot $step.Script)
}

Write-Host '[OK] All quality gates passed.' -ForegroundColor Green
if ($env:RUN_DOCKER_ACCEPTANCE -eq '1') {
    Invoke-CheckedStep 'Docker observability acceptance' (Join-Path $PSScriptRoot 'test-observability.ps1')
}
exit 0
