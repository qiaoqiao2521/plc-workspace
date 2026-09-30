# Strict mcode workflow through CM/Paperclip

User intent (2026-10-01): enforce ordered industrial-engineering steps, use only local mcode, allow parallel workers and one supervisor.

1. Reuse the live local Paperclip process adapter, per CM's confirmed direction; do not extend the legacy Python scheduler. Adopt CapMesh capabilities/index.md agent-control and CM plans/paperclip-based-cm/task_plan.md.
2. Add a narrow PLC workflow: request analysis → independent supervisor approval of frozen specification → generation → parallel independent semantic/interface reviews → same supervisor disposition. Programmatic gates, exact packet hashes and no unknown-as-pass.
3. Missing process decisions block code generation. Runtime assets remain outside Git. No time-based generation cutoff; cancellation remains external/process-owned. No auto-deploy/PLC write.
4. Test rejected/unknown/tampered paths with deterministic fixtures; run frozen A/B requests through real mcode/Paperclip and account for every invocation.
5. Bind review only to its own request/specification/candidate hashes. With no source-bound tool evidence, even approved reviews remain review drafts; TIA/PLCSIM/machine acceptance remains pending.

Knowledge adopted: Obsidian Wiki/自动化开发范式与智能体协作.md distinguishes completion, evidence and acceptance. Single-model reviewers share failure modes; independent sessions do not establish independent model errors.

Root Codex integrates and closes out serially; mcode roles return scoped packets only. No edits to canonical ST, assertions or prior fixtures. Prior retained legacy work keeps its existing owner/acceptance routes.
