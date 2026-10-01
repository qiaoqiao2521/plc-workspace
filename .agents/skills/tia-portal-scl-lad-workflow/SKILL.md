---
name: tia-portal-scl-lad-workflow
description: "Plan and integrate a Siemens TIA PLC project from hardware/I/O and block properties through reusable SCL FC/FB, DB strategy and LAD calls in OB1."
---

# TIA Portal SCL/LAD Project Workflow

Use for an integrated PLC project, not an isolated syntax question. Keep reusable SCL logic independent of physical I/O and make its LAD call/DB mapping easy to inspect online.

## Establish the project contract

Recover existing facts before asking: CPU family/model, relevant firmware/TIA version, optimized-access policy, DI/DO/AI/AO tags and addresses, electrical meaning, analog raw/engineering ranges, interlocks, alarms and startup/failure behavior.

Missing physical I/O does not prevent an interface-only draft: use neutral typed signals/UDTs and label the unbound mapping. Do not invent physical addresses or output permissions. Before hardware execution, the real mapping, scaling, interlocks and operating limits must be resolved.

## Build the integration

1. Confirm the hardware and I/O contract with [I/O and properties checklist](references/io-and-properties-checklist.md) where details are needed: debounce/filtering, sample/update rate, wire-break/out-of-range handling, block access and retention/initial values.
2. Choose FC for pure mapping/conversion and FB for stateful logic. Keep physical `%I/%Q/%IW/%QW` access in the mapping layer, not reusable control blocks. Make Input/Output/InOut, FB static state and temporary variables explicit; follow the actual TIA source syntax.
3. Use [SCL block templates](references/scl-block-templates.md) for the required interfaces. For a deeper internal pattern use [block patterns](../siemens-scl-block-patterns/SKILL.md); for a standards review use [SCL/LAD standards](../siemens-scl-lad-standards/SKILL.md).
4. Integrate OB1/Main in readable LAD networks where the project uses that style: mapping → logic → outputs. State how each FB gets its instance DB, what belongs in shared/global DBs, and how formal parameters bind to real tags/DB fields.

Produce the necessary block/interface list, SCL source, OB1 call plan and DB/access assumptions. Mark unbound I/O and unverified compiler/PLC behavior. TIA import/compile, online watch/trace and safe physical behavior are different acceptance stages; source generation alone proves none of the latter.
