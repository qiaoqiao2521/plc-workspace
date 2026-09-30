# Progress

Current: frontend and local agy generation acceptance complete. Git history identifies the delivered change.

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
- In-app browser Blob download event timed out. Export preview and copy action are available; OS-level file save and clipboard persistence are not confirmed.
- Local job results are process memory and browser view state; reloading before export does not restore an in-flight job. Server retains single-job exclusion until completion/cancellation/budget termination.
- Older imported assets remain preserved with root-Codex owner and per-group shortest acceptance routes in plans/plc-frontend/legacy-handoff.md.

Next: user reviews the local generation workspace, selects a real process and supplies missing hardware/engineering facts before Siemens integration. Runtime logs, prompts, generated demo candidate and CLI session IDs remain outside Git.
