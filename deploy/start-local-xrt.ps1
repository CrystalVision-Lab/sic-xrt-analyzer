# Start the existing local XRT deployment when its Windows owner signs in.
# Tailscale Funnel uses its own persistent daemon configuration.
[CmdletBinding()]
param([string]$DockerExecutable = '')

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$logDirectory = Join-Path $projectRoot 'artifacts\server-startup'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory 'last-start.log'


function Test-DockerReady {
    try {
        & $dockerCommand info --format '{{.ServerVersion}}' *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

try {
    $dockerCommand = if ($DockerExecutable) { $DockerExecutable } else { (Get-Command docker -ErrorAction Stop).Source }
    if (-not (Test-Path -LiteralPath $dockerCommand -PathType Leaf)) { throw 'Docker CLI is unavailable.' }
    if (-not (Test-DockerReady)) {
        $desktopRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $dockerCommand))
        $desktopPath = Join-Path $desktopRoot 'Docker Desktop.exe'
        if (-not (Test-Path -LiteralPath $desktopPath -PathType Leaf)) {
            throw 'Docker Desktop is not installed.'
        }
        Start-Process -FilePath $desktopPath -WindowStyle Hidden
    }
    $readyDeadline = [DateTime]::UtcNow.AddMinutes(5)
    while (-not (Test-DockerReady)) {
        if ([DateTime]::UtcNow -ge $readyDeadline) {
            throw 'Docker Desktop did not become ready within five minutes.'
        }
        Start-Sleep -Seconds 3
    }
    $composeArguments = @(
        'compose', '-p', 'xrt-research',
        '-f', (Join-Path $projectRoot 'deploy\docker-compose.yml'),
        '-f', (Join-Path $projectRoot 'deploy\portal.compose.yml'),
        'up', '-d', '--no-build', '--pull', 'never',
        'postgres', 'api', 'portal', 'web'
    )
    # Compose reports normal container progress on stderr; Windows PowerShell
    # must still judge success by the process exit code.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $dockerCommand @composeArguments *> $logPath
        $composeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($composeExitCode -ne 0) {
        throw 'The existing XRT containers could not be started. See last-start.log.'
    }
    Add-Content -LiteralPath $logPath -Value ('XRT_READY ' + [DateTime]::UtcNow.ToString('o'))
    exit 0
} catch {
    Add-Content -LiteralPath $logPath -Value ('XRT_START_FAILED ' + $_.Exception.Message)
    exit 1
}