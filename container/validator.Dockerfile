FROM mcr.microsoft.com/powershell:7.4-debian-bookworm

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ARG ALL_PROXY=
ARG http_proxy=
ARG https_proxy=
ARG all_proxy=
ARG PLCREX_VERSION=2.0.0
ARG PYMODBUS_VERSION=2.5.3
ARG PYYAML_VERSION=6.0.3

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WINEDEBUG=-all \
    WINEPREFIX=/root/.wine

RUN if [ -n "${HTTP_PROXY}" ]; then \
        printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' "${HTTP_PROXY}" "${HTTPS_PROXY:-${HTTP_PROXY}}" >/etc/apt/apt.conf.d/99proxy; \
    else \
        printf 'Acquire::http::Proxy "false";\nAcquire::https::Proxy "false";\n' >/etc/apt/apt.conf.d/99proxy; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        openjdk-17-jre-headless \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        wine \
        wine-binfmt \
        wine64 \
        wine64-tools \
    && python3 -m pip install --no-cache-dir --break-system-packages \
        "plcrex==${PLCREX_VERSION}" \
        "pymodbus==${PYMODBUS_VERSION}" \
        "PyYAML==${PYYAML_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

RUN cat <<'EOF' >/usr/local/bin/ensure-wine-prefix
#!/usr/bin/env bash
set -euo pipefail
if [ ! -f "${WINEPREFIX:-/root/.wine}/system.reg" ]; then
  wineboot --init >/tmp/wineboot.log 2>&1 || true
fi
EOF

RUN cat <<'EOF' >/usr/local/bin/iec-checker-wrapper
#!/usr/bin/env bash
set -euo pipefail
/usr/local/bin/ensure-wine-prefix
target="${IEC_CHECKER_WINDOWS_EXE:-/workspace/validation/tools/iec-checker/iec_checker_Windows_x86_64.exe}"
exec /usr/lib/wine/wine64 "$target" "$@"
EOF

RUN cat <<'EOF' >/usr/local/bin/nuxmv-wrapper
#!/usr/bin/env bash
set -euo pipefail
/usr/local/bin/ensure-wine-prefix
target="${PLCVERIF_NUXMV_EXE:-/workspace/validation/tools/plcverif/tools/tools/nuxmv/nuXmv.exe}"
exec /usr/lib/wine/wine64 "$target" "$@"
EOF

RUN cat <<'EOF' >/usr/local/bin/plcverif-entry
#!/usr/bin/env bash
set -euo pipefail
cli_dir="${PLCVERIF_CLI_DIR:-/workspace/validation/tools/plcverif/cli}"
launcher="${cli_dir}/plugins/org.eclipse.equinox.launcher_1.4.0.v20161219-1356.jar"
exec java -jar "$launcher" "$@"
EOF

RUN cat <<'EOF' >/usr/local/bin/plcrex-entry.py
#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path

from plcrex.tools.stp.st_parser import STParser


def run_st_parser(source: Path, export: Path, txt: bool = True, dot: bool = True, beckhoff: bool = False) -> int:
    out_dir = export.parent / "PLCreX_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    STParser(source, out_dir, export.stem, txt, dot, beckhoff).translate()
    print(f"Wrote parser outputs to {out_dir}")
    return 0


def run_iec_check(source: Path, exe: Path, export: Path, verbose: bool = False, help_flag: bool = False) -> int:
    out_dir = export.parent / "PLCreX_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"{export.stem}.log"
    option = "--help" if help_flag else "--verbose" if verbose else "--quiet"
    with open(log_path, "w", encoding="utf-8") as stream:
        completed = subprocess.run([str(exe), str(source), option], stdout=stream, stderr=subprocess.STDOUT, check=False)
    print(log_path.read_text(encoding="utf-8", errors="replace"))
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["st-parser", "iec-check"])
    parser.add_argument("args", nargs="+")
    ns = parser.parse_args()

    if ns.command == "st-parser":
        if len(ns.args) != 2:
            raise SystemExit("st-parser requires: <source> <export>")
        return run_st_parser(Path(ns.args[0]), Path(ns.args[1]))

    if len(ns.args) != 3:
        raise SystemExit("iec-check requires: <source> <exe> <export>")
    return run_iec_check(Path(ns.args[0]), Path(ns.args[1]), Path(ns.args[2]))


if __name__ == "__main__":
    sys.exit(main())
EOF

RUN cat <<'EOF' >/usr/local/bin/run-validator-container.ps1
$ErrorActionPreference = "Stop"

$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:all_proxy = ""
$env:NO_PROXY = "localhost,127.0.0.1,openplc"
$env:no_proxy = "localhost,127.0.0.1,openplc"

$workspaceRoot = if ($env:WORKSPACE_ROOT) { $env:WORKSPACE_ROOT } else { "/workspace" }
$projectPath = if ($env:VALIDATOR_PROJECT) { $env:VALIDATOR_PROJECT } else { "/workspace/projects/FB_MainSequence" }
$configPath = "/tmp/toolchain.validator.json"

$config = [ordered]@{
    py39 = "/usr/bin/python3"
    plcrex_entry = "/usr/bin/python3"
    plcrex_cli_script = "/usr/local/bin/plcrex-entry.py"
    iec_checker_exe = "/usr/local/bin/iec-checker-wrapper"
    plcverif_entry = "/usr/local/bin/plcverif-entry"
    plcverif_cli_dir = "/workspace/validation/tools/plcverif/cli"
    plcverif_tools_dir = "/workspace/validation/tools/plcverif/tools"
    plcverif_demo_project_dir = "/workspace/validation/tools/plcverif/tools/workspace/DemoProject"
    plcverif_backend_binary = "/usr/local/bin/nuxmv-wrapper"
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
EOF

RUN cat <<'EOF' >/usr/local/bin/run-smoke-container.ps1
$ErrorActionPreference = "Stop"

$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:all_proxy = ""
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
EOF

RUN chmod +x \
    /usr/local/bin/ensure-wine-prefix \
    /usr/local/bin/iec-checker-wrapper \
    /usr/local/bin/nuxmv-wrapper \
    /usr/local/bin/plcverif-entry \
    /usr/local/bin/plcrex-entry.py

WORKDIR /workspace
