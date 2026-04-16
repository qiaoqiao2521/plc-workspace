param(
    [string]$Project = "FB_MainSequence",
    [switch]$Build,
    [string]$ProxyUrl = ""
)

$ErrorActionPreference = "Stop"

$containerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $containerDir
$composeFile = Join-Path $containerDir "docker-compose.yml"
$projectDir = Join-Path (Join-Path $workspaceRoot "projects") $Project
$openplcContext = Join-Path $workspaceRoot "validation\tools\OpenPLC_v3"
$openplcDockerfile = Join-Path $containerDir "openplc-smoke.Dockerfile"

if (-not (Test-Path -LiteralPath $projectDir)) {
    throw "project not found: $projectDir"
}

if (-not (Test-Path -LiteralPath $openplcContext)) {
    throw "OpenPLC build context missing: $openplcContext"
}

$resolvedProxyUrl = $ProxyUrl
if (-not $resolvedProxyUrl -and (Test-NetConnection 127.0.0.1 -Port 3067 -WarningAction SilentlyContinue).TcpTestSucceeded) {
    $resolvedProxyUrl = "http://host.docker.internal:3067"
}

$env:SMOKE_PROJECT = "/workspace/projects/$Project"
if ($resolvedProxyUrl) {
    $env:PLC_HTTP_PROXY = $resolvedProxyUrl
    $env:PLC_HTTPS_PROXY = $resolvedProxyUrl
    $env:PLC_ALL_PROXY = $resolvedProxyUrl
    $env:PLC_http_proxy = $resolvedProxyUrl
    $env:PLC_https_proxy = $resolvedProxyUrl
    $env:PLC_all_proxy = $resolvedProxyUrl
}

try {
    & docker image inspect plc-workspace-openplc:v3-smoke *> $null
    $imageMissing = $LASTEXITCODE -ne 0
    if ($Build -or $imageMissing) {
        $buildArgs = @()
        if ($resolvedProxyUrl) {
            $buildArgs += @(
                "--build-arg", "HTTP_PROXY=$resolvedProxyUrl",
                "--build-arg", "HTTPS_PROXY=$resolvedProxyUrl",
                "--build-arg", "ALL_PROXY=$resolvedProxyUrl",
                "--build-arg", "http_proxy=$resolvedProxyUrl",
                "--build-arg", "https_proxy=$resolvedProxyUrl",
                "--build-arg", "all_proxy=$resolvedProxyUrl"
            )
        }
        & docker build @buildArgs -f $openplcDockerfile -t plc-workspace-openplc:v3-smoke $openplcContext
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    & docker compose -f $composeFile up --build --abort-on-container-exit --exit-code-from smoke openplc smoke
    $exitCode = $LASTEXITCODE
}
finally {
    & docker compose -f $composeFile down --remove-orphans | Out-Null
    Remove-Item Env:SMOKE_PROJECT -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_HTTP_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_ALL_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_http_proxy -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_https_proxy -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_all_proxy -ErrorAction SilentlyContinue
}

exit $exitCode
