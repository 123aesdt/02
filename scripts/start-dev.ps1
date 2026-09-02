$ErrorActionPreference = 'Stop'

function Write-Step([string]$Step) {
    Write-Host $Step -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "[成功] $Message" -ForegroundColor Green
}

function Stop-Launcher([string]$Message) {
    Write-Host "[错误] $Message" -ForegroundColor Red
    exit 1
}

function Test-BackendHealth {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
        return $health.status -eq 'ok'
    } catch {
        return $false
    }
}

function Test-HttpUrl([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    } catch {
        return $false
    }
}

function Test-LocalPortInUse([int]$Port) {
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return $null -ne ($listeners | Where-Object { $_.Port -eq $Port } | Select-Object -First 1)
}

function Wait-Until([scriptblock]$Condition, [int]$Attempts, [int]$DelayMilliseconds) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        if (& $Condition) {
            return $true
        }
        Start-Sleep -Milliseconds $DelayMilliseconds
    }
    return $false
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$databaseScript = Join-Path $projectRoot 'scripts\init-dev-db.ps1'
$databasePath = (Join-Path $backendRoot 'countyflow.db').Replace('\', '/')
$databaseUrl = "sqlite+pysqlite:///$databasePath"
$powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source

Write-Step '[1/5] 正在检查运行环境……'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Stop-Launcher '未找到项目 Python 虚拟环境 .venv。请先完成项目依赖安装。'
}
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Stop-Launcher '未检测到 Node.js / npm。请安装 Node.js 后重试。'
}
if (-not (Test-Path -LiteralPath $frontendRoot -PathType Container)) {
    Stop-Launcher '未找到 frontend 目录。'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules') -PathType Container)) {
    Write-Host '[提示] 正在安装前端依赖……'
    Push-Location $frontendRoot
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Stop-Launcher '前端 npm 依赖安装失败。'
        }
    } finally {
        Pop-Location
    }
}
Write-Ok 'Python .venv 与 Node.js/npm 均可用。'

Write-Step '[2/5] 正在准备数据库……'
try {
    & $databaseScript
    if ($LASTEXITCODE -ne 0) {
        Stop-Launcher '数据库迁移失败。'
    }
} catch {
    Stop-Launcher '数据库迁移失败。'
}
Write-Ok 'SQLite 数据库已更新到最新 Alembic 版本。'

$escapedPython = $python.Replace("'", "''")
$escapedDatabaseUrl = $databaseUrl.Replace("'", "''")
$backendProcess = $null
Write-Step '[3/5] 正在启动后端……'
if (Test-BackendHealth) {
    Write-Ok '后端已在运行。'
} elseif (Test-LocalPortInUse 8000) {
    Stop-Launcher '端口 8000 已被其他进程占用。'
} else {
    $backendCommand = "`$Host.UI.RawUI.WindowTitle = 'CountyFlow AI - Backend'; `$env:DATABASE_URL = '$escapedDatabaseUrl'; `$env:TASK_EVENT_BROKER = 'memory'; & '$escapedPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
    $backendProcess = Start-Process -FilePath $powershellExe -ArgumentList @('-NoExit', '-Command', $backendCommand) -WorkingDirectory $backendRoot -PassThru
    if (-not (Wait-Until { Test-BackendHealth } 40 500)) {
        if ($backendProcess.HasExited) {
            Stop-Launcher '后端导入失败。请查看 CountyFlow AI - 后端窗口。'
        }
        Stop-Launcher '后端未能进入健康状态。请查看 CountyFlow AI - 后端窗口。'
    }
    Write-Ok '后端已就绪：http://127.0.0.1:8000'
}

Write-Step '[4/5] 正在启动前端……'
$frontendUrl = $null
foreach ($port in 5173..5176) {
    $candidate = "http://127.0.0.1:$port"
    if (Test-HttpUrl $candidate) {
        $frontendUrl = $candidate
        Write-Ok "前端已在运行：$frontendUrl"
        break
    }
}
if (-not $frontendUrl) {
    $frontendCommand = "`$Host.UI.RawUI.WindowTitle = 'CountyFlow AI - Frontend'; `$env:VITE_DATA_MODE = 'api'; `$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'; npm run dev -- --host 127.0.0.1"
    $frontendProcess = Start-Process -FilePath $powershellExe -ArgumentList @('-NoExit', '-Command', $frontendCommand) -WorkingDirectory $frontendRoot -PassThru
    foreach ($port in 5173..5176) {
        $candidate = "http://127.0.0.1:$port"
        if (Wait-Until { Test-HttpUrl $candidate } 10 500) {
            $frontendUrl = $candidate
            break
        }
    }
    if (-not $frontendUrl) {
        if ($frontendProcess.HasExited) {
            Stop-Launcher '前端启动失败。请查看 CountyFlow AI - 前端窗口。'
        }
        Stop-Launcher '前端未能进入可用状态。请查看 CountyFlow AI - 前端窗口。'
    }
    Write-Ok "前端已就绪：$frontendUrl"
}

Write-Step '[5/5] 正在打开浏览器……'
Start-Process $frontendUrl
Write-Host ''
Write-Host '========================================'
Write-Host ' CountyFlow AI'
Write-Host '========================================'
Write-Host ' 后端：'
Write-Host ' http://127.0.0.1:8000'
Write-Host ''
Write-Host ' API 文档：'
Write-Host ' http://127.0.0.1:8000/docs'
Write-Host ''
Write-Host ' 前端：'
Write-Host " $frontendUrl"
Write-Host ''
Write-Host ' 数据库：'
Write-Host ' 已就绪'
Write-Host ''
Write-Host ' API:'
Write-Host ' 已连接'
Write-Host ''
Write-Host ' Redis:'
Write-Host ' 未启动（本地开发模式的预期状态）'
Write-Host ''
Write-Host ' Worker：'
Write-Host ' 未启动（本地开发模式的预期状态）'
Write-Host '========================================'
Write-Host '[提示] 本地开发模式未运行真实 Redis。'
Write-Host '[提示] 提交调度任务时可能返回 QUEUE_UNAVAILABLE。'
Write-Host '[提示] 如需 Docker 开发环境的 Redis/Worker 完整运行链路，请使用“一键启动完整版.bat”。'
