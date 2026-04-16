# Container Boundary Contract

## Purpose

Define the validation-layer container boundary for `E:\web\plc-workspace` without changing the Siemens-side delivery flow.

The container goal is reuse of the harness layer:

`static -> modelcheck -> smoke`

The container goal is not replacement of:

`TIA Portal -> PLCSIM -> Siemens final evidence`

## Responsibility Split

### Container responsibilities

The containerized layer is responsible for:

- reading `PLC素材库/`
- reading `docs/harness/`
- executing `validation/scripts/run-static-gate.ps1`
- executing `validation/scripts/run-modelcheck-gate.ps1`
- executing `validation/scripts/run-smoke-gate.ps1`
- running `PLCreX`
- running `iec-checker`
- running `PLCverif CLI`
- running `OpenPLC` smoke
- reading and writing `projects/*/02_src`
- reading and writing `projects/*/03_checks`
- reading and writing `projects/*/04_reports`
- preparing and reading `projects/*/05_tia_sync`

### Host responsibilities

The host remains responsible for:

- opening and editing the actual TIA project
- importing `05_tia_sync/exported_scl`
- compilation inside TIA
- runtime checks inside `PLCSIM / PLCSIM Advanced`
- watch tables, online monitoring, download, and Siemens-specific diagnostics
- writing final Siemens evidence into `04_reports/tia_final`
- deciding whether a release can move beyond `blocked_missing_tia_final`

## Boundary Directories

### Shared bind-mounted directories

These directories are intentionally shared between host and containers:

- `projects/*/02_src`
- `projects/*/03_checks`
- `projects/*/04_reports`
- `projects/*/05_tia_sync`
- `releases/`
- `docs/harness`
- `docs/contracts`
- `PLC素材库`

### Exchange boundary

`projects/*/05_tia_sync` is the formal exchange boundary between the container world and the TIA world.

Rules:

1. Container validation may prepare, inspect, and document the `05_tia_sync` payload.
2. Host-side TIA work consumes that payload.
3. Any manual Siemens-side behavior change must be reflected back into `02_src/st` before the next validation run.
4. `05_tia_sync` is packaging and traceability, not a second source-of-truth tree.

## Why TIA / PLCSIM Stay Outside Containers

`TIA Portal` and `PLCSIM` do not go into containers because:

1. They are Windows GUI tools with Siemens licensing and installation requirements.
2. They depend on host integration patterns that are not reliable in Dockerized Linux validation runners.
3. Their value is final Siemens-native execution evidence, not generic headless reuse.
4. Trying to containerize them would blur the audit boundary between harness-level confidence and Siemens final proof.

So the contract is explicit:

- containers can prove harness-level validity
- only the host can prove Siemens final validity

## Report and Release Rules

The following outputs must remain host-visible and in-place:

- `projects/*/04_reports/static/*`
- `projects/*/04_reports/modelcheck/*`
- `projects/*/04_reports/smoke/*`
- `projects/*/04_reports/tia_final/*`
- `projects/*/03_checks/test_vectors/*`
- `releases/*/release-manifest.yaml`

This keeps:

1. `test_vectors` as the real smoke input
2. `04_reports` as the single report sink
3. `release-manifest.yaml` able to reference the newest reports without post-copy sync

Container reports must keep tool failures explicit. A Wine failure from a Windows-only validation binary is evidence for remediation, not a substitute for a successful static/modelcheck result.

## Non-Goals

This container boundary does not:

- replace Siemens final verification
- claim TIA final success from OpenPLC smoke
- move the full TIA project into Docker
- rewrite project logic just to make the container story cleaner
