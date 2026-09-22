# Project entry

1. Read `PROJECT.md` for user intent and the current boundary.
2. For PLC changes, read `projects/FB_MainSequence/01_specs/scan-contract.md` before source.
   Read `docs/SCL_STANDARD_BASELINE.md` as well: it supersedes the earlier request to let the user choose an arbitrary Enable/Reset convention and records the official basis and the implemented v0.3 scope.
3. Follow `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` and `plans/plc-semantics-v1/` only as needed.

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

Update the contract and decision record when behavior changes. Keep large third-party tools out of project-memory documents.
