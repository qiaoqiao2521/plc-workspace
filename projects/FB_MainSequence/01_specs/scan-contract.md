# FB_MainSequence scan contract v0.3 — continuous enable

Status: implemented abstract-core contract; Siemens engineering acceptance unverified.
Interface version: 0.2.0 (behavior changes, five appended outputs and changed instance layout).
Supersedes the v0.2 start-only Enable / stop-clears-fault candidate.

## Authority and scope

`02_src/st/*.st` is authoritative; checker/export copies are generated. See repository `docs/SCL_STANDARD_BASELINE.md` for official references and the language / CPU / interface / safety distinction.

This block applies DA008 output ownership and DA011 continuous-enable/error/diagnostic lifecycles. Its sequencing command, healthy-command Reset and cycle marker are project extensions. It is not a complete PLCopen compliance claim, imported LGF template or F safety function. xEStop=TRUE is external inhibit feedback; actual safety stopping and acknowledgment belong to the safety layer. Do not wire it as ESTOP1's oppositely polarized E_STOP input.

## Invocation ownership

One cyclic caller invokes one instance once per logical scan, including when Enable is FALSE. Do not gate the call with EN/IF to simulate disable: an uncalled FB cannot revoke outputs or consume edges. Multiple calls and competing writers are outside the contract. Persistent state belongs to the instance, never to its output fields.

A bounded call snapshots internal state, derives conditions once, computes next values, commits internals and publishes each output once without reading outputs. Commit assignments are sequential, not hardware-atomic. Observe after the owning call returns; physical I/O timing and other OBs need separate integration.

## Continuous block lifecycle

- Enable FALSE: Init, timer zero, current Error/TimeoutFault cleared, Valid/Busy FALSE and all action outputs off. A canceled busy command reports CommandAborted for this call.
- Enable TRUE: Valid/Busy TRUE unless a block error is latched. This includes healthy idle and stop-inhibited idle. Busy describes the continuous FB; CommandBusy describes an executing sequence.
- Enable rising: start a new diagnostic session and clear old timeout history; newly detected faults in that invocation remain recorded.
- Enable alone never starts motion: fresh Start edge and InitDone are required.
- Latched block errors hold phase 900 while enabled, including through Stop/EStop/Reset. Disable clears current error; subsequent enable rise clears historical timeout diagnostics. This follows the fatal-error lifecycle of the chosen enable profile.

## Commands and priority

Phases remain 0 Init, 1 Transport, 2 Flip, 3 Output, 900 Error.

1. Disable clears current execution/error state regardless of other inputs.
2. While enabled, existing faults or invalid phases override command transitions. Stops never acknowledge faults.
3. Healthy Reset is accepted only on a rising edge after Stop/EStop release; it returns Init and cancels a running command. Reset is a business reinitialization, not a block-error acknowledgment bypass.
4. Stop/EStop or held Reset inhibit actions and normal transitions. Healthy sequences return Init; faults remain Error. A canceled step does not produce a new timeout on that invocation.
5. Otherwise Init + InitDone + Start rising enters Transport; busy states advance at most once per call, 1→2→3→1. Current-phase completion wins at the timeout deadline.

Start/Reset edge memories update on every call, including disabled/stopped/faulted calls. Ignored requests are consumed, not queued. Holding Start through stop/reset/re-enable cannot restart. Stop release alone does not resume the interrupted step.

TimeoutFault is the current timeout reason. TimeoutDiagnostic records historical timeout information: Stop/Reset/disable do not erase it; a new enable session clears it. Invalid phase raises Error without falsely reporting a timeout.

## Outputs and command lifecycle

- BeltForward: executing phase 1/3; Q1: phase 2; Q2: phase 3; StartLamp: phase 2/3.
- BeltReverse is constant FALSE; this does not establish a real reversing-drive interlock.
- ResetLamp: enabled healthy Init, without Stop/EStop/Reset held. It indicates idle/ready, not a safety acknowledgment request.
- CommandBusy: enabled, uninhibited healthy phase 1/2/3.
- CommandAborted: set when a busy command is canceled by disable/Stop/EStop/Reset; retained while enabled until accepted Start or healthy Reset. Disable cancellation is visible for one call, then clears on the next disabled call. It is not an error indication.
- Done: existing one-call Output→Transport cycle marker, not DA012 terminal Done. The continuous command remains busy across the marker.
- Valid and Error are mutually exclusive. Busy is distinct from CommandBusy.

Completion inputs are current-operation levels. Multiple levels cannot cascade within one call, but stale levels in later calls can advance later steps. Real child command/Busy/Done handshakes remain an integration responsibility.

## Scan-count timeout

UINT 0..65535 counts calls, not milliseconds. Entry sets timer=0. On later waiting calls, threshold N>0 expires at previousTimer+1>=N: calls 1..N-1 hold, call N commits Error, timeout reason, diagnostic and output revocation. N=1 expires on the first waiting call. Zero disables counting and keeps timer zero.

The threshold is live each call: decreasing it may expire immediately, increasing it extends the wait, and zero disables it. Completion still wins. This is explicit continuous-update behavior, not frozen-at-execute parameters. TON/wall-clock timing belongs to Siemens integration.

## Migration and evidence

Existing I/O names/types remain; xValid, xBusy, xCommandBusy, xCommandAborted and xTimeoutDiagnostic are appended. Behavioral changes are breaking: maintain Enable during operation, recover errors through an observed disabled call and provide fresh Start edges. An HMI Reset that previously cleared errors directly needs caller-side explicit disable/re-enable handling; such a caller is not supplied here.

Instance layout changed: TIA recompilation/DB migration, startup/download and retention need separate verification. Native ST tests and formal checks are not TIA/PLCSIM, full OpenPLC-service or machine acceptance. Preserve old proof as historical and use the v0.3 source-bound report for current behavior.
