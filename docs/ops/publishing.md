# Publishing Guide

This guide describes how to publish the validation-layer repository so another
machine can run the same harness without receiving generated reports or local
history.

## What Gets Published

The public git repository contains:

- container definitions and wrappers
- validation scripts
- contracts and operations documentation
- runtime asset export tooling
- the versioned FB_MainSequence abstract core, semantic tests and generated projections
- compact source-bound verification records under docs/verification/

The GitHub Release asset `runtime-assets.zip` contains runtime payloads that are
needed to execute the harness but are intentionally not committed to git:

- `validation/tools/plcverif/`
- `validation/tools/OpenPLC_v3/`
- selected project assets under `projects/<project>/`
- `docs/harness/`
- `PLC素材库/`
- selected validation config and template files

## What Must Not Be In The Asset

The export script excludes:

- `.git/`
- `.claude/`
- `workspace/`
- `以往项目/`
- `validation/.venv39/`
- `validation/config/toolchain.local.json`
- `projects/*/04_reports/`
- `projects/*/03_checks/plcrex/PLCreX_outputs/`
- `projects/*/03_checks/iec-checker/*.log`
- `projects/*/03_checks/plcverif/output/`
- `projects/*/03_checks/plcverif/workspace/`
- `projects/*/03_checks/plcverif/plcverif.log`
- `*.log`
- `*.zip`, `*.7z`, `*.rar`, `*.tar`, `*.tar.gz`
- Python caches and bytecode

This keeps generated evidence and local tool state out of the release.

## Build The Runtime Asset

From the workspace root:

```powershell
pwsh .\scripts\export-runtime-assets.ps1 -Project FB_MainSequence
```

Default output:

```text
releases/runtime-assets.zip
releases/runtime-assets.manifest.json
```

Old archives can contain an obsolete copy of the versioned project. Extract
outside the checkout and copy only external validation payloads:

```powershell
git clone https://github.com/muqiao215/plc-workspace.git
cd plc-workspace
Expand-Archive .\runtime-assets.zip -DestinationPath ..\plc-runtime-assets -Force
foreach ($folder in @("tools", "config", "docker", "templates")) {
    Copy-Item "..\plc-runtime-assets\validation\$folder" .\validation\ -Recurse -Force
}
```

## Create A GitHub Release

Recommended tag for the containerized harness layer:

```powershell
$tag = "validation-layer-v0.1.0"

gh release create $tag `
  .\releases\runtime-assets.zip `
  .\releases\runtime-assets.manifest.json `
  --repo muqiao215/plc-workspace `
  --title "Validation layer v0.1.0" `
  --notes "Containerized harness layer release. TIA Portal and PLCSIM remain host-side final verification tools."
```

Use a new tag for each released asset set. Do not reuse tags unless you delete
the existing release intentionally.

## Validate A Fresh Clone

Windows:

```powershell
git clone https://github.com/muqiao215/plc-workspace.git fresh-plc-workspace
cd fresh-plc-workspace
Expand-Archive ..\runtime-assets.zip -DestinationPath ..\plc-runtime-assets -Force
foreach ($folder in @("tools", "config", "docker", "templates")) {
    Copy-Item "..\plc-runtime-assets\validation\$folder" .\validation\ -Recurse -Force
}
docker compose -f .\container\docker-compose.release.yml build validator openplc
docker compose -f .\container\docker-compose.release.yml run --rm validator
docker compose -f .\container\docker-compose.release.yml up --abort-on-container-exit --exit-code-from smoke openplc smoke
```

Linux:

```bash
git clone https://github.com/muqiao215/plc-workspace.git fresh-plc-workspace
cd fresh-plc-workspace
unzip ../runtime-assets.zip -d ../plc-runtime-assets
cp -a ../plc-runtime-assets/validation/{tools,config,docker,templates} validation/
docker compose -f container/docker-compose.release.yml build validator openplc
VALIDATOR_PROJECT=/workspace/projects/FB_MainSequence docker compose -f container/docker-compose.release.yml run --rm validator
SMOKE_PROJECT=/workspace/projects/FB_MainSequence docker compose -f container/docker-compose.release.yml up --abort-on-container-exit --exit-code-from smoke openplc smoke
```

## Boundary Reminder

The release proves the reusable harness layer can run. It does not prove a
Siemens final result.

The following remain host responsibilities:

- TIA Portal compile and import
- PLCSIM execution
- Siemens final report under `projects/*/04_reports/tia_final`
