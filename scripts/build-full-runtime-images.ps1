param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [string]$DockerCommand = 'docker',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'

function Get-ChildRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$BasePath,
        [Parameter(Mandatory = $true)][string]$ChildPath
    )

    $baseFullPath = [IO.Path]::GetFullPath($BasePath).TrimEnd([char[]]@('\', '/'))
    $childFullPath = [IO.Path]::GetFullPath($ChildPath)
    $basePrefix = $baseFullPath + [IO.Path]::DirectorySeparatorChar
    if (-not $childFullPath.StartsWith($basePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the expected root: $childFullPath"
    }
    return $childFullPath.Substring($basePrefix.Length)
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $sha256 = $null
    $stream = $null
    try {
        $sha256 = [Security.Cryptography.SHA256]::Create()
        $stream = [IO.File]::OpenRead($Path)
        return ([BitConverter]::ToString($sha256.ComputeHash($stream))).Replace('-', '')
    }
    finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
        if ($null -ne $sha256) {
            $sha256.Dispose()
        }
    }
}

function Assert-ContextHashes {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$DestinationRoot,
        [Parameter(Mandatory = $true)][string[]]$RelativePaths
    )

    $destinationPaths = @(
        Get-ChildItem -LiteralPath $DestinationRoot -Recurse -File -Force |
            ForEach-Object { Get-ChildRelativePath -BasePath $DestinationRoot -ChildPath $_.FullName } |
            Sort-Object
    )
    if ($destinationPaths.Count -ne $RelativePaths.Count) {
        throw "Staged build context file count mismatch: $DestinationRoot"
    }

    foreach ($relativePath in $RelativePaths) {
        $sourcePath = Join-Path $SourceRoot $relativePath
        $destinationPath = Join-Path $DestinationRoot $relativePath
        if (-not (Test-Path -LiteralPath $destinationPath -PathType Leaf)) {
            throw "Staged build file is missing: $relativePath"
        }
        $sourceHash = Get-FileSha256 -Path $sourcePath
        $destinationHash = Get-FileSha256 -Path $destinationPath
        if ($sourceHash -ne $destinationHash) {
            throw "Staged build file hash mismatch: $relativePath"
        }
    }
}

function Copy-VerifiedContext {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$DestinationRoot,
        [Parameter(Mandatory = $true)][scriptblock]$IncludeFile,
        [Parameter(Mandatory = $true)][scriptblock]$IncludeDirectory
    )

    $sourceFullPath = [IO.Path]::GetFullPath($SourceRoot)
    if (-not (Test-Path -LiteralPath $sourceFullPath -PathType Container)) {
        throw "Build context source directory is missing: $sourceFullPath"
    }

    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    $pendingDirectories = [Collections.Generic.Stack[string]]::new()
    $pendingDirectories.Push($sourceFullPath)
    $relativePaths = [Collections.Generic.List[string]]::new()
    while ($pendingDirectories.Count -gt 0) {
        $currentDirectory = $pendingDirectories.Pop()
        foreach ($entry in Get-ChildItem -LiteralPath $currentDirectory -Force) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                continue
            }
            $relativePath = Get-ChildRelativePath -BasePath $sourceFullPath -ChildPath $entry.FullName
            if ($entry.PSIsContainer) {
                if (& $IncludeDirectory $relativePath) {
                    $pendingDirectories.Push($entry.FullName)
                }
            } elseif (& $IncludeFile $relativePath) {
                $relativePaths.Add($relativePath)
            }
        }
    }
    $relativePaths = @($relativePaths | Sort-Object)
    if ($relativePaths.Count -eq 0) {
        throw "Build context is empty: $sourceFullPath"
    }

    foreach ($relativePath in $relativePaths) {
        $destinationPath = Join-Path $DestinationRoot $relativePath
        New-Item -ItemType Directory -Path (Split-Path -Parent $destinationPath) -Force | Out-Null
        $sourceBytes = [IO.File]::ReadAllBytes((Join-Path $sourceFullPath $relativePath))
        [IO.File]::WriteAllBytes($destinationPath, $sourceBytes)
    }
    Assert-ContextHashes -SourceRoot $sourceFullPath -DestinationRoot $DestinationRoot -RelativePaths $relativePaths
    $stagedBytes = (
        $relativePaths |
            ForEach-Object { (Get-Item -LiteralPath (Join-Path $DestinationRoot $_)).Length } |
            Measure-Object -Sum
    ).Sum
    Write-Host ("[暂存] {0}：{1} 个文件，{2} 字节" -f (Split-Path -Leaf $SourceRoot), $relativePaths.Count, $stagedBytes)
}

