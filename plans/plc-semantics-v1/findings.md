# Current result: v0.3 implemented and verified; earlier entries below are historical.

# Findings
- Baseline HEAD e8c282f4defdea8f7c8c8501cf149ecb11ada129, staged executable-mode-only changes in 4 container scripts.
- At baseline, canonical ST and TIA payload matched byte-for-byte; OpenPLC FB behavior matched. PLCverif snapshotted timeout before updates, but canonical ST recalculated after timer update.
- Original source defects and original model pass were independently reproduced in previous task turn.
- Source/spec assets were already untracked; do not interpret their presence as changes authored this turn.
- Pending domain decisions: Stop/EStop and fault acknowledgement; xEnable start-only vs ongoing permission.
- Preserve completion priority, zero disables timeout, live timeout input semantics unless user redirects. These are explicitly documented compatibility choices, not general PLC rules.

## Verified changes
- Canonical ST now snapshots phase/timer/fault, derives timeout once, computes next values, commits, then decodes outputs. The three assignments are not hardware-atomic; observation is after the owning invocation returns.
- Baseline tests reproduced early fault at threshold 8 on waiting call 7 and a completion/timeout inconsistency. Final compiled-ST suite passes 12 tests; Python supplies stimuli and checks compiled ST, not a replacement state-machine implementation.
- 5,000 deterministic invocations compare the canonical ST, Step7-adapted projection and OpenPLC core. This is bounded differential coverage, not complete equivalence proof or full OpenPLC-service acceptance.
- All 16 assertion comments are included in one formally satisfied assertion conjunction. Timeout is an unconstrained unsigned word[16] resampled at loop_start in the generated model. The model proves the current candidate and does not resolve contradictory process requirements.
- Compatible final settings: Classic, dynamic=true, df=true, req_as_invar=false. Earlier default BDD/invariant attempts timed out; the Ic3 path encountered backend incompatibility. Keep those attempts separate from final pass.
- Real negative control: deliberately false assertion -> VIOLATED, tool exit 0, new gate exit 1. Four verdict tests additionally reject UNKNOWN, missing verdict and nonzero tool exits.
- Existing reports parent is root-owned. Created only a new semantics subdirectory and assigned that new directory to the current user; existing reports and their ownership were preserved.
- All nine generated TIA exchange units match canonical text; TIA import/compile, PLCSIM and actual CPU behavior are unverified.

## Evidence
Source-bound summary and final proof are in projects/FB_MainSequence/04_reports/semantics/. Task outputs contain a review report and portable evidence archive. Full scratch builds/backups remain outside the repository under the Codex task's work/plc-semantics and work/plc-review directories.

## Official-source correction after user feedback
- Official Siemens style guide V2.1.0 (04/2025), DA008/DA011/DA012 reviewed. Continuous enable differs from single-execution execute; previous start-only Enable recommendation withdrawn.
- Candidate reads its own xTimeoutFault/xError outputs; DA008 calls for separate internal state and output publication. This is a style-guide compliance gap, not a newly demonstrated language error.
- STEP 7 Safety ESTOP1 acknowledgment is not a universal ordinary-Stop/fault-reset rule.
- Official references and exact scope recorded in docs/SCL_STANDARD_BASELINE.md. Old questionnaire is superseded; no ST or proof inputs changed in this research turn.

## v0.3 implementation
- Initial new tests demonstrated Enable loss did not stop, Stop cleared error, and held Start replayed after stop; all three were corrected.
- DA011 error recovery is implemented via disable, not a business Reset bypass. Timeout history is separate and cleared on the next enable rise.
- 24 compiled-ST tests / 160 combinations / 5,000 comparisons pass. 26 assertions pass; actual FALSE is rejected. Full native example passes at call 50.
- Outputs are single-write and never read by canonical FB; output tampering cannot affect internal state.
- The initial green development run preceded final Reset semantics. Only final-scan, final formal and v0.3 evidence are current.
