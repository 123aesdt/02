param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('DISPATCHER', 'SUPERVISOR', 'OPERATOR', 'AUDITOR', 'ADMIN')]
    [string]$Role,
    [ValidateRange(1, 900)]
    [int]$TtlSeconds = 600
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$helper = Join-Path $PSScriptRoot 'create_dev_token.py'
$profile = if ($env:RUNTIME_PROFILE) { $env:RUNTIME_PROFILE } else { 'local' }

if ($profile -eq 'production') { throw 'Development JWT creation is forbidden in production.' }
if (-not $env:DEVELOPMENT_JWT_SECRET) { throw 'DEVELOPMENT_JWT_SECRET is not configured in the ignored environment.' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project .venv Python is unavailable.' }

Write-Warning 'The next line is a short-lived development access token. Do not save it in logs, source control, or command history.'
& $python $helper --role $Role --ttl-seconds $TtlSeconds
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
