# State machine — v0.3

See `scan-contract.md` for authoritative priority, edge consumption and lifecycle rules. Observations are at the end of the owning FB call.

| Phase | Healthy execution outputs | Normal transition |
|---|---|---|
| 0 Init | ResetLamp if enabled and uninhibited | Fresh Start + InitDone → 1 |
| 1 Transport | BeltForward | TransportDone → 2 |
| 2 Flip | StartLamp, Q1 | FlipDone → 3 |
| 3 Output | BeltForward, StartLamp, Q2 | OutputDone → 1; Done marks this cycle |
| 900 Error | No action outputs | Disable → 0; Reset/Stop/EStop do not acknowledge it |

Disable returns any phase to Init, clearing the current error and timer. Enabled invalid phase produces Error. Stop/EStop cancel healthy busy phases to Init, preserve Error and revoke actions. Healthy Reset rising returns Init, provided stop feedback is absent. Held Reset inhibits normal transitions. Any canceled step loses its timer/progress; release never resumes that step.

Completion wins at a timeout deadline only when no cancellation/inhibit/error overrides normal execution. Otherwise each call holds or advances at most one normal phase. Continuous flow is 0→1→2→3→1; this is not a DA012 one-shot job.

TimeoutDiagnostic is historical and may remain TRUE while disabled Init reports no current Error. Conversely invalid phase can produce Error without TimeoutFault. These combinations are intentional, not inconsistent state.
