FUNCTION FC_MainSequence_InvalidPhase : BOOL
VAR_INPUT
    iPhase : INT := 0;
END_VAR

FC_MainSequence_InvalidPhase := (iPhase < 0) OR ((iPhase > 3) AND (iPhase <> 900));

END_FUNCTION
