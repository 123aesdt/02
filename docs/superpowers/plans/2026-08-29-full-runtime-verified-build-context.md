# Full Runtime Verified Build Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Full Runtime Docker images from receiving corrupted source bytes when the repository is stored in OneDrive.

**Architecture:** A focused PowerShell builder copies the exact Docker inputs to an OS-temporary directory, verifies a SHA-256 manifest, builds the Compose image tags there, and safely removes its staging directory. `start-full.ps1` calls that builder and then starts the existing Compose project with `--no-build`.

**Tech Stack:** Windows PowerShell 5.1, PowerShell 7, Docker Engine, Docker Compose, pytest

**Spec:** `docs/superpowers/specs/2026-08-29-full-runtime-verified-build-context-design.md`

## Global Constraints

- Preserve all current user changes in the dirty `master` workspace.
- Never print or copy `.docker.env`, `.env`, authorization headers, or key material into a Docker context.
- Do not change business endpoints, runtime graph behavior, persistence, queues, service count, ports, or volumes.
- Use behavior-level RED-GREEN TDD and never weaken a test to pass.
- Before completion run `ruff check backend`, `pytest`, frontend lint/test/build, targeted Docker checks, and `git -c safe.directory=<workspace> diff --check`.

---

### Task 1: Specify verified staging and launcher wiring

**Files:**
- Modify: `backend/tests/unit/test_dev_launcher_scripts.py`
- Create: `scripts/build-full-runtime-images.ps1`
- Modify: `scripts/start-full.ps1`

**Interfaces:**
- Consumes: the existing repository layout and `Resolve-DockerCommand` result
- Produces: `build-full-runtime-images.ps1 -ProjectRoot <path> -DockerCommand <path> [-ValidateOnly]`

- [ ] **Step 1: Write failing behavior and wiring tests**

```python
def test_verified_full_runtime_builder_stages_and_hashes_without_docker() -> None:
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(BUILDER), "-ProjectRoot", str(PROJECT_ROOT), "-ValidateOnly"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Verified staged Docker contexts" in result.stdout


def test_full_launcher_uses_verified_images_and_disables_compose_build() -> None:
    source = (PROJECT_ROOT / "scripts" / "start-full.ps1").read_text(encoding="utf-8")
    assert "build-full-runtime-images.ps1" in source
    assert "up -d --no-build" in source
    assert "up -d --build" not in source
```

- [ ] **Step 2: Run tests to verify RED**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/unit/test_dev_launcher_scripts.py -k "verified_full_runtime or full_launcher_uses_verified" -v`

Expected: FAIL because the builder is absent and the launcher still uses `--build`.

- [ ] **Step 3: Implement verified staging and building**

```powershell
param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [string]$DockerCommand = 'docker',
    [switch]$ValidateOnly
)

function Assert-ContextHashes(
    [string]$SourceRoot,
    [string]$DestinationRoot,
    [string[]]$RelativePaths
) {
    foreach ($relativePath in $RelativePaths) {
        $sourceHash = (Get-FileHash -LiteralPath (Join-Path $SourceRoot $relativePath) -Algorithm SHA256).Hash
        $destinationHash = (Get-FileHash -LiteralPath (Join-Path $DestinationRoot $relativePath) -Algorithm SHA256).Hash
        if ($sourceHash -ne $destinationHash) {
            throw "Staged build file hash mismatch: $relativePath"
        }
    }
}

