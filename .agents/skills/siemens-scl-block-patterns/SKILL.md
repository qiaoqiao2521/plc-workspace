---
name: siemens-scl-block-patterns
description: "Design reusable Siemens SCL FB/FC interfaces and internals: state, reset, cycle time, timers, arrays and control-block patterns."
---

# Siemens SCL Block Patterns

Use for concrete block examples and interface/internal design. Coding conventions and review criteria belong to [SCL/LAD standards](../siemens-scl-lad-standards/SKILL.md); whole-project I/O, DB and OB1 integration belongs to [TIA project workflow](../tia-portal-scl-lad-workflow/SKILL.md).

Read [block patterns](references/block-patterns.md) for the requested pattern, not as an obligation to redesign the whole project.

Preserve the engineering boundaries:

- FB for retained cycle-to-cycle state; FC for pure calculation/mapping. State and reset behavior must be explicit.
- Pass typed signals/UDTs through interfaces; keep physical I/O mapping outside reusable logic.
- Make scan period, timer behavior, initialization, bounds and state transitions explicit where they affect behavior.
- For control/PID examples, state units, saturation and anti-windup assumptions; do not introduce a controller merely because a pattern exists.
- Provide a block/interface summary, the needed SCL example and a watch/debug strategy. Source syntax review is not TIA compilation or a PLC runtime test.

Use the current CPU family, TIA dialect and project properties when available. For a conceptual pattern, label assumptions instead of demanding an entire I/O list first.
