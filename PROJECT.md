# PLC Workspace

## Why

Turn human process requirements or flow language into reviewable PLC engineering: clarify state/I/O/constraints, use AI to generate Main LAD and FB SCL, then validate and prepare engineering outputs. Cyclic execution, persistent state and timing constrain the generator; verification protects its quality.

## User Intent

The user has invested substantially in this industrial-automation workspace. On 2026-10-01 the user corrected the product direction: human requirements/flow language → AI-generated LAD/SCL is the main purpose. The earlier semantic-convergence work is the supporting Agent quality layer. Python supports engineering without obscuring PLC scan semantics.

2026-11-06: Keep the product narrow: accurate LAD and SCL generation, not a general industrial platform. The Harness must strictly constrain process assumptions, supported generation, validation and delivery; it must not invent process choices or expand into general Agent orchestration. Use SpecMesh to record this refactor in this repository, not to redesign SpecMesh itself. TIA may be referenced or optionally connected, but is not a mandatory core dependency. At that date a bounded Logic IR and two deterministic output paths were planned; the S2 BOOL slice was implemented on 2026-11-23.

2026-11-23: The user retired CM/Paperclip and requested direct model API configuration plus external Agent control. Both now use the same constrained PLC controller. The user also requested Skill/CLI/workflow integration; the repository provides `plc-workspace-control` and a thin persistent `plc-agent.py` client around that same controller. No model CLI, company ID or general Agent platform is required.

2026-11-26: The user requested an AI-callable, atomically composable and visually useful simulation entry tied to PLC logic, then authorized full integration and actual subagent testing. This adds a bounded validation workspace beside generation, with an optional pinned Open Industry Project plant bridge. It does not start generation S3/S4 or broaden Siemens acceptance.

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

The strict SCL path loads project Skill content, accepts original SCL, checks captured generated source with matiec, and retries source-only repairs (two by default). `conveyor-12-v1` adds independently fixed native scan expectations; other tasks get compilation only. S1 report v2 and deterministic required-check gates now distinguish these scopes, retain failed/cancelled candidates and prevent imported/legacy reports from granting current acceptance. The explicitly selected synthetic latch-start-stop-v1 benchmark now has a bounded BOOL IR, deterministic SCL and executable serialized LAD graph. Other tasks retain limited LAD review networks; none are TIA-importable LAD projects. See [current SCL loop](docs/SCL_CLOSED_LOOP.md). One actual Agent latch generation run is recorded separately from fixture-driven regression. Configured remote API, actual Agent diagnostic repair and Windows TIA acceptance remain open.

The main entry in `web/` is a requirement-to-engineering workspace with in-page API configuration and external Agent takeover. Specification review precedes generation; actual source/graph checks precede concurrent text reviews and the same supervisor role's final review. `plc-workflow.py` owns the sequence and acceptance; `model-api.py` transports fresh Chat Completions requests, and `agent-dispatch.py` waits for authenticated, schema-checked stage answers. No CM/Paperclip/mcode or old model CLI adapter remains in the runtime. The repository Agent Skill uses a thin stdio CLI for request preparation, stage answers and cancellation; it does not schedule roles or sign verification results. See [execution protocol](docs/PLC_AGENT_WORKFLOW.md). Static hosting retains file handoff; `validation.html` retains the repository example's compiled-ST replay.

## Current Priority

The [composable simulation entry](docs/PLC_SIMULATION.md) now uses the same 8766 service and Agent CLI: typed atomic devices, captured-source native execution, independent finite cases, fault injection, 3D observation and trace replay. Current engineering imports validate request/result identity; saved verdicts stay historical. Four explicit profiles and a new synthetic transfer/pusher example are supported. OIP can run a real Jolt conveyor under the same native conveyor source, separately from its upstream IEC-subset self-tests. Actual implementation and test evidence are tracked in [the simulation plan](plans/plc-composable-simulation/progress.md).

[PLC Logic Harness v1](plans/plc-logic-harness-v1/task_plan.md) remains the active generation plan. S1's scoped evidence and S2's deterministic BOOL IR, LAD/SCL outputs, independent native/graph checks, bounded IR repair and UI recovery are implemented. The 2026-11-23 access correction replaces the old orchestration dependency with direct API configuration or external Agent answers. The PLC contract, checks and repair limits remain in force. Local HTTP fixtures test the new connections and use real native tools where stated; an actual Agent has completed one first-attempt latch generation through the Skill/CLI, while configured remote API and actual Agent diagnostic-repair acceptance remain open.

S3–S4 have not started. Do not add model roles, a scheduler, broader PLC instructions or mandatory Siemens dependencies. The next online check uses the same latch contract with a configured API or an actual Agent repair scenario, records failures/repairs/cancellation and keeps TIA/PLCSIM/machine acceptance separate. Cloud deployment and real-machine integration still require their own scope and actual project inputs.

## Knowledge Map

- `AGENTS.md`: startup protocol.
- `plans/plc-logic-harness-v1/`: active refactor plan, inspected facts and implementation status.
- `docs/ARCHITECTURE.md`: current implementation, adapters and evidence map; proposed structure is not yet implemented.
- `docs/DECISIONS.md`: durable choices and scoped implementation decisions.
- `docs/SCL_STANDARD_BASELINE.md`: official references, corrections to earlier advice, and implementation gaps.
- `docs/SCL_CLOSED_LOOP.md`: implemented current-source compilation and repair loop.
- `docs/PLC_SIMULATION.md`: typed scene, current-engineering handoff, CLI/HTTP actions and OIP evidence boundaries.
- `projects/FB_MainSequence/01_specs/scan-contract.md`: authoritative implemented abstract-core semantics and migration rules.
- `plans/plc-semantics-v1/`: abstract-core semantic convergence records, not the new generator plan.
- `validation/tests/README.md`: offline verification commands and limits.
- `web/README.md`: generation workspace, bridges, result format and trace regeneration.
- `plans/plc-frontend/`: frontend acceptance and recoverable legacy-work handoff.
- `plans/plc-generation-ui/`: earlier product correction and local generation acceptance.
