param(
    [string]$EnvFile = ''
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspaceRoot '.venv\Scripts\python.exe'
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $workspaceRoot '.env'
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Write-Error 'Local .venv Python was not found.'
    exit 2
}
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    Write-Error 'Local .env file was not found.'
    exit 2
}

try {
    foreach ($line in Get-Content -LiteralPath $EnvFile -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) {
            continue
        }
        $parts = $trimmed.Split('=', 2)
        $name = $parts[0].Trim()
        if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
            continue
        }
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, 'Process'))) {
            $value = $parts[1].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}
catch {
    Write-Error 'Local .env could not be loaded safely.'
    exit 2
}

$required = @(
    'EMBEDDING_BASE_URL',
    'EMBEDDING_API_KEY',
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMENSION'
)
foreach ($name in $required) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, 'Process'))) {
        Write-Error "Missing required configuration: $name"
        exit 2
    }
}
Write-Host 'EMBEDDING_BASE_URL: CONFIGURED'
Write-Host 'EMBEDDING_API_KEY: CONFIGURED'
Write-Host 'EMBEDDING_MODEL: CONFIGURED'
Write-Host 'EMBEDDING_DIMENSION: CONFIGURED'

$qdrantUrl = 'http://localhost:6333'
try {
    $null = Invoke-WebRequest -UseBasicParsing -Uri "$qdrantUrl/readyz" -TimeoutSec 5
}
catch {
    Write-Error 'Docker Qdrant is not ready at http://localhost:6333.'
    exit 3
}

$runner = Join-Path $workspaceRoot 'scripts\run_memory_benchmark.py'
$output = Join-Path $workspaceRoot 'docs\verification\v2-e\raw\v2-e-real-embedding-regression.json'
$csvOutput = Join-Path $workspaceRoot 'docs\verification\v2-e\raw\v2-e-real-embedding-regression.csv'
$finalReport = Join-Path $workspaceRoot 'docs\verification\v2-e\v2-e-final-acceptance.md'
$vectorReport = Join-Path $workspaceRoot 'docs\verification\v2-e\vector-memory-acceptance.md'

$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $workspaceRoot 'backend'
Push-Location $workspaceRoot
try {
    & $python $runner `
        --require-real `
        --qdrant-url $qdrantUrl `
        --output $output `
        --csv-output $csvOutput `
        --final-report $finalReport `
        --vector-report $vectorReport
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host 'Real embedding regression result created successfully.'
Write-Host $output
exit 0
