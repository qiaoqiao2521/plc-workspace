FUNCTION_BLOCK FB_MainSequence
VAR_INPUT
    xEnable : BOOL := FALSE;
    xEvtStart : BOOL := FALSE;
    xEStop : BOOL := FALSE;
    xStop : BOOL := FALSE;
    xReset : BOOL := FALSE;
    xInitDone : BOOL := FALSE;
    xTransportDone : BOOL := FALSE;
    xFlipDone : BOOL := FALSE;
    xOutputDone : BOOL := FALSE;
    uiStepTimeoutScans : UINT := 8;
END_VAR

VAR_OUTPUT
    iPhase : INT := 0;
    xBeltForward : BOOL := FALSE;
    xBeltReverse : BOOL := FALSE;
    xStartLamp : BOOL := FALSE;
    xResetLamp : BOOL := FALSE;
    xQ1 : BOOL := FALSE;
    xQ2 : BOOL := FALSE;
    xDone : BOOL := FALSE;
    xError : BOOL := FALSE;
    xTimeoutFault : BOOL := FALSE;
    xValid : BOOL := FALSE;
    xBusy : BOOL := FALSE;
    xCommandBusy : BOOL := FALSE;
    xCommandAborted : BOOL := FALSE;
    xTimeoutDiagnostic : BOOL := FALSE;
END_VAR

VAR
    iPhaseStat : INT := 0;
    uiStepTimerStat : UINT := 0;
    xTimeoutFaultStat : BOOL := FALSE;
    xTimeoutDiagnosticStat : BOOL := FALSE;
    xAbortedStat : BOOL := FALSE;
    xEnablePrev : BOOL := FALSE;
    xStartPrev : BOOL := FALSE;
    xResetPrev : BOOL := FALSE;
END_VAR

VAR_TEMP
    iPhasePrev : INT;
    uiStepTimerPrev : UINT;
    xTimeoutFaultPrev : BOOL;
    xDiagnosticPrev : BOOL;
    xAbortedPrev : BOOL;
    xEnableRise : BOOL;
    xStartRise : BOOL;
    xResetRise : BOOL;
    xStopReq : BOOL;
    xResetAccepted : BOOL;
    xClearReq : BOOL;
    xAbortReq : BOOL;
    xInvalidPhase : BOOL;
    xBusyPhase : BOOL;
    xFaultLatched : BOOL;
    xStepDone : BOOL;
    xTimeoutReached : BOOL;
    iPhaseNext : INT;
    uiStepTimerNext : UINT;
    xTimeoutFaultNext : BOOL;
    xDiagnosticNext : BOOL;
    xAbortedNext : BOOL;
    xStartAccepted : BOOL;
    xErrorCore : BOOL;
    xExecAllowed : BOOL;
END_VAR

(* Snapshot persistent internals only; outputs are never used as state. *)
iPhasePrev := iPhaseStat;
uiStepTimerPrev := uiStepTimerStat;
xTimeoutFaultPrev := xTimeoutFaultStat;
xDiagnosticPrev := xTimeoutDiagnosticStat;
xAbortedPrev := xAbortedStat;
xEnableRise := xEnable AND NOT xEnablePrev;
xStartRise := xEvtStart AND NOT xStartPrev;
xResetRise := xReset AND NOT xResetPrev;

(* xEStop is external safety-inhibit feedback, not an F safety function.
   Reset reinitializes a healthy command. Block errors need enable=FALSE. *)
xStopReq := xEStop OR xStop;
xInvalidPhase := FC_MainSequence_InvalidPhase(iPhase := iPhasePrev);
xBusyPhase := FC_MainSequence_BusyPhase(iPhase := iPhasePrev);
xFaultLatched := (iPhasePrev = 900) OR xTimeoutFaultPrev;
xResetAccepted := xEnable AND xResetRise AND NOT xStopReq AND NOT xFaultLatched AND NOT xInvalidPhase;
xClearReq := (NOT xEnable) OR xResetAccepted;
xAbortReq := xStopReq OR xReset;
xStepDone := FC_MainSequence_StepDone(
    iPhase := iPhasePrev,
    xTransportDone := xTransportDone,
    xFlipDone := xFlipDone,
    xOutputDone := xOutputDone
);
xTimeoutReached := FC_MainSequence_TimeoutReached(
    xBusyPhase := xBusyPhase,
    xStepDone := xStepDone,
    uiStepTimerStat := uiStepTimerPrev,
    uiStepTimeoutScans := uiStepTimeoutScans
);

