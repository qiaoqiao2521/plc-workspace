# Progress

Current: Requested v0.3 abstract-core implementation complete.

Done: Reproduced three legacy behavior failures, separated persistent internals from outputs, implemented continuous enable and distinct error/diagnostic lifecycle, consumed command edges, synchronized all projections and specifications. Native scan tests: 24 passed, including 160 input-priority combinations and 5,000 differential invocations. Tooling tests: 4 drift + 4 verdict passed. Formal: 26 assertions satisfied over the full UINT timeout domain. Complete native OpenPLC example: passed at call 50. Intentionally false formal assertion: rejected, gate exit 1.

Migration: Interface 0.2.0 appends five outputs and changes instance layout. Maintain Enable during operation; clear block errors through disable, then re-enable. Reset only reinitializes healthy commands. Read scan-contract.md before updating callers.

Remaining external acceptance: actual Main/child FB handshakes and safety interface, TIA compile/import, instance DB migration, restart retention, PLCSIM and machine validation. Full OpenPLC service and legacy gate recovery are separate.

Evidence: projects/FB_MainSequence/04_reports/semantics/v0.3/. Prior v0.2 evidence is historical. No commit/push/deployment. Four pre-existing staged executable-mode changes preserved; source assets were already untracked before this work.

Next: Hand off the implemented core and migration notes; do not reopen the superseded preference questionnaire.
