# Architecture

The product turns human process requirements into AI-generated Main LAD / FB SCL drafts, supported by a validation layer and an abstract PLC sequencing example. It does not include the full machine project.

## Generation entry

`web/index.html` owns requirements and engineering review. `generation-model.js` defines immutable request fingerprints and display validation; `generation.js` drives local generation, import/export and stale-result handling. No browser module executes PLC logic. Complete engineering recovery validates and restores the original request/result pair; standalone Agent-result import keeps exact current-task binding. Imported claims never confer the repository example’s proof.

`web/scripts/local-server.py` serves the static build and a loopback-only `/api` bridge. The default strict path calls `mcode-workflow.py`: Paperclip owns native processes, mcode supplies all AI roles, and program gates order specification approval, generation, parallel semantic/interface review and final supervision. One supervisor role handles both reviews; packet hashes bind exact inputs. Unresolved/fail/unknown results are withheld. No generation deadline is imposed on that path. Earlier agy/ZCode adapters remain explicit diagnostic options. No generated source is automatically promoted into `02_src/st`; approved text reviews remain drafts without industrial acceptance. Cancellation requests native run cancellation, with transport-failure limits documented in the [execution protocol](PLC_AGENT_WORKFLOW.md).

`web/validation.html` exposes only the repository example’s existing proof and replay. The static build generates an example payload directly from canonical ST and trace metadata. LAD networks are an engineering review representation, not Siemens project serialization. Static deployment without `/api` keeps task/result file handoff; it does not connect to a visitor’s localhost. A cloud implementation can use the same request/result format later.

## Visible simulation

`web/simulation.html` shows one historical conveyor draft with inputs, native outputs and a scan trace. `simulation-server.py` is a separate loopback-only service (8767); `conveyor-runtime.py` adapts Siemens syntax and compiles that fixed SCL with matiec/GCC. Each session has its own persistent native FB. A call samples toy-plant sensors, executes the FB once and advances the plant from Motor. The browser draws returned values and never implements PLC transitions. No arbitrary generated code is accepted; the generator’s approval gates stay unchanged. Startup captures SCL and static assets; matiec compiles the captured bytes and HTTP serves only the immutable in-memory bundle. Source bytes must match exactly. A bundle hash identifies responses and new sessions; post-start file edits/rebuilds do not alter existing or new native instances. Rebuild/restart and browser refresh load a new snapshot. Animation pacing and synthetic position do not confer Siemens, mechanics or safety acceptance. See [web run instructions](../web/README.md#visible-conveyor-simulation).

## Canonical flow

`01_specs/scan-contract.md → 02_src/st/*.st → sync-semantics.py → checker/export projections`

`FB_MainSequence` owns internal phase, timer, current timeout reason, diagnostic history, abort status and input-edge memory. Public outputs are never state storage. Helper FCs compute values without persistent instance state. A call snapshots previous values, derives transition conditions, computes the next tuple, commits, then decodes outputs.

The external inputs and outputs remain those listed in `00_meta/interface-contract.yaml`. See the scan contract for timing, continuous enable and error/diagnostic lifecycles; do not infer runtime semantics from variable names.

## Derived files

- PLCverif: canonical functions with Step7 BEGIN separators and independently authored assertion comments from `03_checks/plcverif/assertions.scl`.
- OpenPLC: canonical functions plus the separate `03_checks/openplc/driver.st` test program.
- TIA exchange: copies of the canonical source in `05_tia_sync/exported_scl`; prepared source is not proven importable/compiled Siemens output.
- `00_meta/projection-manifest.json`: source/contract/generator/output hashes. `--check` fails on drift.

## Evidence

- `validation/tests/test_scan_semantics.py` compiles actual ST through matiec and executes persistent FB instances; Python supplies inputs and checks explicit requirements.
- The same runner compares canonical/Step7-adapted/OpenPLC core outputs over deterministic input sequences. It does not boot the whole OpenPLC service.
- `validation/scripts/run-semantic-modelcheck.py` launches a fresh PLCverif case, records exact inputs and distinguishes pass/fail/unknown from process exit codes.
- Legacy static/modelcheck/smoke scripts still have issues described by the initial review; they must not be confused with the new semantic proof entry point.
- Siemens final evidence remains under the host boundary in `docs/contracts/container-boundary.md`.

## Read next

For changes, read the scan contract, then only the affected helper/FB, its assertions and tests. For process rationale, read `docs/DECISIONS.md`. For missing tools/full-machine integration, read the current plan before old recovery notes.

## v0.3 lifecycle boundary

The core is a continuously enabled block with an explicit repeating command, not a one-shot execute block. FB Busy/Valid differ from CommandBusy; Done remains a cycle marker. Disable clears current error; enable rising clears timeout history. Business Reset only reinitializes healthy commands. External xEStop is inhibition feedback, never an implementation of F safety. See the scan contract and interface 0.2.0 migration notes.
