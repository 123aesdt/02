function Resolve-DockerCommand {
    param(
        [object]$PathCommand = (Get-Command docker -ErrorAction SilentlyContinue),
        [string[]]$CandidatePaths = @(
            (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Docker\Docker\resources\bin\docker.exe')
        )
    )

    if ($null -ne $PathCommand) {
        if ($PathCommand -is [string]) { return $PathCommand }
        if ($PathCommand.Source) { return $PathCommand.Source }
        if ($PathCommand.Path) { return $PathCommand.Path }
    }
    foreach ($candidate in $CandidatePaths) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    throw 'Docker Desktop / Docker CLI 未检测到。'
}
