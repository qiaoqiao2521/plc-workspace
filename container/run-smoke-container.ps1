$ErrorActionPreference = "Stop"

$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:all_proxy = ""
$env:LC_ALL = "C.UTF-8"
$env:LANG = "C.UTF-8"
$env:NO_PROXY = "localhost,127.0.0.1,openplc"
$env:no_proxy = "localhost,127.0.0.1,openplc"

$workspaceRoot = if ($env:WORKSPACE_ROOT) { $env:WORKSPACE_ROOT } else { "/workspace" }
$projectPath = if ($env:SMOKE_PROJECT) { $env:SMOKE_PROJECT } else { "/workspace/projects/FB_MainSequence" }
$configPath = "/tmp/toolchain.smoke.json"

$config = [ordered]@{
    py39 = "/usr/bin/python3"
    openplc_mode = "external"
    openplc_image_tag = "plc-workspace-openplc:v3-smoke"
    openplc_http_host = "openplc"
    openplc_http_port = 8080
    openplc_https_host = "openplc"
    openplc_https_port = 8443
    openplc_modbus_host = "openplc"
    openplc_modbus_port = 502
}

$config | ConvertTo-Json -Depth 10 | Set-Content -Path $configPath -Encoding UTF8

& /workspace/validation/scripts/run-smoke-gate.ps1 `
    -ProjectPath $projectPath `
    -WorkspaceRoot $workspaceRoot `
    -ConfigPath $configPath
