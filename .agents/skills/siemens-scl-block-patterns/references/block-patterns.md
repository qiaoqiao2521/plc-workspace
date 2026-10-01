# Siemens SCL Block Patterns

Use this reference when the user asks for practical SCL block structure and reusable coding patterns.

Primary public reference used for this summary:

- `OttoMeister/Siemens-Tia-Portal-PID-Controller`

## Practical patterns worth reusing

- external source import is a first-class workflow in TIA projects
- reusable control logic should expose a compact, understandable interface
- reset handling must be explicit when retained state or integrators exist
- cycle time or elapsed time handling must be explicit for dynamic algorithms
- logic should not depend on hidden global data if it is meant to be portable
- arrays, timers, and state variables should be structured so that online debugging remains possible
- the block should fit a mixed-programming architecture: SCL internals, LAD-visible shell

## Interface shaping

Prefer interfaces that make these visible:

- process input / measured value
- setpoint or command
- gains or configuration
- reset / enable / stop semantics
- output value
- status or diagnostic values if commissioning needs them
- a small set of watch-table-friendly internals when the block is expected to be commissioned online

## State handling

Use `FB` when the algorithm needs:

- retained controller state
- filters with memory
- sequence state
- edge/history values

Keep state reset rules explicit:

- what `Reset` clears
- what remains retained
- what happens when the loop is interrupted
- what first-scan or startup initialization does

Prefer `FC` when:

- the logic is pure scaling, conversion, limit checking, or formatting
- no retained state is required
- the result should be deterministic from current inputs only

## Cycle time handling

For dynamic blocks, document:

- expected call rate
- whether elapsed time is measured or passed in
- valid cycle-time range
- what happens when cycle time is invalid
- whether the CPU family changes the debug strategy (`S7-1500` breakpoint-capable vs weaker `S7-1200` debugging)

## State-machine pattern

For sequences and device modes:

- prefer one explicit state variable
- prefer `CASE` over long nested `IF/ELSIF`
- include a default/illegal-state branch
- expose current state and last fault/state cause in status outputs if operators will inspect it

## Timer and array pattern

Do not assume every Siemens pseudo-type composes cleanly in arrays.

When per-channel timing is required:

- use a wrapper structure or dedicated FB per channel when direct timer arrays are awkward or unsupported
- keep timer intent explicit in the interface and status
- avoid hiding timer state in opaque temporary logic that cannot be monitored online

## Initialization pattern

For arrays, UDTs, and retained state:

- define startup values explicitly
- define reset values explicitly
- if bulk initialization is needed, use a loop in startup/reset logic rather than relying on implied defaults
- say whether initialization belongs in startup OB, block init path, or explicit reset command

## External source workflow

For source-based delivery, prefer this instruction pattern:

1. place `.scl` files under `External source files`
2. run `Generate blocks from source`
3. verify generated interfaces and instance DB behavior
4. verify the generated block still matches the intended mixed architecture (`SCL block internals`, `LAD call layer`, `clear reset/init strategy`)

Use this workflow when the user wants portable source artifacts rather than screenshots or manual clicking instructions.
