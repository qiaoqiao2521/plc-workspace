# Containerized Validation Layer

## Scope

This directory only containerizes the reusable validation layer. It does not try to containerize Siemens GUI tooling.

Containerized:

- `PLC素材库/` read access
- `docs/harness/` read access
- `validation/scripts/` execution
- `PLCreX`
- `iec-checker`
- `PLCverif CLI`
- `OpenPLC` smoke runtime
- `projects/*` source, projection, reports, traceability-style outputs

Host-only:

- `TIA Portal`
- `PLCSIM / PLCSIM Advanced`
- Siemens license-bound GUI tools
- final `TIA / PLCSIM` evidence under `04_reports/tia_final/`

## Recommended Architecture

```text
宿主机 Windows
├─ TIA Portal / PLCSIM / Siemens license tools
├─ E:\web\plc-workspace
│  ├─ projects/*/02_src/st
│  ├─ projects/*/03_checks
│  ├─ projects/*/04_reports
│  ├─ projects/*/05_tia_sync   <== 容器世界与 TIA 世界交换边界
│  ├─ docs/harness
│  └─ PLC素材库
└─ Docker Desktop
   ├─ validator container
   │  ├─ runs static gate
   │  └─ runs modelcheck gate
   ├─ smoke container
   │  └─ runs run-smoke-gate.ps1 against compose sidecar
   └─ openplc sidecar
      └─ receives projected ST and exposes runtime API + Modbus
```

## Boundary Directories

Mounted read/write into validator and smoke containers:

- `projects/*/02_src`
- `projects/*/03_checks`
- `projects/*/04_reports`
- `projects/*/05_tia_sync`
- `releases/`

Mounted read-only by convention, but still part of the workspace bind mount:

- `docs/harness`
- `docs/contracts`
- `PLC素材库`

Operational boundary:

- `projects/*/05_tia_sync` is the handoff package from container validation into host-side TIA/PLCSIM.
- `projects/*/04_reports/tia_final` remains host-owned evidence. Containers must not claim Siemens final success.

## Why Two Dockerfiles

Two Dockerfiles are kept intentionally:

1. `validator.Dockerfile`
   - tiny build context: only `container/`
   - contains PowerShell, Python, Java, native Linux `iec-checker` and native Linux `nuXmv`
   - executes `run-static-gate.ps1` and `run-modelcheck-gate.ps1`
2. `openplc-smoke.Dockerfile`
   - build context is only `validation/tools/OpenPLC_v3`
   - isolates the heavier OpenPLC runtime image build from the validator image

Merging them would either bloat the validator image or force the whole workspace into the OpenPLC build context.

## Commands

Validator:

```powershell
pwsh .\container\run-validator.ps1 -Project FB_MainSequence
```

Smoke:

```powershell
pwsh .\container\run-smoke.ps1 -Project FB_MainSequence
```

If Docker build needs an explicit proxy, pass it directly:

```powershell
pwsh .\container\run-validator.ps1 -Project FB_MainSequence -ProxyUrl http://host.docker.internal:3067
pwsh .\container\run-smoke.ps1 -Project FB_MainSequence -ProxyUrl http://host.docker.internal:3067
```

The host wrappers also auto-detect a local listener on `127.0.0.1:3067` and map it into Docker as `host.docker.internal:3067`.

Both commands keep outputs in the host workspace:

- `projects/<project>/04_reports/static`
- `projects/<project>/04_reports/modelcheck`
- `projects/<project>/04_reports/smoke`

`test_vectors` remains the real smoke input because `run-smoke-gate.ps1` still reads `projects/*/03_checks/test_vectors/*.yaml`.

## Build Context Strategy

Validator build context:

- context: `container/`
- avoids sending the workspace, reports, releases, and vendor tools into the image build

OpenPLC build context:

- context: `validation/tools/OpenPLC_v3`
- built explicitly by `run-smoke.ps1`

Large directories intentionally kept out of validator build context:

- `validation/.venv39` about `0.18 GB`
- `validation/tools/plcverif` about `0.14 GB`
- `validation/tools/OpenPLC_v3` about `0.07 GB`
- `workspace/` Eclipse metadata
- `以往项目/` historical assets

Additional downloads performed inside the validator image:

- `iec-checker` Linux release asset from the upstream GitHub release
- `nuXmv` Linux x86_64 tarball from the upstream FBK download page

This keeps the Docker build context small while avoiding vendoring large binary archives into the repo.

## Notes

- `PLCverif` is launched from the mounted workspace via JVM, not by copying the vendor bundle into the image.
- `iec-checker` now uses the upstream Linux x86_64 binary in the validator image. This avoids the previous Wine failure mode while keeping the report truthful about parser or rule-check failures.
- `PLCverif` still comes from the mounted workspace, but its backend now points to the upstream Linux `nuXmv` binary in the validator image. The failing Windows `nuXmv.exe` under Wine is no longer the default path.
- `nuXmv` is not redistributed in the git repo. It is fetched during image build because its licensing model is different from the LGPL `NuSMV` lineage and should stay an explicit upstream dependency.
- `PLCreX` is invoked through `container/plcrex-entry.py` so its Linux package can run with the current Windows-authored resource paths.
- `release-manifest.yaml` keeps referencing the newest reports because reports are still written in place under `04_reports`.
