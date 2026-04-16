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
$env:PLCVERIF_CLI_DIR = "/workspace/validation/tools/plcverif/cli"

$workspaceRoot = if ($env:WORKSPACE_ROOT) { $env:WORKSPACE_ROOT } else { "/workspace" }
$projectPath = if ($env:VALIDATOR_PROJECT) { $env:VALIDATOR_PROJECT } else { "/workspace/projects/FB_MainSequence" }
$configPath = "/tmp/toolchain.validator.json"

$config = [ordered]@{
    py39 = "/usr/bin/python3"
    plcrex_entry = "/usr/bin/python3"
    plcrex_cli_script = "/workspace/container/plcrex-entry.py"
    iec_checker_exe = "/opt/iec-checker/iec_checker"
    plcverif_entry = "/workspace/container/plcverif-entry.sh"
    plcverif_cli_dir = "/workspace/validation/tools/plcverif/cli"
    plcverif_tools_dir = "/workspace/validation/tools/plcverif/tools"
    plcverif_demo_project_dir = "/workspace/validation/tools/plcverif/tools/workspace/DemoProject"
    plcverif_backend_binary = "/opt/nuxmv/bin/nuXmv"
}

$config | ConvertTo-Json -Depth 10 | Set-Content -Path $configPath -Encoding UTF8

& /workspace/validation/scripts/run-static-gate.ps1 `
    -ProjectPath $projectPath `
    -WorkspaceRoot $workspaceRoot `
    -ConfigPath $configPath

& /workspace/validation/scripts/run-modelcheck-gate.ps1 `
    -ProjectPath $projectPath `
    -WorkspaceRoot $workspaceRoot `
    -ConfigPath $configPath
