FUNCTION FC_MainSequence_StepDone : BOOL
VAR_INPUT
    iPhase : INT := 0;
    xTransportDone : BOOL := FALSE;
    xFlipDone : BOOL := FALSE;
    xOutputDone : BOOL := FALSE;
END_VAR

CASE iPhase OF
    1:
        FC_MainSequence_StepDone := xTransportDone;
    2:
        FC_MainSequence_StepDone := xFlipDone;
    3:
        FC_MainSequence_StepDone := xOutputDone;
    ELSE
        FC_MainSequence_StepDone := FALSE;
END_CASE;

END_FUNCTION
