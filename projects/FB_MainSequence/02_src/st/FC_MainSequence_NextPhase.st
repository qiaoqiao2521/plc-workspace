FUNCTION FC_MainSequence_NextPhase : INT
VAR_INPUT
    xClearReq : BOOL := FALSE;
    xAbortReq : BOOL := FALSE;
    xFaultLatched : BOOL := FALSE;
    iPhaseStat : INT := 0;
    xInvalidPhase : BOOL := FALSE;
    xStepDone : BOOL := FALSE;
    xTimeoutReached : BOOL := FALSE;
    iSuccessPhase : INT := 0;
    xStartReady : BOOL := FALSE;
END_VAR

IF xClearReq THEN
    FC_MainSequence_NextPhase := 0;
ELSIF xFaultLatched OR xInvalidPhase THEN
    FC_MainSequence_NextPhase := 900;
ELSIF xAbortReq THEN
    FC_MainSequence_NextPhase := 0;
ELSIF iPhaseStat = 0 THEN
    IF xStartReady THEN
        FC_MainSequence_NextPhase := 1;
    ELSE
        FC_MainSequence_NextPhase := 0;
    END_IF;
ELSIF iPhaseStat = 900 THEN
    FC_MainSequence_NextPhase := 900;
ELSIF xInvalidPhase THEN
    FC_MainSequence_NextPhase := 900;
ELSIF xStepDone THEN
    FC_MainSequence_NextPhase := iSuccessPhase;
ELSIF xTimeoutReached THEN
    FC_MainSequence_NextPhase := 900;
ELSE
    FC_MainSequence_NextPhase := iPhaseStat;
END_IF;

END_FUNCTION
