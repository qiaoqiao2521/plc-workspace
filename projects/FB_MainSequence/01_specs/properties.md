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

P2/P19/P20 distinguish current-error and diagnostic lifetimes. P4/P7/P25 prohibit stop/reset from acknowledging an enabled block error. P8 requires a fresh start edge. P21 distinguishes continuous FB health from P22 command execution. P1 has limited scope because reverse is always FALSE. Native tests separately cover illegal-state injection, 160 control combinations, output tampering and 5,000 differential calls.