function Copy-VerifiedContext(
    [string]$SourceRoot,
    [string]$DestinationRoot,
    [scriptblock]$IncludeFile,
    [scriptblock]$IncludeDirectory
) {
    $sourceFullPath = [IO.Path]::GetFullPath($SourceRoot)
    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    $pendingDirectories = [Collections.Generic.Stack[string]]::new()
    $pendingDirectories.Push($sourceFullPath)
    $relativePaths = [Collections.Generic.List[string]]::new()
    while ($pendingDirectories.Count -gt 0) {
        $currentDirectory = $pendingDirectories.Pop()
        foreach ($entry in Get-ChildItem -LiteralPath $currentDirectory -Force) {
            $relativePath = [IO.Path]::GetRelativePath($sourceFullPath, $entry.FullName)
            if ($entry.PSIsContainer -and (& $IncludeDirectory $relativePath)) {
                $pendingDirectories.Push($entry.FullName)
            } elseif (-not $entry.PSIsContainer -and (& $IncludeFile $relativePath)) {
                $relativePaths.Add($relativePath)
            }
        }
    }
    $relativePaths = @($relativePaths | Sort-Object)
    if ($relativePaths.Count -eq 0) { throw "Build context is empty: $SourceRoot" }
    foreach ($relativePath in $relativePaths) {
        $destinationPath = Join-Path $DestinationRoot $relativePath
        New-Item -ItemType Directory -Path (Split-Path -Parent $destinationPath) -Force | Out-Null
        $sourceBytes = [IO.File]::ReadAllBytes((Join-Path $sourceFullPath $relativePath))
        [IO.File]::WriteAllBytes($destinationPath, $sourceBytes)
    }
    Assert-ContextHashes $sourceFullPath $DestinationRoot $relativePaths
}

