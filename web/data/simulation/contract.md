# Composable PLC simulation v1

This is a bounded, synthetic teaching and engineering-check environment. It is
not a model of the user's machine, a Siemens runtime, a safety function, or a
physical dynamics acceptance result. Existing PLC source and contracts stay intact.

## Execution and composition

Every step samples the assembled scene's sensor values, calls one persistent
compiled ST FB exactly once, publishes its outputs, then advances each plant
component once. A device's `step` is normalized travel per invocation, not m/s.
Rendering never advances this clock. Controls remain at their written level until
changed; two consecutive Start=true calls are one held input, not two edges.

Ports are typed BOOL or REAL. Connections and PLC bindings have one writer per
input, and the device graph must be acyclic. Commands and feedback are separate.
Motor, conveyor, photoeye and cylinder faults change the plant or its feedback,
not the PLC program. Sessions have independent PLC and plant state.

## Synthetic conveyor-pusher-v1 contract

`FB_TransferPusher` has BOOL inputs Enable, Start, Stop, Reset, AtEnd, Extended,
Retracted. Outputs Motor, Extend, Retract, Busy, Done, Error, TimeoutFault are BOOL;
State and WaitCount are UINT. The first invocation may consume a rising Start.

States: 0 idle, 1 conveying, 2 extending, 3 retracting, 900 latched fault. The
initial cylinder is retracted. Enabled idle starts only on a fresh Start edge
with Retracted feedback. Conveyor arrival stops Motor and starts Extend; Extended
stops Extend and starts Retract; Retracted stops Retract and emits Done for one
invocation. A normal call advances at most one phase. Entry is not a waiting call;
each phase allows 11 incomplete waiting calls and faults on the 12th. Completion
wins at that deadline. Motor, Extend and Retract are mutually exclusive.

Stop or Enable=false revoke actions on the current invocation and cancel the
healthy sequence to idle. Neither clears an existing fault. Every invocation
consumes Start/Reset edges, including inhibited calls, so releasing Stop or
re-enabling with held Start does not restart. Reset is accepted only on a rising
edge when enabled, Stop=false and Start=false; it clears the fault and returns to
idle without motion. Holding Reset inhibits motion and does not repeat reset.
Reset does not move a physical cylinder home: a new Start still needs Retracted.
Conflicting cylinder end feedback raises Error; an invalid state raises Error.
These faults do not falsely set TimeoutFault. This is not an emergency-stop or
F-safety implementation. Cold reconstruction is not a Reset input or a retention
test.

## Other explicitly separate profiles

* `conveyor-8-demo-v1` runs the historical, unchanged eight-wait-call example.
* `conveyor-12-v1` uses the existing twelve-wait-call contract and its original
  Enable/Reset semantics. The bundled twelve-call example is a separate source
  copy; it does not replace the historical candidate.
* `latch-start-stop-v1` retains the existing synthetic BOOL latch contract.

An unknown profile or incompatible interface is rejected. A new scene does not
inherit another scene's evidence. Independent case expectations are authored
separately from the control program; case results bind source, scene and contract
identities and never upgrade the generation workspace's acceptance. A wrong
eight-call candidate labeled as twelve-call must fail the timeout case.

## Scope and fault isolation

The native compiler and every persistent FB run in a disposable subprocess;
per-call watchdogs retain the completed trace and terminate a stuck worker.
Each step batch also has a 30-second wall-clock budget (with the existing two-second per-call limit); exhausting either halts only that session, preserves completed scans and yields unknown rather than a partial pass.
This limits accidental hangs and is not a hostile-code security sandbox.
Vendor addressing/pragmas, extra programs, time-based function blocks and
interfaces outside these profiles are rejected. No real-time TON, fieldbus,
retention, LAD execution, TIA/PLCSIM or real-device acceptance is claimed here.
