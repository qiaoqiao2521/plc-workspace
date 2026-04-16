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

if (-not (Test-Path -LiteralPath $projectDir)) {
    throw "project not found: $projectDir"
}

$resolvedProxyUrl = $ProxyUrl
if (-not $resolvedProxyUrl -and (Test-NetConnection 127.0.0.1 -Port 3067 -WarningAction SilentlyContinue).TcpTestSucceeded) {
    $resolvedProxyUrl = "http://host.docker.internal:3067"
}

$env:VALIDATOR_PROJECT = "/workspace/projects/$Project"
if ($resolvedProxyUrl) {
    $env:PLC_HTTP_PROXY = $resolvedProxyUrl
    $env:PLC_HTTPS_PROXY = $resolvedProxyUrl
    $env:PLC_ALL_PROXY = $resolvedProxyUrl
    $env:PLC_http_proxy = $resolvedProxyUrl
    $env:PLC_https_proxy = $resolvedProxyUrl
    $env:PLC_all_proxy = $resolvedProxyUrl
}

try {
    $args = @("compose", "-f", $composeFile, "run", "--rm")
    if ($Build) {
        $args += "--build"
    }
    $args += "validator"

    & docker @args
    exit $LASTEXITCODE
}
finally {
    Remove-Item Env:VALIDATOR_PROJECT -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_HTTP_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_ALL_PROXY -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_http_proxy -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_https_proxy -ErrorAction SilentlyContinue
    Remove-Item Env:PLC_all_proxy -ErrorAction SilentlyContinue
}
