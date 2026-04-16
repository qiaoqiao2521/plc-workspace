# PLC Workspace Validation Layer

This repository publishes the containerized validation layer for a Siemens PLC
workspace. It does not containerize TIA Portal, PLCSIM, or Siemens GUI tools.

The containerized layer runs:

- static checks with PLCreX and iec-checker
- model checking with PLCverif CLI and native Linux nuXmv
- OpenPLC smoke tests driven by `projects/*/03_checks/test_vectors`

TIA Portal and PLCSIM stay on the Windows host. Final Siemens evidence remains
host-owned and must be stored under `projects/*/04_reports/tia_final`.

## Repository vs Runtime Assets

The public git repository intentionally contains only the reusable harness
logic, container definitions, and documentation.

Large or project-specific runtime assets are shipped separately as a GitHub
Release asset named `runtime-assets.zip`.

The release asset is expected to provide:

- `validation/tools/plcverif/`
- `validation/tools/OpenPLC_v3/`
- `projects/FB_MainSequence/`
- `docs/harness/`
- `PLC素材库/`
- selected validation config and template files

Generated reports, logs, Eclipse workspaces, Python caches, and historical
outputs are excluded from that zip.

## Windows Quick Start

Prerequisites:

- Docker Desktop
- PowerShell 7+
- Git

Setup:

```powershell
git clone https://github.com/muqiao215/plc-workspace.git
cd plc-workspace

# Download runtime-assets.zip from the GitHub Release page, then:
Expand-Archive .\runtime-assets.zip -DestinationPath . -Force
```

Run validation:

```powershell
pwsh .\container\run-validator.ps1 -Project FB_MainSequence -Build
pwsh .\container\run-smoke.ps1 -Project FB_MainSequence
```

If Docker build needs an explicit proxy:

```powershell
pwsh .\container\run-validator.ps1 -Project FB_MainSequence -Build -ProxyUrl http://host.docker.internal:3067
pwsh .\container\run-smoke.ps1 -Project FB_MainSequence -ProxyUrl http://host.docker.internal:3067
```

## Linux Server Quick Start

Prerequisites:

- Docker Engine with Compose plugin
- Git
- unzip

Setup:

```bash
git clone https://github.com/muqiao215/plc-workspace.git
cd plc-workspace
unzip runtime-assets.zip -d .
```

Run validation:

```bash
docker compose -f container/docker-compose.yml build validator

VALIDATOR_PROJECT=/workspace/projects/FB_MainSequence \
  docker compose -f container/docker-compose.yml run --rm validator

SMOKE_PROJECT=/workspace/projects/FB_MainSequence \
  docker compose -f container/docker-compose.yml up --build --abort-on-container-exit --exit-code-from smoke openplc smoke
```

If the server requires a proxy, export Docker build proxy variables first:

```bash
export PLC_HTTP_PROXY=http://proxy.example:3128
export PLC_HTTPS_PROXY=http://proxy.example:3128
export PLC_ALL_PROXY=http://proxy.example:3128
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

See `docs/contracts/container-boundary.md` for the full boundary contract.

## Publishing Runtime Assets

Maintainers can build a release asset from a prepared workspace:

```powershell
pwsh .\scripts\export-runtime-assets.ps1 -Project FB_MainSequence
```

See `docs/ops/publishing.md` for the full release workflow.
