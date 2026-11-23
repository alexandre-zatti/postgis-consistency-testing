# E6 launcher (PowerShell 7): build four GEOS images, then replay families B to F on them.
#
#   pwsh -NoProfile -File scripts/run_e6_geos_fixes.ps1
#
# Steps:
#   1. docker build docker/geos-rebuild -> tavs-geos:before-faaaad0b (parent of the merge of PR #1601)
#   2. docker build docker/geos-rebuild -> tavs-geos:fix-695a1909    (merge of PR #1601, family B)
#   3. docker build docker/geos-rebuild -> tavs-geos:before-b6754aa2 (parent of the merge of PR #1615)
#   4. docker build docker/geos-rebuild -> tavs-geos:fix-35fa80c9    (merge of PR #1615, family D)
#   5. python -s -m tavs.replay_fixes (the four targets, in that order)
# Everything goes to runs/e6-geos-fixes/log.txt. The last action writes runs/e6-geos-fixes/DONE
# with the exit code: 0 ok, 10 the base image is missing, 11 to 14 a build failed (in the order
# above), otherwise the replay's code (1 exception, 3 a target failed its GEOS verification).
# Existing images and containers are not touched; the replay removes its own containers.
# -BuildOnly stops after step 4 and writes BUILD_DONE instead of DONE.

param(
    [string]$OutDir = '',
    [switch]$BuildOnly
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$Out = if ($OutDir) { $OutDir } else { Join-Path $Root 'runs/e6-geos-fixes' }
$Log = Join-Path $Out 'log.txt'
$Done = Join-Path $Out $(if ($BuildOnly) { 'BUILD_DONE' } else { 'DONE' })
$Py = Join-Path $Root '.venv/Scripts/python.exe'
$Base = 'postgis/postgis@sha256:620f1f1ffb479ffbda686dbfde113557a9859cdf9de0f86683b0702846915107'
$Context = Join-Path $Root 'docker/geos-rebuild'
$Builds = @(
    @{ Tag = 'tavs-geos:before-faaaad0b'; Commit = 'faaaad0b0b95e8a0bdb72e2b28416bd1511e7deb'; Fail = 11 },
    @{ Tag = 'tavs-geos:fix-695a1909';    Commit = '695a19097e4750e689c02f6b4de69bc25a5f70e3'; Fail = 12 },
    @{ Tag = 'tavs-geos:before-b6754aa2'; Commit = 'b6754aa2eb591a2bdabfe7f730c1e3c9c71408e5'; Fail = 13 },
    @{ Tag = 'tavs-geos:fix-35fa80c9';    Commit = '35fa80c99e8db5738f06163082caa49fc7c2ee3d'; Fail = 14 }
)
$Jobs = 6

New-Item -ItemType Directory -Force $Out | Out-Null
if (Test-Path $Done) {
    Move-Item $Done ($Done + '.prev-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
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
    Say "E6 start; root $Root; out $Out; build only $BuildOnly; PowerShell $($PSVersionTable.PSVersion); host $env:COMPUTERNAME"
    Run 'git' @('-C', $Root, 'rev-parse', 'HEAD') | Out-Null
    Run 'git' @('-C', $Root, 'status', '--porcelain', '--', 'tavs', 'docker', 'scripts') | Out-Null
    Run 'docker' @('version', '--format', '{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}') | Out-Null
    Run 'docker' @('info', '--format', 'MemTotal={{.MemTotal}} NCPU={{.NCPU}}') | Out-Null
    if ((Run 'docker' @('image', 'inspect', '--format', '{{.Id}} {{json .RepoDigests}}', $Base)) -ne 0) {
        Say "base image $Base is not present locally"
        return 10
    }
    foreach ($b in $Builds) {
        Say "build $($b.Tag) at GEOS $($b.Commit)"
        $rc = Run 'docker' @('build', '--progress=plain', '-t', $b.Tag,
            '--build-arg', "GEOS_COMMIT=$($b.Commit)", '--build-arg', "JOBS=$Jobs",
            '--build-arg', "BASE_IMAGE=$Base", $Context)
        if ($rc -ne 0) { return $b.Fail }
        Run 'docker' @('image', 'inspect', '--format',
            '{{.Id}} {{.Created}} {{json .Config.Labels}}', $b.Tag) | Out-Null
    }
    if ($BuildOnly) { Say 'build only: stop before the replay'; return 0 }
    Say 'replay'
    Push-Location $Root
    try {
        return (Run $Py @('-s', '-m', 'tavs.replay_fixes'))
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
    Say "E6 end; exit code $code"
    Set-Content -Path $Done -Value "$code" -Encoding ascii -NoNewline
}
exit $code
