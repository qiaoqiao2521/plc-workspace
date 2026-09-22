FUNCTION FC_MainSequence_NextTimeoutFault : BOOL
VAR_INPUT
    xClearReq : BOOL := FALSE;
    xAbortReq : BOOL := FALSE;
    xTimeoutReached : BOOL := FALSE;
    xTimeoutFaultStat : BOOL := FALSE;
END_VAR

IF xClearReq THEN
    FC_MainSequence_NextTimeoutFault := FALSE;
ELSIF xAbortReq THEN
    FC_MainSequence_NextTimeoutFault := xTimeoutFaultStat;
ELSE
    FC_MainSequence_NextTimeoutFault := xTimeoutFaultStat OR xTimeoutReached;
END_IF;

END_FUNCTION
