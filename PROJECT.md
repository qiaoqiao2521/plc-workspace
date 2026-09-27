# PLC Workspace

## Why

Preserve and verify PLC sequencing logic across tooling and agent sessions. The core challenge is cyclic execution, persistent state, timing and process semantics; ordinary code plausibility is insufficient.

## User Intent

The user has invested substantially in this industrial-automation workspace. Priority as of 2026-09-22: converge PLC logic first, then fix the Siemens/Windows and Linux tooling environment. Python should support verification and engineering work without obscuring PLC scan semantics.

## Non-goals

No replacement of TIA/PLCSIM with container evidence. No remote/device writes or deployment as part of semantic convergence. No platform migration or broad rewrite.

## Success

One explicit scan contract, one canonical implementation, generated/checkable projections, executable boundary scenarios and honestly scoped proof. Another agent can recover this from a few entry files.

## Constraints

- Existing Main=LAD, FB=SCL and semantic I/O separation remain.
- Current example is an abstraction of 303翻转; the real machine's Main, child FBs and I/O are absent.
- Normal flow remains 0→1→2→3→1.
- TIA/PLCSIM and CPU/firmware versions are not yet pinned; no Siemens final evidence exists.
- Project assets were historically shipped outside Git. Existing assets and pre-existing staged execution-mode changes must be preserved.

## Current State

The v0.3 abstract scan contract and interface 0.2.0 are implemented: internal state/output separation, continuous enable, edge-consumed commands, distinct current error and timeout history. Twenty-seven compiled-ST tests include 160 control combinations and 5,000 differential calls; fourteen tooling tests pass. The 32-assertion conjunction passes with a full UINT timeout input. The complete OpenPLC test program passes natively after 50 calls, without running its service. Source-bound current evidence is in `projects/FB_MainSequence/04_reports/semantics/v0.3/`. Compact published verification records are in `docs/verification/plc-semantics-v0.3/`. Old v0.2 proof is historical. No Siemens/machine acceptance or full PLCopen conformance is claimed.

## Current Priority

The requested abstract-core implementation is complete. Preserve the contract and source-bound evidence; further machine integration needs the actual Main/child FBs, safety interface, TIA/CPU versions and retention configuration. Do not reopen the superseded policy questionnaire or treat generated TIA files as a successful import.
## Knowledge Map

- `AGENTS.md`: startup protocol.
- `docs/ARCHITECTURE.md`: source, adapters and evidence map.
- `docs/DECISIONS.md`: durable choices and scoped implementation decisions.
- `docs/SCL_STANDARD_BASELINE.md`: official references, corrections to earlier advice, and implementation gaps.
- `projects/FB_MainSequence/01_specs/scan-contract.md`: authoritative implemented abstract-core semantics and migration rules.
- `plans/plc-semantics-v1/`: current task state.
- `validation/tests/README.md`: offline verification commands and limits.
