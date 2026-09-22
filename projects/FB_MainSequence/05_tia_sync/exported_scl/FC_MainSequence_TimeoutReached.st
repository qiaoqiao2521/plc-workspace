FUNCTION FC_MainSequence_TimeoutReached : BOOL
VAR_INPUT
    xBusyPhase : BOOL := FALSE;
    xStepDone : BOOL := FALSE;
    uiStepTimerStat : UINT := 0;
    uiStepTimeoutScans : UINT := 0;
END_VAR

FC_MainSequence_TimeoutReached :=
    xBusyPhase AND
    (NOT xStepDone) AND
    (uiStepTimeoutScans > 0) AND
    ((uiStepTimerStat + 1) >= uiStepTimeoutScans);

END_FUNCTION
