FUNCTION FC_MainSequence_BusyPhase : BOOL
VAR_INPUT
    iPhase : INT := 0;
END_VAR

FC_MainSequence_BusyPhase := (iPhase = 1) OR (iPhase = 2) OR (iPhase = 3);

END_FUNCTION
