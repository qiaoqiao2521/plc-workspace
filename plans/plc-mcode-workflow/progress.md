# 2026-10-01 implementation and acceptance

Implemented [execution protocol](../../docs/PLC_AGENT_WORKFLOW.md), a PLC-specific controller using the existing Paperclip process adapter, mcode-only AI roles and one supervisor per engineering workflow. `npm --prefix web run dev` now selects this strict path with timeout 0; existing company/runtime parameters remain explicit. Local frontend 8766 is running this configuration. Old agy/ZCode adapters are explicit diagnostics.

## Accepted behavior

- Programmatic ordering: unresolved questions or supervisor rejection prevents generation; packet hashes bind reviews; changed request identity fails. Parallel semantic/interface reports precede final supervision. Fail/unknown cannot be overridden by an approve verdict.
- Failed review delivery becomes controller-classified unknown and still goes to supervision. No runtime lock, diagnostic or CLI session is committed.
- 13 JS / 17 Python tests pass; static build and canonical projection check pass. Python workflow/bridge tests are deterministic fixtures, not model or PLC proof.
- Real Paperclip 2026.916.1 + mcode 0.5.9 (MiniMax-M3.1-Flash-Preview): 12 model invocations, 8 successful packets and 4 invalid structured outputs. All task-local roles paused after delivery/failure; no generation stage started in these real runs.
- A preflight: analyst supplied a ready label but unresolved questions/defaults; supervisor rejected specification inconsistencies. Controller blocked generation.
- B preflight: first two attempts failed format validation (one diagnostic showed Markdown-fenced JSON); no generation. After explicit bare-JSON instruction, analyst returned blocked with 12 questions. Supervisor approved the incomplete specification packet, but controller correctly retained blocked status because questions/unresolved items remained. No automatic retries.
- First read-only audit: parallel semantic packet delivered, interface packet failed JSON validation, controller stopped. After improving error aggregation and compact JSON instructions, fresh audit ran both reviewers concurrently; both packets delivered, supervisor rejected. It explicitly corrected the interface reviewer's false claim that the eighth waiting call was the seventh. This does not establish that all other reviewer/supervisor findings are correct.
- Actual UI → strict bridge → native mcode B run: model output failed format validation. Editable requirement survived, no candidate appeared, engineering export remained disabled. Initial UI blamed model/login/network generically; corrected to workflow failure/not released, covered by bridge regression. Saved/reloaded B requirements and strict-path label confirmed on the final running server. No successful real clarified-request generation-to-approved-draft round trip was obtained or claimed.
- Cancellation: one additional **synthetic mcode stub** native process, zero model invocation. SIGTERM of controller yielded Paperclip run status cancelled, no generation. Genuine model cancellation and full UI-to-native cancellation remain unverified.

All real invocation stages/status/exits/durations and selected findings are in [sanitized acceptance](acceptance.json). Runtime originals remain in the chat work directory, outside Git. Initial B cleanup tried Paperclip's blocked status without its required blocker data and received 422; task handoff now uses in_review, and the first affected records were reconciled. No old service/config/provider changes or upstream Paperclip code changes.

## Limits and next owner

Root Codex owns continuation. A clarified request must pass specification review before testing a real generation-to-draft round trip. New-candidate compilation, native scan and formal checks are not integrated automatically, and no industrial-accepted state exists. Siemens/TIA/PLCSIM/machine evidence remains absent. Same-model review can misread requirements and over-block; add source-bound tool evidence and verify corrections rather than waive gates.

Canonical ST, assertions, contract, oracle and earlier model fixtures remain unchanged. Existing legacy assets retain the root-Codex owner and shortest acceptance entries in [legacy handoff](../plc-frontend/legacy-handoff.md).
