# PLC semantics v1

## Goal
Converge FB_MainSequence scan semantics, align authoritative ST and checker projections, and verify scan-boundary behavior. User request: 收敛 PLC 语义.

## Scope
- Preserve normal 0→1→2→3→1 and existing I/O names/types; document appended outputs and breaking lifecycle migration.
- Correct mixed old/new timer decisions.
- Resolve Stop/Reset/fault and Enable policy before changing dependent behavior.
- Generate or check projections against one source, add executable scan tests and exact properties.
- Add minimal SpecMesh entry points for agent continuity.

## Non-goals
No PLC/network/device writes, TIA deployment, platform migration, full OpenPLC service recovery, or broad toolchain rewrite. Preserve existing staged mode changes and untracked assets. Do not commit/push without a separate instruction.

## Phases
1. Official-source mapping and v0.3 scan contract — complete
2. Canonical core, command lifecycle and generated projections — complete
3. Compiled-ST, differential, full native example and formal checks — complete
4. Specs, interface migration, continuity and source-bound evidence — complete

## Next Step
The requested abstract-core implementation is complete. Further work is actual machine/TIA integration once its assets and versions are available; no automatic platform migration or deployment.

## Acceptance
- Continuous Enable, error/diagnostic lifetime and edge consumption are executable requirements.
- Twenty-four compiled-ST tests include 160 control combinations and 5,000 differential calls.
- Eight tooling tests pass; 26 formal assertions pass with all UINT timeout values.
- The complete native OpenPLC example passes at call 50; a real false assertion is rejected with exit 1.
- Current evidence is projects/FB_MainSequence/04_reports/semantics/v0.3/; Siemens/full-service acceptance remains unverified.
