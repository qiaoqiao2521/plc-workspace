---
name: siemens-scl-lad-standards
description: "Review Siemens SCL/ST and LAD conventions, naming, typing, optimized blocks and SCL/LAD architecture boundaries in TIA Portal."
---

# Siemens SCL/LAD Standards

Use for conventions, review criteria and architecture boundaries. Concrete FB/FC internals belong to [block patterns](../siemens-scl-block-patterns/SKILL.md); I/O collection, DB strategy and OB1 integration belong to [TIA workflow](../tia-portal-scl-lad-workflow/SKILL.md).

Read the relevant part of [style rules](references/scl-lad-style-rules.md). Distinguish a cited Siemens/IEC requirement, a recommendation, and this project's engineering convention. Check CPU family, firmware/TIA version and project settings before applying version-sensitive advice.

Preferred engineering defaults, subject to the actual customer/project contract:

- Optimized blocks and symbolic access where compatible with external tools/HMI and customer constraints.
- Explicit types, initialization, array bounds, reset/retention behavior and interface checks.
- SCL for algorithms; LAD/FBD for orchestration and online monitoring when that matches the team's design.
- Encapsulated FB/FC logic rather than large raw algorithms in OB1; `CASE` state machines when they clarify state transitions.

Report the applicable rules and highest-risk findings: initialization/state, bounds, interface mismatch and watch/debug visibility. Do not turn stylistic preferences into compulsory rewrites of working code, and do not claim compiler/runtime validation from a standards review alone.