function Remove-SafeStagingRoot([string]$Path) {
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $resolvedPath = [IO.Path]::GetFullPath($Path)
    $relativePath = [IO.Path]::GetRelativePath($temporaryRoot, $resolvedPath)
    if ([IO.Path]::IsPathRooted($relativePath) -or $relativePath.Contains('..') -or $relativePath -notmatch '^countyflow-build-[0-9a-f]{32}$') {
        throw "Refusing to remove unsafe staging path: $resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

function Invoke-CheckedDocker([string[]]$Arguments) {
    & $DockerCommand @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $($Arguments[0])" }
}
```

```powershell
$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) ("countyflow-build-{0}" -f [guid]::NewGuid().ToString('N'))
$backendStage = Join-Path $stagingRoot 'backend'
$frontendStage = Join-Path $stagingRoot 'frontend'
$qdrantStage = Join-Path $stagingRoot 'qdrant'
try {
    $backendFilter = {
        param($relativePath)
        $normalized = $relativePath.Replace('\', '/')
        $segments = $normalized.Split('/')
        if ($segments -contains '__pycache__' -or $normalized.EndsWith('.pyc')) { return $false }
        return $normalized -in @('Dockerfile', 'pyproject.toml', 'alembic.ini') -or
            $normalized.StartsWith('app/') -or $normalized.StartsWith('alembic/')
    }
    $frontendFilter = {
        param($relativePath)
        $normalized = $relativePath.Replace('\', '/')
        $segments = $normalized.Split('/')
        if (@($segments | Where-Object { $_ -in @('node_modules', '.npm-cache', 'dist') }).Count -gt 0) { return $false }
        $name = [IO.Path]::GetFileName($normalized)
        return $name -ne '.env' -and -not $name.StartsWith('.env.') -and $name -ne 'npm-debug.log'
    }
    $qdrantFilter = { param($relativePath) $relativePath.Replace('\', '/') -eq 'qdrant.Dockerfile' }

    Copy-VerifiedContext (Join-Path $ProjectRoot 'backend') $backendStage $backendFilter
    Copy-VerifiedContext (Join-Path $ProjectRoot 'frontend') $frontendStage $frontendFilter
    Copy-VerifiedContext (Join-Path $ProjectRoot 'infra') $qdrantStage $qdrantFilter
    Write-Host '[OK] Verified staged Docker contexts.' -ForegroundColor Green

    if (-not $ValidateOnly) {
        Invoke-CheckedDocker @('build', '--no-cache', '--tag', 'countyflow-ai-backend:latest', $backendStage)
        foreach ($tag in @('countyflow-ai-migration:latest', 'countyflow-ai-worker-1:latest', 'countyflow-ai-worker-2:latest')) {
            Invoke-CheckedDocker @('image', 'tag', 'countyflow-ai-backend:latest', $tag)
        }
        Invoke-CheckedDocker @(
            'build',
            '--no-cache',
            '--build-arg', 'VITE_DATA_MODE=api',
            '--build-arg', 'VITE_API_BASE_URL=http://localhost:8001',
            '--build-arg', 'VITE_AUTHENTICATION_MODE=development_jwt',
            '--build-arg', 'VITE_RUNTIME_THREAD_STATE_ENABLED=true',
            '--tag', 'countyflow-ai-frontend:latest',
            $frontendStage
        )
        Invoke-CheckedDocker @(
            'build', '--no-cache', '--file', (Join-Path $qdrantStage 'qdrant.Dockerfile'),
            '--tag', 'countyflow-ai-qdrant:latest', $qdrantStage
        )
    }
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) { Remove-SafeStagingRoot $stagingRoot }
}
```

- [ ] **Step 4: Wire the launcher to verified images**

```powershell
$builder = Join-Path $PSScriptRoot 'build-full-runtime-images.ps1'
& $builder -ProjectRoot $projectRoot -DockerCommand $dockerCommand
& $dockerCommand compose --env-file $envFile up -d --no-build
```

- [ ] **Step 5: Run focused tests to verify GREEN**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest tests/unit/test_dev_launcher_scripts.py -v`

Expected: all launcher tests pass.

### Compatibility correction: double-click launcher runtime

The desktop batch file invokes `powershell.exe`, not `pwsh`. The builder must therefore avoid APIs that are absent or unreliable in the Windows PowerShell 5.1 process environment:

- Compute child-relative paths with normalized full paths, an ordinal-ignore-case descendant check, and prefix removal instead of `[IO.Path]::GetRelativePath`.
- Compute SHA-256 with `[Security.Cryptography.SHA256]::Create()` and `[IO.File]::OpenRead()` instead of relying on `Get-FileHash` module auto-loading.
- Run `test_verified_full_runtime_builder_supports_windows_powershell` before accepting the launcher fix, then execute `一键启动完整版.bat` itself as the final user-path check.

### Task 2: Recover and verify Full Runtime

**Files:**
- Modify: none
- Test: Docker images, Compose services, HTTP endpoints, Redis consumer state

**Interfaces:**
- Consumes: verified images `countyflow-ai-backend`, `countyflow-ai-migration`, `countyflow-ai-worker-1`, `countyflow-ai-worker-2`, `countyflow-ai-frontend`, and `countyflow-ai-qdrant`
- Produces: healthy existing Full Runtime services

- [ ] **Step 1: Run the repaired launcher without opening a second browser**

```powershell
& scripts/build-full-runtime-images.ps1 -ProjectRoot $PWD -DockerCommand docker
docker compose --env-file .docker.env up -d --no-build
```

- [ ] **Step 2: Verify source integrity inside the backend image**

```powershell
$hostHash = (Get-FileHash backend/app/api/v1/task_events.py -Algorithm SHA256).Hash
$imageHash = docker run --rm --entrypoint python countyflow-ai-backend -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('/app/app/api/v1/task_events.py').read_bytes()).hexdigest().upper())"
if ($hostHash -ne $imageHash.Trim()) { throw 'Backend image source hash mismatch.' }
```

- [ ] **Step 3: Verify runtime state**

Run: `docker compose --env-file .docker.env ps -a`

Expected: backend/frontend/dependencies healthy or running, migration exited with code 0, and both workers running.

Run: HTTP checks for `http://localhost:8001/health`, `http://localhost:5173`, and `http://localhost:3000/api/health`.

Expected: HTTP 200 from each endpoint.

- [ ] **Step 4: Verify quality gates and workspace diff**

Run: `scripts/check.ps1`

Expected: backend Ruff/pytest and frontend lint/test/build all exit 0.

Run: `git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check`

Expected: exit 0 with no output.
