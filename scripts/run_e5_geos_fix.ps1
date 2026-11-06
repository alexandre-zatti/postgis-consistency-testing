# E5 launcher (PowerShell 7): build the two GEOS images, then replay family A on them.
#
#   pwsh -NoProfile -File scripts/run_e5_geos_fix.ps1
#
# Steps:
#   1. docker build docker/geos-rebuild -> tavs-geos:before-fc3eca90 (GEOS fc3eca90, parent of the fix)
#   2. docker build docker/geos-rebuild -> tavs-geos:fix-2c8e04fa    (GEOS 2c8e04fa, merge of PR #1590)
#   3. python -s -m tavs.replay_fix (targets before, fix, and the pinned dev image as anchor)
# Everything goes to runs/e5-geos-fix/log.txt. The last action writes runs/e5-geos-fix/DONE with
# the exit code: 0 ok, 11 or 12 a build failed (before, fix), 13 the base image is missing,
# otherwise the replay's code (1 exception, 3 a target failed its GEOS verification).
# Existing images and containers are not touched; the replay removes its own tavs-e5-* containers.
# -PreflightOnly runs only the checks before step 1 (git, docker, base image) and writes DONE.

param(
    [string]$OutDir = '',
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$Out = if ($OutDir) { $OutDir } else { Join-Path $Root 'runs/e5-geos-fix' }
$Log = Join-Path $Out 'log.txt'
$Done = Join-Path $Out 'DONE'
$Py = Join-Path $Root '.venv/Scripts/python.exe'
$Base = 'postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107'
$Context = Join-Path $Root 'docker/geos-rebuild'
$Builds = @(
    @{ Tag = 'tavs-geos:before-fc3eca90'; Commit = 'fc3eca9063096a665700651d6523f56de4dae415'; Fail = 11 },
    @{ Tag = 'tavs-geos:fix-2c8e04fa';    Commit = '2c8e04faf8235456b417979bcf23271ef34148a7'; Fail = 12 }
)
$Jobs = 6

New-Item -ItemType Directory -Force $Out | Out-Null
if (Test-Path $Done) {
    Move-Item $Done (Join-Path $Out ("DONE.prev-" + (Get-Date -Format 'yyyyMMdd-HHmmss')))
}
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:DOCKER_BUILDKIT = '1'

function Say([string]$m) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'), $m
    Add-Content -Path $Log -Value $line -Encoding utf8
}
function Run([string]$exe, [string[]]$argv) {
    Say ("$ " + $exe + ' ' + ($argv -join ' '))
    & $exe @argv 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $Log -Encoding utf8
    $rc = $LASTEXITCODE
    Say "exit code $rc"
    return $rc
}

function Main {
    Say "E5 start; root $Root; out $Out; PowerShell $($PSVersionTable.PSVersion); host $env:COMPUTERNAME"
    Run 'git' @('-C', $Root, 'rev-parse', 'HEAD') | Out-Null
    Run 'git' @('-C', $Root, 'status', '--porcelain', '--', 'tavs', 'docker', 'scripts') | Out-Null
    Run 'docker' @('version', '--format', '{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}') | Out-Null
    Run 'docker' @('info', '--format', 'MemTotal={{.MemTotal}} NCPU={{.NCPU}}') | Out-Null
    if ((Run 'docker' @('image', 'inspect', '--format', '{{.Id}} {{json .RepoDigests}}', $Base)) -ne 0) {
        Say "base image $Base is not present locally"
        return 13
    }
    if ($PreflightOnly) { Say 'preflight only: stop before the builds'; return 0 }
    foreach ($b in $Builds) {
        Say "build $($b.Tag) at GEOS $($b.Commit)"
        $rc = Run 'docker' @('build', '--progress=plain', '-t', $b.Tag,
            '--build-arg', "GEOS_COMMIT=$($b.Commit)", '--build-arg', "JOBS=$Jobs",
            '--build-arg', "BASE_IMAGE=$Base", $Context)
        if ($rc -ne 0) { return $b.Fail }
        Run 'docker' @('image', 'inspect', '--format',
            '{{.Id}} {{.Created}} {{json .Config.Labels}}', $b.Tag) | Out-Null
    }
    Say 'replay'
    Push-Location $Root
    try {
        return (Run $Py @('-s', '-m', 'tavs.replay_fix'))
    } finally {
        Pop-Location
    }
}

$code = 1
try {
    $code = Main
} catch {
    Say "launcher exception: $_"
    $code = 1
} finally {
    Say "E5 end; exit code $code"
    Set-Content -Path $Done -Value "$code" -Encoding ascii -NoNewline
}
exit $code
