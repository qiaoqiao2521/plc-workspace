# Progress

Current: the initial frontend/local agy round trip is delivered. The [CM Codex user evaluation](user-eval-report.md) confirms draft review/export usability but identifies open generation-quality and project-recovery problems; generated engineering is not accepted.

Done:
- Product intention restored in PROJECT/README; prior validation setup preserved in docs/validation-setup.md.
- Requirement/state editor, immutable request fingerprint, SCL/I/O/LAD views, stale-result restrictions and Agent task/result handoff implemented.
- Loopback agy bridge: one active task, 180-second default budget, structured result validation, cancellation and explicit failure states. Generated code remains a candidate.
- 10/10 JavaScript tests and 6/6 Python bridge tests passed. Python tests are synthetic process/control-flow tests, not model or PLC proof.
- Actual browser-to-agy-to-browser round trip: independent single-step conveyor demand → FB_ConveyorDraft.scl + LAD periodic call/specification → displayed candidate, 50.8 seconds. Generated PLC code was not compiled or semantically accepted.
- Desktop and 390×844 mobile inspection; mobile document widths 375/375, no horizontal page overflow.
- Actual UI checks: schema failure preserves requirement; example review; imported example is treated as an unverified candidate; requirement edits disable old-result export; export preview contains actual source text; missing bridge shows offline handoff; secondary replay loads six scenarios and published example counts.
- Core projection check passed. Canonical ST, scan contract and formal assertions unchanged.

Model invocation accounting (no hard CapMesh experiment budget was requested):
1. Small compatibility probe, plan+sandbox+disable-slash: SUCCESS, 16.1s; warning revealed plan mode ineffective.
2. UI full conveyor generation: exit 3, schema/provider rejection, no accepted result.
3. Plan+sandbox small probe without disable-slash: SUCCESS, 7.2s.
4. UI simplified conveyor generation before schema fix: exit 3, no accepted result.
5. Minimal full-schema diagnostic: INVALID_ARGUMENT on numeric enum, no accepted result.
6. Same simplified UI demand after fix: SUCCESS, 50.8s, candidate displayed.

Remaining:
- New generated engineering needs independent compilation/scan/formal checks and Siemens acceptance; example proof cannot be reused for it.
- LAD is currently a review-network representation, not a TIA project. Cloud generation/deployment and account/domain checks are future work.
- Earlier in-app browser Blob download event timed out. The later CM Codex evaluation downloaded actual engineering/SCL/LAD files in isolated Chromium and checked hashes. In-app browser OS-level save and clipboard persistence remain unconfirmed.
- Local job results are process memory and browser view state; reloading before export does not restore an in-flight job. Server retains single-job exclusion until completion/cancellation/budget termination.
- Older imported assets remain preserved with root-Codex owner and per-group shortest acceptance routes in plans/plc-frontend/legacy-handoff.md.

Next: root Codex handles clarification before actuation generation, full-engineering recovery, and verification bound to each generated candidate. Runtime logs, raw prompts and CLI session IDs remain outside Git. The evaluation's synthetic requirements and two explicitly unaccepted candidates are retained as reproducible review samples; they do not modify canonical PLC source.


## 2026-10-01 code fixes and ZCode comparison

- Full engineering reopen implemented with original request/result binding and recomputed fingerprint; ordinary result import retains current-task matching. Imported engineering never receives example proof.
- LAD title numbering normalized consistently in view/export; handoff buttons wrap on small displays.
- Actual old exported example and conveyor reopened in a fresh browser page; refresh/reopen succeeded, edited requirement disabled stale export. 390px layout measured without page overflow.
- Optional ZCode local CLI adapter implemented; 13 JS / 8 Python tests and build/projection checks passed. Strict JSON response validation, tool denial, process budgets and unchanged agy default retained.
- Model invocation accounting and observed acceptance boundary are in [ZCode retest](zcode-retest.md). Earlier PLC candidates/oracle hashes unchanged; no automatic generated-source promotion.
- Root Codex remains owner for independent new-candidate checks and ZCode service/runtime diagnosis. This turn does not introduce CM-native ZCode support or claim PLC correctness from process/connection success.


## 2026-10-01 unlimited local CLI comparison

- Explicit timeout 0 implemented; default bounded budget and cancellation retained. UI reports unlimited generation correctly. Regression: 13 JS / 9 Python and static build pass.
- Six real invocations recorded, including two MiniMax setup failures; no time-based termination. Both corrected A/B pairs completed. MiniMax A matched 16 selected normalized-ST observations; ZCode A mismatched three. Both B deliveries failed clarification-before-actuation requirement B04.
- Original generated fixtures, source-bound observations and reproducible native probes are retained in [unlimited delivery report](unlimited-delivery.md). Normalization and first MiniMax compiler failure are disclosed; no TIA, LAD import or physical-machine acceptance is claimed.
- Canonical source/oracle unchanged. Prior legacy assets remain preserved with root-Codex owner and acceptance routes in [legacy handoff](../plc-frontend/legacy-handoff.md). Runtime sessions, requests and logs stay outside Git.
