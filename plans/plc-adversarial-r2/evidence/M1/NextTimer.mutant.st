FUNCTION FC_MainSequence_NextTimer : UINT
VAR_INPUT
    xResetReq : BOOL := FALSE;
    iPhaseStat : INT := 0;
    xInvalidPhase : BOOL := FALSE;
    xStepDone : BOOL := FALSE;
    xTimeoutReached : BOOL := FALSE;
    xBusyPhase : BOOL := FALSE;
    uiStepTimerStat : UINT := 0;
    uiStepTimeoutScans : UINT := 0;
END_VAR

IF xResetReq OR (iPhaseStat = 0) OR (iPhaseStat = 900) OR xInvalidPhase OR xStepDone OR xTimeoutReached THEN
    FC_MainSequence_NextTimer := 0;
ELSIF xBusyPhase AND (uiStepTimeoutScans > 0) THEN
    FC_MainSequence_NextTimer := uiStepTimerStat + 1;
ELSIF xBusyPhase THEN
    FC_MainSequence_NextTimer := uiStepTimerStat;
ELSE
    FC_MainSequence_NextTimer := 0;
END_IF;

END_FUNCTION
