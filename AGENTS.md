# Project entry

1. Read `PROJECT.md` for user intent and the current boundary.
2. For PLC changes, read `projects/FB_MainSequence/01_specs/scan-contract.md` before source.
   Read `docs/SCL_STANDARD_BASELINE.md` as well: it supersedes the earlier request to let the user choose an arbitrary Enable/Reset convention and records the official basis and the implemented v0.3 scope.
3. For new generation/Harness work, read `plans/plc-logic-harness-v1/task_plan.md`, then its `findings.md` and `progress.md`. Distinguish implemented S1/S2 and model-access changes from the unstarted S3/S4 slices; stop at the recorded boundary.
4. Follow `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` and `plans/plc-semantics-v1/` only as needed for the existing implementation and abstract core.
5. For composable simulation, read `docs/PLC_SIMULATION.md` and `plans/plc-composable-simulation/`. The 2026-11-26 user authorization adds this verification entry independently of the still-unstarted generation S3/S4 slices; do not use the older full-simulator non-goal to block this implemented scope. For Siemens simulation research or adapters, also read `docs/SIEMENS_SIMULATION_BASELINE.md` and `web/data/simulation/siemens-reference-index.json`; documented product capabilities and proposed gaps are not implemented backend support or runtime acceptance.

## PLC-specific rules

- Reason about successive FB invocations and persistent state, not a one-shot function.
- Snapshot old phase/timer/fault, derive conditions once, compute next values, commit, decode outputs.
- Do not conflate invocation persistence with power-loss retention.
- Main owns physical I/O and shared events; the semantic FB has no hardware addresses.
- `02_src/st` is authoritative. Run `validation/scripts/sync-semantics.py --write` after changes, then `--check`; never hand-patch a generated projection.
- Do not replace real parameter inputs with checker-only constants without explicit bounded proof scope.
- Test boundary scans and simultaneous inputs; record tool errors/UNKNOWN as such.
- Follow official language/runtime/interface rules before asking process questions. Distinguish Siemens engineering guidance, language semantics, safety functions and machine-specific requirements; do not present the current candidate as standards compliant.
- Linux compiled-ST/formal evidence does not establish TIA compilation, PLCSIM, or real PLC acceptance.
- `CURRENT_STATE.md` is a dated recovery snapshot, not current proof. Use source-bound reports.
- Keep specification authority, generation, independent expected behavior and verdict authority separate. Shared IR or matching outputs alone do not prove correctness.
- Do not add a scheduler or general Agent platform under the Harness refactor. SpecMesh records project intent and continuity; it does not replace the deterministic PLC checks.
- No automatic device writes/downloads or F-safety logic generation. Optional TIA integration never upgrades unrun checks into acceptance.

Update the contract and decision record when behavior changes. Keep large third-party tools out of project-memory documents. Keep plan status, historical evidence and newly executed verification distinct.

## New engineering generation

The currently implemented path uses [PLC Agent execution protocol](docs/PLC_AGENT_WORKFLOW.md): analyze → supervisor review → freeze → generate → parallel scan/interface reviews → same supervisor → programmatic draft gate. Direct API calls and external Agent answers enter the same `plc-workflow.py` controller. No CM/Paperclip, mcode or CLI adapter is required. Model transport cannot alter verification authority. Unresolved process decisions must prevent generation, not merely accompany generated actions as questions. Review approval does not grant tool, Siemens or machine acceptance.

S1 evidence classification and the S2 synthetic latch BOOL IR/LAD slice are implemented; one actual Agent initial-generation latch run is recorded; configured remote API and actual Agent diagnostic-repair acceptance remain open. Local protocol fixtures do not close those items. S2 repairs only IR and regenerates both products; old SCL tasks still repair source. Until a slice is implemented and verified, describe the existing runtime truthfully; do not infer new support from these planning documents. Update the affected protocol and architecture only with the corresponding implementation.

The 2026-11-23 user correction removes the former CM/Paperclip requirement. Keep API keys and Agent tokens out of source, runtime evidence, argv, browser storage and exports. Agent control means answering controller-issued packets, not editing expectations or writing acceptance. Current setup and protocol are in `docs/PLC_AGENT_WORKFLOW.md`; older CM/CLI plan records are historical.

For external Agent takeover, read `.agents/skills/plc-workspace-control/SKILL.md` and use `web/scripts/plc-agent.py`. The Skill guides one persistent CLI session; it cannot replace the controller’s gates. Keep task credentials only in that process’s stdin/memory, not a new config file or argv.

Simulation actions use finite `plc-agent.py simulate` requests, not the generation stdio workflow. Capture exact current source, typed scene and explicit profile; never replace a current engineering candidate with a passing template. UI rendering does not execute PLC transitions. Keep native scan-count plant evidence, OIP native-PLC/physics evidence and OIP own IEC-subset self-tests separate. Record source/scene/contract hashes and first failures; imported reports and zero-assertion runs confer no acceptance. Optional upstream code stays pinned outside this repository.
