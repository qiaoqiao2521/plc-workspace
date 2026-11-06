# PLC Workspace

## Why

Turn human process requirements or flow language into reviewable PLC engineering: clarify state/I/O/constraints, use AI to generate Main LAD and FB SCL, then validate and prepare engineering outputs. Cyclic execution, persistent state and timing constrain the generator; verification protects its quality.

## User Intent

The user has invested substantially in this industrial-automation workspace. On 2026-10-01 the user corrected the product direction: human requirements/flow language → AI-generated LAD/SCL is the main purpose. The earlier semantic-convergence work is the supporting Agent quality layer. Python supports engineering without obscuring PLC scan semantics.

2026-11-06: Keep the product narrow: accurate LAD and SCL generation, not a general industrial platform. The Harness must strictly constrain process assumptions, supported generation, validation and delivery; it must not invent process choices or expand into general Agent orchestration. Use SpecMesh to record this refactor in this repository, not to redesign SpecMesh itself. TIA may be referenced or optionally connected, but is not a mandatory core dependency. A bounded Logic IR and two deterministic output paths are planned, not implemented.

## Non-goals

No replacement of TIA/PLCSIM with container evidence. No remote/device writes, automatic download or F-safety code generation. No platform migration or broad rewrite. No new general-purpose Harness, scheduler, PLC IDE, HMI/SCADA suite or multi-vendor platform. No automatic claim of correctness from compilation, shared IR, model approval or matching finite traces.

## Success

A user can describe a process, review state and I/O specifications, generate and export SCL/LAD drafts, then verify that particular engineering output. The planned bounded path must generate actual LAD logic, not merely a call to an SCL FB. Independent expectations and negative controls must distinguish correct outputs from known wrong variants. Unresolved process choices block executable logic generation; missing evidence cannot become acceptance. Generated code never inherits another example's proof.

Another agent can recover product intent, current implementation, planned changes and the scan contract from a few entry files.

## Constraints

- Existing Main=LAD, FB=SCL examples and semantic I/O separation remain. A future bounded dual-output comparison path must not silently change existing engineering contracts.
- Current example is an abstraction of 303翻转; the real machine's Main, child FBs and I/O are absent.
- Normal flow remains 0→1→2→3→1.
- TIA/PLCSIM and CPU/firmware versions are not yet pinned; no Siemens final evidence exists.
- Project assets were historically shipped outside Git. Existing assets and pre-existing staged execution-mode changes must be preserved.
- Canonical `02_src/st` and its existing evidence remain authoritative for the abstract example. The planned IR applies to new supported generation tasks, not a retroactive rewrite of this core.
- Compilation, behavior, LAD/SCL comparison and platform checks need separate scopes and verdicts. Failed candidates may remain reviewable without gaining a release/acceptance status.

## Current State

The v0.3 abstract scan contract and interface 0.2.0 are implemented: internal state/output separation, continuous enable, edge-consumed commands, distinct current error and timeout history. Repository records report twenty-seven compiled-ST tests including 160 control combinations and 5,000 differential calls, fourteen tooling tests, a 32-assertion conjunction with a full UINT timeout input, and a complete OpenPLC test program passing natively after 50 calls without running its service. These historical checks were not rerun for the 2026-11-06 plan-only change.

Source-bound current evidence is in `projects/FB_MainSequence/04_reports/semantics/v0.3/`. Compact published verification records are in `docs/verification/plc-semantics-v0.3/`. Old v0.2 proof is historical. No Siemens/machine acceptance or full PLCopen conformance is claimed.

The strict SCL path loads project Skill content, accepts original SCL, checks captured generated source with matiec, and retries source-only repairs (two by default). `conveyor-12-v1` adds independently fixed native scan expectations; other tasks get compilation only. LAD remains a limited review representation, not a general executable or TIA-importable graph. See [current SCL loop](docs/SCL_CLOSED_LOOP.md). Online mcode/CM and Windows TIA acceptance remain separate from fixture-driven regression.

The main entry in `web/` is a requirement-to-engineering workspace. The selected strict workflow uses mcode through CM/Paperclip: specification review precedes generation, two reviewers run concurrently and one supervisor reviews the outcome. See [execution protocol](docs/PLC_AGENT_WORKFLOW.md). Earlier agy/ZCode adapters remain diagnostic options. Static hosting retains request/result handoff; `validation.html` retains compiled-ST replay for the repository example. Parallel text reviews are not industrial acceptance.

## Current Priority

2026-11-06: [PLC Logic Harness v1](plans/plc-logic-harness-v1/task_plan.md) is the active generation/Harness refactor plan. This change delivers planning documents only; S1–S4 are not implemented. Start with S1: distinguish compile-only success from behavior acceptance and enforce explicit required-check verdicts. Then deliver one bounded start/stop LAD+SCL vertical slice before adding conveyor sequencing or optional TIA adaptation.

Do not add Agent roles, change the current scheduler, rewrite the abstract core, or introduce a mandatory Siemens dependency as part of this planning change. Cloud deployment and real-machine integration remain outside the active slice. Real integration still needs the actual Main/child FBs, safety interface, TIA/CPU versions and retention configuration.

## Knowledge Map

- `AGENTS.md`: startup protocol.
- `plans/plc-logic-harness-v1/`: active refactor plan, inspected facts and implementation status.
- `docs/ARCHITECTURE.md`: current implementation, adapters and evidence map; proposed structure is not yet implemented.
- `docs/DECISIONS.md`: durable choices and scoped implementation decisions.
- `docs/SCL_STANDARD_BASELINE.md`: official references, corrections to earlier advice, and implementation gaps.
- `docs/SCL_CLOSED_LOOP.md`: implemented current-source compilation and repair loop.
- `projects/FB_MainSequence/01_specs/scan-contract.md`: authoritative implemented abstract-core semantics and migration rules.
- `plans/plc-semantics-v1/`: abstract-core semantic convergence records, not the new generator plan.
- `validation/tests/README.md`: offline verification commands and limits.
- `web/README.md`: generation workspace, bridges, result format and trace regeneration.
- `plans/plc-frontend/`: frontend acceptance and recoverable legacy-work handoff.
- `plans/plc-generation-ui/`: earlier product correction and local generation acceptance.
