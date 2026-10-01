# Siemens SCL/LAD Style Rules

Use this reference when the user asks for standards, conventions, review criteria, or conversion rules for Siemens SCL/LAD work.

## Source boundary

This file summarizes public Siemens guidance and IEC-oriented project conventions. It is not a verbatim standard.

Primary references used for this summary:

- Siemens `Programming Guideline for S7-1200/1500`
- Siemens `Programming style guide for SIMATIC S7-1200/S7-1500`

Interpretation rule:

- Treat Siemens "Rule" items as default project constraints unless the user provides stronger customer or plant rules.
- Treat Siemens "Recommendation" items as defaults that may be overridden for readability or project fit.
- Treat "IEC 61131-3" here as the language family and typing model boundary, not as a quote of the standard text.

## Default project posture

- Prefer `S7-1200` or `S7-1500` with optimized blocks.
- Prefer fully symbolic access.
- Turn on IEC-conformant checks for new blocks.
- Keep array-bound checks enabled.
- Keep EN/ENO evaluation enabled unless there is a measured reason to disable it.
- If the user did not specify otherwise, assume English identifiers/comments and international mnemonics.
- Treat explicit initialization as mandatory for arrays, UDTs, and retained state.
- Treat mixed programming (`SCL core + LAD/FBD shell`) as the default maintainable architecture.

## Language split

Use SCL for:

- math, scaling, filtering, PID, state machines, sequences
- loops, arrays, records/UDTs, reusable algorithms
- code that should stay hardware-independent

Use LAD for:

- OB1 orchestration and network-by-network execution visibility
- simple permissives/interlocks that operators and commissioning staff inspect online
- block calls, instance wiring, and scan-order documentation
- visible start/stop/permissive/alarm paths that maintenance staff must debug quickly

Do not force dense algorithmic logic into LAD just because the project uses LAD in OB1.
Do not place dense SCL directly into the main OB just because SCL can express it.

## Block and data model

- Use `FC` for pure computation or mapping helpers with no retained state.
- Use `FB` for logic with memory or lifecycle state; state belongs in `VAR_STAT` and therefore in an instance DB.
- Use UDTs to decouple logic from physical I/O and HMI naming churn.
- Keep `%I/%Q/%IW/%QW` usage in the mapping layer only.
- Prefer explicit interfaces over hidden global dependencies.
- Keep state-machine state visible and reviewable; prefer a single state variable and `CASE`.
- Be cautious with timer arrays and similar Siemens-specific patterns. If the platform/pattern is ambiguous, fall back to wrapper FB/UDT structures instead of assuming `ARRAY OF TON` is acceptable.

## Naming and interface discipline

- Keep object names stable and descriptive.
- Prefer consistent prefixes/suffixes across the project.
- Use `VAR_INPUT`, `VAR_OUTPUT`, `VAR_IN_OUT`, `VAR_TEMP`, `VAR_STAT` intentionally and explain the choice in generated output.
- Avoid a generic `mode` parameter that switches many unrelated behaviors inside one block.
- Prefer descriptive variable prefixes that expose intent (`b`, `x`, `i`, `di`, `do`, `ai`, `ao`, etc.) if the project already uses them.
- Initialize what you declare; do not rely on "probably zero on startup" as a coding standard.

## Performance and maintainability rules

- Prefer optimized blocks and symbolic access end to end.
- Avoid deep call hierarchies without a reason.
- Avoid `JMP`/label-style flow unless required by legacy code.
- Use `DInt` for loop/index variables unless the project enforces something else.
- Cache repeated array or I/O accesses in temp variables when the same element is used multiple times in one cycle.
- Prefer simple boolean expressions over verbose `IF ... ELSE` when behavior is identical.
- Fix the first compile error first; later syntax markers are often cascade noise.
- Assume watch tables, monitor mode, and online trace are part of the design, not a post-hoc debugging convenience.

## Conversion rules between SCL and LAD

When converting requirements or pseudo-code to PLC structure:

- Put plant-independent logic in SCL blocks.
- Put plant-dependent wiring and network sequencing in LAD.
- Convert a long LAD rung into SCL only when it is algorithmic, repetitive, or array-heavy.
- Convert SCL back into LAD only for the visible call layer or for simple boolean gating.
- If a maintenance electrician must diagnose it online during a fault, bias that part toward LAD/FBD or at least expose the state clearly through LAD-visible tags.

When the user says "梯形图标准":

- interpret it as a request for readable rung/network structure, explicit permissives, visible outputs, and commissioning-friendly online monitoring
- not as a demand to express every algorithm in ladder form

## What to state explicitly in every answer

- CPU family/version assumption
- optimized vs non-optimized access assumption
- instance DB vs global DB strategy where relevant
- which parts are standards-driven and which parts are engineering convention
- initialization strategy
- online debug strategy (watch table / monitor / breakpoint expectations)

## Useful Siemens links

- Programming guideline:
  `https://support.industry.siemens.com/cs/document/81318674/programming-guidelines-and-programming-styleguide-for-simatic-s7-1200-and-s7-1500-and-wincc-(tia-portal)`
- Style guide:
  `https://support.industry.siemens.com/cs/ww/en/view/109478084`
