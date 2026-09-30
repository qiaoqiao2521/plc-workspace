# Architecture

The product turns human process requirements into AI-generated Main LAD / FB SCL drafts, supported by a validation layer and an abstract PLC sequencing example. It does not include the full machine project.

## Generation entry

`web/index.html` owns requirements and engineering review. `generation-model.js` defines immutable request fingerprints and display validation; `generation.js` drives local generation, import/export and stale-result handling. No browser module executes PLC logic. Complete engineering recovery validates and restores the original request/result pair; standalone Agent-result import keeps exact current-task binding. Imported claims never confer the repository example’s proof.

`web/scripts/local-server.py` serves the static build and a loopback-only `/api` bridge. One bounded job runs the selected CLI in a disposable directory with a JSON result schema: agy uses plan/sandbox, while ZCode uses explicit edit mode with tool denial and a stable CLI runtime path. No generated source is automatically promoted into `02_src/st`. The result is a candidate even if the model self-reports passing checks. Cancellation terminates the job; wrong fingerprints, malformed output, missing structured results and non-success process status are rejected.

`web/validation.html` exposes only the repository example’s existing proof and replay. The static build generates an example payload directly from canonical ST and trace metadata. LAD networks are an engineering review representation, not Siemens project serialization. Static deployment without `/api` keeps task/result file handoff; it does not connect to a visitor’s localhost. A cloud implementation can use the same request/result format later.

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
