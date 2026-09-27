# Formal properties — v0.3

The exact assertions are in `03_checks/plcverif/assertions.scl`, evaluated at the end of each invocation. The formal result checks their conjunction from an initialized instance, with unrestricted BOOL inputs and a fresh UINT timeout each call. Internal derived conditions are complemented by independent compiled-ST boundary tests; this is not complete PLCopen, safety or Siemens acceptance.

- P1_BeltMutualExclusion
- P2_DisabledLifecycle
- P3_InhibitDeenergizes
- P4_StopPreservesFault
- P5_HealthyStopInit
- P6_AcceptedReset
- P7_FaultHolds
- P8_StartRequired
- P9_TransportCompletes
- P10_FlipCompletes
- P11_OutputCompletes
- P12_BusyHolds
- P13_TimeoutCommitsTogether
- P14_FaultPhaseConsistent
- P15_ErrorDeenergizes
- P16_InvalidPhase
- P17_TimerReset
- P18_DoneTransition
- P19_DiagnosticNewSession
- P20_DiagnosticRetained
- P21_ValidBusy
- P22_CommandBusy
- P23_CommandAbort
- P24_NoEarlyFault
- P25_TimeoutReasonHeld
- P26_DiagnosticRecordsFault
- P27_EdgeMemoriesTrackInputs
- P28_AbortClearedOnAcceptedStart
- P29_NoEarlyExpiration
- P30_DeadlineObligation
- P31_WaitingCallCountsOne
- P32_ZeroThresholdKeepsTimerZero

P2/P19/P20 distinguish current-error and diagnostic lifetimes. P4/P7/P25 prohibit stop/reset from acknowledging an enabled block error. P8 requires a fresh start edge. P21 distinguishes continuous FB health from P22 command execution. P1 has limited scope because reverse is always FALSE. Native tests separately cover illegal-state injection, 160 control combinations, output tampering and 5,000 differential calls.

P27–P31 were added after the 2026-09-22 adversarial variant pass proved that edge consumption (P27), CommandAborted clearing on an accepted Start (P28) and the absolute scan-count timing semantics (P29–P31) were pinned only by native tests. After the 2026-09-23 independent review (whose late-by-one-at-threshold-31 variant passed every then-shipped layer), P29–P31 are derived from the contract side only — the threshold input, the prior timer and the completion levels; `xTimeoutReached` never gates a check. P29 forbids early expiration, P30 obliges the deadline commit (phase 900, error and timeout reason) for every positive threshold at `prevTimer+1 >= N`, and P31 requires a waiting call to count exactly one. The deadline is written overflow-free as `prev < 65535 AND prev >= N-1`. Reachability boundary of the `prev = 65535` exclusion (corrected after the 2026-09-23 re-review): a busy step can never enter a scan with prior timer 65535 — with `N = 0` the timer is held at zero ("zero disables counting and keeps timer zero"), and with `N > 0` the deadline expires at prior timer `N-1 <= 65534` at the latest — so the exclusion is vacuous on contract-obeying execution and does not establish behavior for test-only injected timer values. Such injected states and cross-tool overflow behavior require separate checks; this initialized-state proof makes no claim about them. Invalid-phase robustness stays native-only: corrupt phases are unreachable from an initialized instance, so a related formal assertion would be vacuous there. P32 was added after the 2026-09-26 adversarial round: a threshold-switched-to-zero variant that froze the prior timer passed every then-shipped layer; P32 pins "zero disables counting and keeps timer zero" for busy waiting calls. The reset-acceptance edge obligation (contract C3) stays native-only, like invalid-phase robustness: assertions evaluate at end of cycle where the edge memory is already committed to this scan's input, and the only temp encoding the previous input (xResetRise) is exactly what an edge-to-level mutant redefines, so that attempted property could not independently check the edge under the current end-of-cycle instrumentation; the native regression pins it instead. `03_checks/plcverif/required-assertions.txt` pins each reviewed assertion line verbatim (ID and expression; its header states the update rule), and the formal gate refuses a source that does not contain every pinned line — deleting, renaming, or rewriting an assertion while keeping its ID (an all-TRUE rewrite passed the solver in the 2026-09-27 review) blocks verification before any solver run. Extra assertion lines remain tolerated: they cannot satisfy a violated required assertion, which is why the appended-FALSE negative control still exercises the solver-rejection path.
