# PLC Agent execution protocol

This protocol governs new requirement-to-engineering drafts. It does not change the abstract example's contract or grant Siemens/machine acceptance. The strict path uses **only mcode** for AI work and the existing **CM/Paperclip process adapter** for execution. One supervisor role reviews both specification and final delivery; two independent review sessions can run concurrently.

## Ordered gates

|Stage|Role|Required output and gate|
|---|---|---|
|1. Analyze request|mcode engineer|Explicit specification, observable obligations, blocking questions. No SCL/LAD. No invented valve, feedback, Stop, Reset destination or time settings.|
|2. Review specification|mcode supervisor|Approve/reject/unknown, with evidence. Unresolved analyst questions or contradictions still block even if the supervisor approves.|
|3. Freeze and generate|mcode engineer|Only after stages 1–2 pass. Bind specification and request hashes. New unresolved questions, fabricated proof or mismatched request identity stop delivery.|
|4a. Scan semantics review|mcode semantic reviewer|Review persistent state, snapshot/next/commit/output timing, edges, simultaneous controls, deadlines and Done pulse against this request.|
|4b. Interface review|mcode interface reviewer|Independently review specification/I/O/SCL/Main LAD agreement, persistent instance and unconditional call, placeholders and unsupported claims. Run concurrently with 4a on identical frozen inputs.|
|5. Final review|same mcode supervisor role|Review original request, candidate and both reports. Worker failure becomes unknown. Any fail/unknown prevents delivery, even if supervisor says approve.|
|6. Deliver review draft|program gate|Only the `reviewed_draft` disposition exposes engineering to the UI. Industrial acceptance remains `not_run`; text reviews cannot manufacture tool evidence.|

The controller starts each stage, validates JSON and input SHA-256, and decides whether the next stage may start. A prompt asking a model to wait is not the gate. Every invocation runs in a fresh mcode session; the supervisor is one persistent Paperclip role, with the exact current packet supplied for each review. It does not rely on conversational memory.

Specification/source changes invalidate prior approvals. This implementation creates a fresh workflow directory for a new request rather than reuse previous packets. Models cannot waive a failed programmatic gate. An `approve` verdict for a specification containing unresolved questions does not authorize generation.

## Evidence and authority

- Main owns physical I/O; FB operates on logical signals. Unknown addresses alone do not authorize inventing addresses. Missing mechanical decisions block actuation generation.
- Process choices come from confirmed user requirements. Official SCL rules constrain implementation but do not choose a valve, stopping behavior or reset position.
- All review findings must cite the supplied requirement or source. Reviewers can invent extra requirements too; the supervisor must distinguish those from actual violations. A model vote is not proof.
- Actual compilation, boundary scan execution and formal checks must bind to that generated source and its independently defined expectations. The repository example's 32 assertions cannot automatically cover a new FB. These automated new-candidate tool gates are **not yet integrated** into this path.
- TIA/CPU/firmware, PLCSIM and machine/safety acceptance remain separate, source-bound engineering steps. The current program has **no industrial-accepted state** and does not deploy/download.
- Same-model parallel review provides separate sessions, not statistically independent failure modes. Smart permission is not a filesystem sandbox. The worker strips Paperclip runtime credentials from the mcode subprocess environment, uses disposable cwd, and instructs no tools; it does not claim protection from a malicious model accessing the host.

## Running the strict frontend

Build, then select the existing local company explicitly. No credentials are passed or stored in the repository:

```sh
npm --prefix web run build
python3 web/scripts/local-server.py --provider mcode-cm --timeout 0 \
  --mcode /absolute/path/to/mcode \
  --cm-company EXISTING_LOCAL_COMPANY_ID \
  --workflow-root /absolute/runtime/root/outside/repository
```

The existing Paperclip loopback API defaults to port 3100. It owns model processes; there is no new general scheduler or change to its upstream source. Periodic heartbeats are disabled for these task-local roles; one explicit wake starts each stage. Roles are paused after completion. Native issues/runs preserve execution history. Runtime requests, jobs, diagnostics and sessions stay outside Git.

No mcode timeout/max-step cutoff or Paperclip process timeout is imposed. HTTP request timeouts handle transport failures, not model generation budgets. Frontend cancellation signals the controller; it requests native cancellation of active Paperclip runs and pauses its roles. Native cancellation/API outages can fail: inspect retained run IDs and use Paperclip's run-cancel endpoint rather than assume all remote processes stopped. Full UI-to-native cancellation has not yet been accepted.

The previous agy/ZCode single-generation adapters remain explicit diagnostic options; they do not execute or satisfy this protocol.

## Read-only audit and recovery

`web/scripts/mcode-workflow.py audit` takes `--request`, `--candidate`, `--runtime`, `--company`, `--mcode`. It reviews an existing structured result with two parallel reviewers and a supervisor, but **never generates or exports engineering**. It does not bypass specification approval for a new generation. `audit_complete` means handoff complete, irrespective of report verdicts.

An invalid result or interrupted workflow preserves runtime evidence, marks the native handoff for review and does not automatically retry. Correct the cause and start a fresh, fully accounted attempt. Unknown is not passed. Root Codex owns integration and release; worker roles cannot edit canonical PLC files or shared project notes through this workflow.

Implementation: [controller](../web/scripts/mcode-workflow.py), [gate regressions](../web/scripts/test_mcode_workflow.py), [task and acceptance](../plans/plc-mcode-workflow/task_plan.md).
