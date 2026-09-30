# PLC Workspace

## Why

Turn human process requirements or flow language into reviewable PLC engineering: clarify state/I/O/constraints, use AI to generate Main LAD and FB SCL, then validate and prepare engineering outputs. Cyclic execution, persistent state and timing constrain the generator; verification protects its quality.

## User Intent

The user has invested substantially in this industrial-automation workspace. On 2026-10-01 the user corrected the product direction: human requirements/flow language → AI-generated LAD/SCL is the main purpose. The earlier semantic-convergence work is the supporting Agent quality layer. The frontend connects local agy first; a public website can use a cloud generation service later. Python supports engineering without obscuring PLC scan semantics.

## Non-goals

No replacement of TIA/PLCSIM with container evidence. No remote/device writes or deployment as part of semantic convergence. No platform migration or broad rewrite.

## Success

A user can describe a process, review state and I/O specifications, generate and export SCL/LAD drafts, then verify that particular engineering output. Generated code never inherits another example’s proof. Another agent can recover the product intent and scan contract from a few entry files.

## Constraints

- Existing Main=LAD, FB=SCL and semantic I/O separation remain.
- Current example is an abstraction of 303翻转; the real machine's Main, child FBs and I/O are absent.
- Normal flow remains 0→1→2→3→1.
- TIA/PLCSIM and CPU/firmware versions are not yet pinned; no Siemens final evidence exists.
- Project assets were historically shipped outside Git. Existing assets and pre-existing staged execution-mode changes must be preserved.

## Current State

The v0.3 abstract scan contract and interface 0.2.0 are implemented: internal state/output separation, continuous enable, edge-consumed commands, distinct current error and timeout history. Twenty-seven compiled-ST tests include 160 control combinations and 5,000 differential calls; fourteen tooling tests pass. The 32-assertion conjunction passes with a full UINT timeout input. The complete OpenPLC test program passes natively after 50 calls, without running its service. Source-bound current evidence is in `projects/FB_MainSequence/04_reports/semantics/v0.3/`. Compact published verification records are in `docs/verification/plc-semantics-v0.3/`. Old v0.2 proof is historical. No Siemens/machine acceptance or full PLCopen conformance is claimed.

## Current Priority

The main entry in `web/` is a requirement-to-engineering workspace. Local `agy` returns structured specifications, SCL files and LAD review networks through a loopback Python bridge; static hosting retains request/result handoff without pretending local generation is available. `validation.html` retains compiled-ST replay for the repository example. Generated engineering is a candidate until its own checks run. Cloud service/deployment remain future work. Preserve the implemented abstract contract; real machine integration needs the actual Main/child FBs, safety interface, TIA/CPU versions and retention configuration.

## Knowledge Map

- `AGENTS.md`: startup protocol.
- `docs/ARCHITECTURE.md`: source, adapters and evidence map.
- `docs/DECISIONS.md`: durable choices and scoped implementation decisions.
- `docs/SCL_STANDARD_BASELINE.md`: official references, corrections to earlier advice, and implementation gaps.
- `projects/FB_MainSequence/01_specs/scan-contract.md`: authoritative implemented abstract-core semantics and migration rules.
- `plans/plc-semantics-v1/`: current task state.
- `validation/tests/README.md`: offline verification commands and limits.

- `web/README.md`: generation workspace, local agy bridge, result format and trace regeneration.
- `plans/plc-frontend/`: frontend acceptance and recoverable legacy-work handoff.

- `plans/plc-generation-ui/`: product correction and local generation acceptance.
