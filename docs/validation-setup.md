# PLC Workspace Validation Layer

For PLC semantics and current work, start with [PROJECT.md](../PROJECT.md),
[the scan contract](../projects/FB_MainSequence/01_specs/scan-contract.md), and
[semantic verification](../validation/tests/README.md). The v0.3 continuous-enable contract is implemented; passing a legacy gate or generating a TIA payload is not final acceptance.

This repository publishes the containerized validation layer for a Siemens PLC
workspace. It does not containerize TIA Portal, PLCSIM, or Siemens GUI tools.

The containerized layer runs:

- static checks with PLCreX and iec-checker
- model checking with PLCverif CLI and native Linux nuXmv
- OpenPLC smoke tests driven by `projects/*/03_checks/test_vectors`

TIA Portal and PLCSIM stay on the Windows host. Final Siemens evidence remains
host-owned and must be stored under `projects/*/04_reports/tia_final`.

## Repository vs Runtime Assets

The public git repository contains the reusable harness, the versioned
FB_MainSequence abstract core, semantic tests and generated checker/export
projections. Compact verification records are in
[docs/verification/plc-semantics-v0.3](verification/plc-semantics-v0.3).

Large or project-specific runtime assets are shipped separately as a GitHub
Release asset named `runtime-assets.zip`.

The release asset is expected to provide:

- `validation/tools/plcverif/`
- `validation/tools/OpenPLC_v3/`
- historical project payloads (do not overwrite the versioned core)
- additional historical harness documentation
- `PLC素材库/`
- selected validation config and template files

Extract old runtime archives outside the checkout. Copy only external validation
payloads; never overwrite the versioned project or its documentation with an old
archive. Run the semantic checks in `validation/tests/README.md` for this core.

Generated reports, logs, Eclipse workspaces, Python caches, and historical
outputs are excluded from that zip.

## Windows Quick Start

Prerequisites:

- Docker Desktop
- PowerShell 7+
- Git

Setup:

```powershell
git clone https://github.com/qiaoqiao2521/plc-workspace.git
cd plc-workspace

# Download runtime-assets.zip from the GitHub Release page, then:
Expand-Archive .\runtime-assets.zip -DestinationPath ..\plc-runtime-assets -Force
foreach ($folder in @("tools", "config", "docker", "templates")) {
    Copy-Item "..\plc-runtime-assets\validation\$folder" .\validation\ -Recurse -Force
}
```

Run validation:

```powershell
docker compose -f .\container\docker-compose.release.yml build validator openplc
docker compose -f .\container\docker-compose.release.yml run --rm validator
docker compose -f .\container\docker-compose.release.yml up --abort-on-container-exit --exit-code-from smoke openplc smoke
```

If Docker build needs an explicit proxy:

```powershell
$env:PLC_HTTP_PROXY = 'http://host.docker.internal:3067'
$env:PLC_HTTPS_PROXY = 'http://host.docker.internal:3067'
$env:PLC_ALL_PROXY = 'http://host.docker.internal:3067'
docker compose -f .\container\docker-compose.release.yml build validator openplc
```

## Linux Server Quick Start

Prerequisites:

- Docker Engine with Compose plugin
- Git
- unzip

Setup:

```bash
git clone https://github.com/qiaoqiao2521/plc-workspace.git
cd plc-workspace
unzip runtime-assets.zip -d ../plc-runtime-assets
cp -a ../plc-runtime-assets/validation/{tools,config,docker,templates} validation/
```

Run validation:

```bash
docker compose -f container/docker-compose.release.yml build validator openplc

VALIDATOR_PROJECT=/workspace/projects/FB_MainSequence \
  docker compose -f container/docker-compose.release.yml run --rm validator

SMOKE_PROJECT=/workspace/projects/FB_MainSequence \
  docker compose -f container/docker-compose.release.yml up --abort-on-container-exit --exit-code-from smoke openplc smoke
```

If the server requires a proxy, export Docker build proxy variables first:

```bash
export PLC_HTTP_PROXY=http://proxy.example:3128
export PLC_HTTPS_PROXY=http://proxy.example:3128
export PLC_ALL_PROXY=http://proxy.example:3128
docker compose -f container/docker-compose.release.yml build validator openplc
```

## Outputs

Reports are written back to the bind-mounted workspace:

- `projects/<project>/04_reports/static`
- `projects/<project>/04_reports/modelcheck`
- `projects/<project>/04_reports/smoke`

Smoke inputs remain:

- `projects/<project>/03_checks/test_vectors/*.yaml`

## Siemens Boundary

The validation container can produce harness-level evidence only. It must not
claim TIA final success.

The host remains responsible for:

- TIA Portal import and compile
- PLCSIM or PLCSIM Advanced execution
- Siemens-native watch table or final runtime evidence
- final evidence under `projects/*/04_reports/tia_final`

See `contracts/container-boundary.md` for the full boundary contract.

## Publishing Runtime Assets

Maintainers can build a release asset from a prepared workspace:

```powershell
pwsh .\scripts\export-runtime-assets.ps1 -Project FB_MainSequence
```

See `ops/publishing.md` for the full release workflow.