function Remove-SafeStagingRoot {
    param([Parameter(Mandatory = $true)][string]$Path)

    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $resolvedPath = [IO.Path]::GetFullPath($Path)
    $relativePath = Get-ChildRelativePath -BasePath $temporaryRoot -ChildPath $resolvedPath
    if (
        [IO.Path]::IsPathRooted($relativePath) -or
        $relativePath.Contains('..') -or
        $relativePath -notmatch '^countyflow-build-[0-9a-f]{32}$'
    ) {
        throw "Refusing to remove unsafe staging path: $resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

function Invoke-CheckedDocker {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & $DockerCommand @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed: docker $($Arguments[0])"
    }
}

$projectFullPath = [IO.Path]::GetFullPath($ProjectRoot)
$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) ("countyflow-build-{0}" -f [guid]::NewGuid().ToString('N'))
$backendStage = Join-Path $stagingRoot 'backend'
$frontendStage = Join-Path $stagingRoot 'frontend'
$qdrantStage = Join-Path $stagingRoot 'qdrant'

try {
    $backendFilter = {
        param($relativePath)
        $normalized = $relativePath.Replace('\', '/')
        $segments = $normalized.Split('/')
        if ($segments -contains '__pycache__' -or $normalized.EndsWith('.pyc')) {
            return $false
        }
        return (
            $normalized -in @('Dockerfile', 'pyproject.toml', 'alembic.ini') -or
            $normalized.StartsWith('app/') -or
            $normalized.StartsWith('alembic/')
        )
    }
    $backendDirectoryFilter = {
        param($relativePath)
        $normalized = $relativePath.Replace('\', '/')
        return (
            $normalized -eq 'app' -or
            $normalized.StartsWith('app/') -or
            $normalized -eq 'alembic' -or
            $normalized.StartsWith('alembic/')
        )
    }
    $frontendFilter = {
        param($relativePath)
        $normalized = $relativePath.Replace('\', '/')
        $segments = $normalized.Split('/')
        $excludedSegmentCount = @(
            $segments | Where-Object { $_ -in @('node_modules', '.npm-cache', 'dist') }
        ).Count
        if ($excludedSegmentCount -gt 0) {
            return $false
        }
        $name = [IO.Path]::GetFileName($normalized)
        return (
            $name -ne '.env' -and
            -not $name.StartsWith('.env.') -and
            $name -ne 'npm-debug.log'
        )
    }
    $frontendDirectoryFilter = {
        param($relativePath)
        $normalized = $relativePath.Replace('\', '/')
        $segments = $normalized.Split('/')
        return @(
            $segments | Where-Object { $_ -in @('node_modules', '.npm-cache', 'dist') }
        ).Count -eq 0
    }
    $qdrantFilter = {
        param($relativePath)
        return $relativePath.Replace('\', '/') -eq 'qdrant.Dockerfile'
    }
    $qdrantDirectoryFilter = { return $false }

    Copy-VerifiedContext -SourceRoot (Join-Path $projectFullPath 'backend') -DestinationRoot $backendStage -IncludeFile $backendFilter -IncludeDirectory $backendDirectoryFilter
    Copy-VerifiedContext -SourceRoot (Join-Path $projectFullPath 'frontend') -DestinationRoot $frontendStage -IncludeFile $frontendFilter -IncludeDirectory $frontendDirectoryFilter
    Copy-VerifiedContext -SourceRoot (Join-Path $projectFullPath 'infra') -DestinationRoot $qdrantStage -IncludeFile $qdrantFilter -IncludeDirectory $qdrantDirectoryFilter
    Write-Host '[成功] 已验证暂存 Docker 构建上下文。' -ForegroundColor Green

    if (-not $ValidateOnly) {
        Write-Host '[构建] 后端、迁移与 Worker……' -ForegroundColor Cyan
        Invoke-CheckedDocker -Arguments @(
            'build',
            '--no-cache',
            '--tag',
            'countyflow-ai-backend:latest',
            $backendStage
        )
        foreach ($tag in @(
            'countyflow-ai-migration:latest',
            'countyflow-ai-worker-1:latest',
            'countyflow-ai-worker-2:latest'
        )) {
            Invoke-CheckedDocker -Arguments @(
                'image',
                'tag',
                'countyflow-ai-backend:latest',
                $tag
            )
        }

        Write-Host '[构建] 前端……' -ForegroundColor Cyan
        Invoke-CheckedDocker -Arguments @(
            'build',
            '--no-cache',
            '--build-arg',
            'VITE_DATA_MODE=api',
            '--build-arg',
            'VITE_API_BASE_URL=http://localhost:8001',
            '--build-arg',
            'VITE_AUTHENTICATION_MODE=development_jwt',
            '--build-arg',
            'VITE_RUNTIME_THREAD_STATE_ENABLED=true',
            '--tag',
            'countyflow-ai-frontend:latest',
            $frontendStage
        )

        Write-Host '[构建] Qdrant……' -ForegroundColor Cyan
        Invoke-CheckedDocker -Arguments @(
            'build',
            '--no-cache',
            '--file',
            (Join-Path $qdrantStage 'qdrant.Dockerfile'),
            '--tag',
            'countyflow-ai-qdrant:latest',
            $qdrantStage
        )
    }
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-SafeStagingRoot -Path $stagingRoot
    }
}
