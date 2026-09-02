$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project .venv Python is unavailable.' }

$previousAuthProvider = $env:AUTHENTICATION_PROVIDER
try {
    $env:AUTHENTICATION_PROVIDER = 'disabled'
    & $python -m pytest `
        (Join-Path $projectRoot 'backend\tests\security') `
        (Join-Path $projectRoot 'backend\tests\api\test_authentication.py') `
        (Join-Path $projectRoot 'backend\tests\api\test_endpoint_permissions.py') `
        (Join-Path $projectRoot 'backend\tests\api\test_rate_limit.py') `
        (Join-Path $projectRoot 'backend\tests\api\test_ws_ticket.py') `
        (Join-Path $projectRoot 'backend\tests\observability\test_security_metrics.py') -q
    if ($LASTEXITCODE -ne 0) { throw 'Focused backend security tests failed.' }
} finally {
    if ($null -eq $previousAuthProvider) { Remove-Item Env:AUTHENTICATION_PROVIDER -ErrorAction SilentlyContinue } else { $env:AUTHENTICATION_PROVIDER = $previousAuthProvider }
}

Push-Location (Join-Path $projectRoot 'frontend')
try {
    & npm test -- --run tests/auth-session.test.tsx tests/task-event-client.test.ts tests/task-events-lifecycle.test.tsx
    if ($LASTEXITCODE -ne 0) { throw 'Focused frontend security tests failed.' }
} finally { Pop-Location }

& $python (Join-Path $PSScriptRoot 'security_integration.py')
if ($LASTEXITCODE -ne 0) { throw 'Docker security integration failed.' }

$envFile = Join-Path $projectRoot '.docker.env'
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw 'Ignored .docker.env is required for browser security E2E.' }
$dockerEnv = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^(?<key>DEVELOPMENT_JWT_SECRET|AUTH_ISSUER|AUTH_AUDIENCE)=(?<value>.*)$') {
        $dockerEnv[$Matches.key] = $Matches.value
    }
}
if ([string]::IsNullOrWhiteSpace($dockerEnv.DEVELOPMENT_JWT_SECRET)) { throw 'Docker development signing configuration is unavailable.' }
$previousBrowserEnv = @{
    DEVELOPMENT_JWT_SECRET = $env:DEVELOPMENT_JWT_SECRET
    AUTH_ISSUER = $env:AUTH_ISSUER
    AUTH_AUDIENCE = $env:AUTH_AUDIENCE
    E2E_API_BASE_URL = $env:E2E_API_BASE_URL
    E2E_WEB_BASE_URL = $env:E2E_WEB_BASE_URL
}
try {
    $env:DEVELOPMENT_JWT_SECRET = $dockerEnv.DEVELOPMENT_JWT_SECRET
    $env:AUTH_ISSUER = $dockerEnv.AUTH_ISSUER
    $env:AUTH_AUDIENCE = $dockerEnv.AUTH_AUDIENCE
    $env:E2E_API_BASE_URL = 'http://localhost:8001'
    $env:E2E_WEB_BASE_URL = 'http://localhost:5173'
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & npm exec playwright test -- security-auth.spec.ts
        if ($LASTEXITCODE -ne 0) { throw 'Five-role browser security E2E failed.' }
    } finally { Pop-Location }
} finally {
    foreach ($name in $previousBrowserEnv.Keys) {
        $value = $previousBrowserEnv[$name]
        if ($null -eq $value) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue } else { Set-Item "Env:$name" $value }
    }
}
Write-Host '[OK] V2-G2 focused security, real Docker controls, and five-role browser acceptance passed.' -ForegroundColor Green
