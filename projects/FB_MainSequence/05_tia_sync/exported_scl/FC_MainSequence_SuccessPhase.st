FUNCTION FC_MainSequence_SuccessPhase : INT
VAR_INPUT
    iPhase : INT := 0;
END_VAR

CASE iPhase OF
    1:
        FC_MainSequence_SuccessPhase := 2;
    2:
        FC_MainSequence_SuccessPhase := 3;
    3:
        FC_MainSequence_SuccessPhase := 1;
    ELSE
        FC_MainSequence_SuccessPhase := iPhase;
END_CASE;

END_FUNCTION