iPhaseNext := FC_MainSequence_NextPhase(
    xClearReq := xClearReq,
    xAbortReq := xAbortReq,
    xFaultLatched := xFaultLatched,
    iPhaseStat := iPhasePrev,
    xInvalidPhase := xInvalidPhase,
    xStepDone := xStepDone,
    xTimeoutReached := xTimeoutReached,
    iSuccessPhase := FC_MainSequence_SuccessPhase(iPhase := iPhasePrev),
    xStartReady := xEnable AND xInitDone AND xStartRise
);
uiStepTimerNext := FC_MainSequence_NextTimer(
    xResetReq := xClearReq OR xAbortReq,
    iPhaseStat := iPhasePrev,
    xInvalidPhase := xInvalidPhase,
    xStepDone := xStepDone,
    xTimeoutReached := xTimeoutReached,
    xBusyPhase := xBusyPhase,
    uiStepTimerStat := uiStepTimerPrev,
    uiStepTimeoutScans := uiStepTimeoutScans
);
xTimeoutFaultNext := FC_MainSequence_NextTimeoutFault(
    xClearReq := xClearReq,
    xAbortReq := xAbortReq,
    xTimeoutReached := xTimeoutReached,
    xTimeoutFaultStat := xTimeoutFaultPrev
);
xStartAccepted := (iPhasePrev = 0) AND (iPhaseNext = 1);

(* Current errors and diagnostic history have separate lifetimes. *)
IF xEnableRise THEN
    xDiagnosticNext := xTimeoutFaultNext;
ELSE
    xDiagnosticNext := xDiagnosticPrev OR xTimeoutFaultNext;
END_IF;
IF xBusyPhase AND (xClearReq OR xAbortReq) THEN
    xAbortedNext := TRUE;
ELSIF (NOT xEnable) OR xResetAccepted OR xStartAccepted THEN
    xAbortedNext := FALSE;
ELSE
    xAbortedNext := xAbortedPrev;
END_IF;
xErrorCore := FC_MainSequence_InvalidPhase(iPhase := iPhaseNext) OR (iPhaseNext = 900);
xExecAllowed := xEnable AND NOT xAbortReq AND NOT xErrorCore;

(* Commit once. Consume input edges on every call, even while inhibited. *)
iPhaseStat := iPhaseNext;
uiStepTimerStat := uiStepTimerNext;
xTimeoutFaultStat := xTimeoutFaultNext;
xTimeoutDiagnosticStat := xDiagnosticNext;
xAbortedStat := xAbortedNext;
xEnablePrev := xEnable;
xStartPrev := xEvtStart;
xResetPrev := xReset;

(* DA008: each output is assigned once and no output is read. *)
iPhase := iPhaseNext;
xError := xErrorCore;
xTimeoutFault := xTimeoutFaultNext;
xBeltForward := xExecAllowed AND ((iPhaseNext = 1) OR (iPhaseNext = 3));
xBeltReverse := FALSE;
xStartLamp := xExecAllowed AND ((iPhaseNext = 2) OR (iPhaseNext = 3));
xResetLamp := xExecAllowed AND (iPhaseNext = 0);
xQ1 := xExecAllowed AND (iPhaseNext = 2);
xQ2 := xExecAllowed AND (iPhaseNext = 3);
xDone := xExecAllowed AND (iPhasePrev = 3) AND xOutputDone AND (iPhaseNext = 1);
xValid := xEnable AND NOT xErrorCore;
xBusy := xEnable AND NOT xErrorCore;
xCommandBusy := xExecAllowed AND FC_MainSequence_BusyPhase(iPhase := iPhaseNext);
xCommandAborted := xAbortedNext;
xTimeoutDiagnostic := xDiagnosticNext;

END_FUNCTION_BLOCK
