(* OpenPLC-only test driver. Core definitions are generated from 02_src/st. *)
PROGRAM PLC_PRG
VAR
    fbMain : FB_MainSequence;
    xEnableSim : BOOL := TRUE;
    xEvtStartSim : BOOL := FALSE;
    xEStopSim : BOOL := FALSE;
    xResetSim : BOOL := FALSE;
    xInitDoneSim : BOOL := TRUE;
    xTransportDoneSim : BOOL := FALSE;
    xFlipDoneSim : BOOL := FALSE;
    xOutputDoneSim : BOOL := FALSE;
    uiStepTimeoutScansSim : UINT := 8;

    iObservedPhase : INT := 0;
    xObservedDone : BOOL := FALSE;
    xObservedError : BOOL := FALSE;
    xObservedTimeoutFault : BOOL := FALSE;

    iLastObservedPhase : INT := -1;
    iPhaseDwell : INT := 0;
    iCycleCountInternal : INT := 0;
    iResetCountInternal : INT := 0;
    iScanCountInternal : INT := 0;
    iScenarioCaseInternal : INT := 0;
    iNextScenarioAfterReset : INT := -1;
    iErrorPhaseLatched : INT := 0;

    xDoneLast : BOOL := FALSE;
    xResetPending : BOOL := FALSE;
    xStartPulsePending : BOOL := FALSE;
    xFaultScenarioStarted : BOOL := FALSE;
    xFaultPulseIssued : BOOL := FALSE;
    xRepeatScenarioStarted : BOOL := FALSE;
    iRepeatPulseCount : INT := 0;
    iRepeatBaselineCycle : INT := -1;
    xTimeoutScenarioStarted : BOOL := FALSE;
    xDisablePending : BOOL := FALSE;
END_VAR

VAR
    iPhaseMon AT %MW0 : INT;
    iCycleCountMon AT %MW1 : INT;
    iResetCountMon AT %MW2 : INT;
    iScanCountMon AT %MW3 : INT;
    iScenarioCaseMon AT %MW4 : INT;
    iErrorPhaseMon AT %MW5 : INT;

    xSawPhase0Mon AT %QX0.0 : BOOL;
    xSawPhase1Mon AT %QX0.1 : BOOL;
    xSawPhase2Mon AT %QX0.2 : BOOL;
    xSawPhase3Mon AT %QX0.3 : BOOL;
    xSawDoneMon AT %QX0.4 : BOOL;
    xSawResetReturnMon AT %QX0.5 : BOOL;
    xBehaviorPassMon AT %QX0.6 : BOOL;
    xBehaviorFailMon AT %QX0.7 : BOOL;

    xFaultInterruptPassMon AT %QX1.0 : BOOL;
    xRepeatStartBlockedPassMon AT %QX1.1 : BOOL;
    xTimeoutFailPassMon AT %QX1.2 : BOOL;
    xStartEventRequiredPassMon AT %QX1.3 : BOOL;
    xTimeoutErrorPassMon AT %QX1.4 : BOOL;
END_VAR

iScanCountInternal := iScanCountInternal + 1;
xEvtStartSim := FALSE;
xEStopSim := FALSE;
xResetSim := FALSE;
xTransportDoneSim := FALSE;
xFlipDoneSim := FALSE;
xOutputDoneSim := FALSE;
xEnableSim := TRUE;
xInitDoneSim := TRUE;

IF xDisablePending THEN
    xEnableSim := FALSE;
    xDisablePending := FALSE;
END_IF;

IF xResetPending THEN
    xResetSim := TRUE;
    xResetPending := FALSE;
    iResetCountInternal := iResetCountInternal + 1;
END_IF;

IF xStartPulsePending THEN
    xEvtStartSim := TRUE;
    xStartPulsePending := FALSE;
END_IF;

IF iScenarioCaseInternal = 99 THEN
    xEnableSim := FALSE;
    xInitDoneSim := FALSE;
END_IF;

CASE iScenarioCaseInternal OF
    0:
        IF (iObservedPhase <> 0) AND (NOT xStartEventRequiredPassMon) AND (iCycleCountInternal = 0) THEN
            xBehaviorFailMon := TRUE;
        END_IF;
        IF (iObservedPhase = 0) AND (iPhaseDwell >= 2) AND (NOT xStartEventRequiredPassMon) THEN
            xStartEventRequiredPassMon := TRUE;
            xStartPulsePending := TRUE;
            iScenarioCaseInternal := 1;
        END_IF;

    1:
        CASE iLastObservedPhase OF
            1:
                IF iPhaseDwell >= 2 THEN
                    xTransportDoneSim := TRUE;
                END_IF;
            2:
                IF iPhaseDwell >= 2 THEN
                    xFlipDoneSim := TRUE;
                END_IF;
            3:
                IF iPhaseDwell >= 2 THEN
                    xOutputDoneSim := TRUE;
                END_IF;
        END_CASE;

    2:
        IF (NOT xFaultScenarioStarted) AND (iObservedPhase = 0) AND (iPhaseDwell >= 1) THEN
            xStartPulsePending := TRUE;
            xFaultScenarioStarted := TRUE;
        END_IF;
        IF xFaultScenarioStarted AND (iObservedPhase = 1) AND (iPhaseDwell >= 2) AND (NOT xFaultPulseIssued) THEN
            xEStopSim := TRUE;
            xFaultPulseIssued := TRUE;
        END_IF;

    3:
        IF (NOT xRepeatScenarioStarted) AND (iObservedPhase = 0) AND (iPhaseDwell >= 1) THEN
            xStartPulsePending := TRUE;
            xRepeatScenarioStarted := TRUE;
        END_IF;

        CASE iLastObservedPhase OF
            1:
                IF iPhaseDwell >= 2 THEN
                    xTransportDoneSim := TRUE;
                END_IF;
            2:
                IF iRepeatBaselineCycle < 0 THEN
                    iRepeatBaselineCycle := iCycleCountInternal;
                END_IF;
                IF (iRepeatPulseCount < 3) AND (iPhaseDwell >= (iRepeatPulseCount + 1)) THEN
                    xEvtStartSim := TRUE;
                    iRepeatPulseCount := iRepeatPulseCount + 1;
                END_IF;
                IF (iRepeatPulseCount >= 3) AND (iCycleCountInternal = iRepeatBaselineCycle) THEN
                    xRepeatStartBlockedPassMon := TRUE;
                END_IF;
                IF (iRepeatPulseCount >= 3) AND (iPhaseDwell >= 6) THEN
                    xFlipDoneSim := TRUE;
                END_IF;
            3:
                IF iPhaseDwell >= 2 THEN
                    xOutputDoneSim := TRUE;
                END_IF;
        END_CASE;

    4:
        IF (NOT xTimeoutScenarioStarted) AND (iObservedPhase = 0) AND (iPhaseDwell >= 1) THEN
            xStartPulsePending := TRUE;
            xTimeoutScenarioStarted := TRUE;
        END_IF;
END_CASE;

fbMain(
    xEnable := xEnableSim,
    xEvtStart := xEvtStartSim,
    xEStop := xEStopSim,
    xStop := FALSE,
    xReset := xResetSim,
    xInitDone := xInitDoneSim,
    xTransportDone := xTransportDoneSim,
    xFlipDone := xFlipDoneSim,
    xOutputDone := xOutputDoneSim,
    uiStepTimeoutScans := uiStepTimeoutScansSim
);

iObservedPhase := fbMain.iPhase;
xObservedDone := fbMain.xDone;
xObservedError := fbMain.xError;
xObservedTimeoutFault := fbMain.xTimeoutFault;

IF iObservedPhase = iLastObservedPhase THEN
    iPhaseDwell := iPhaseDwell + 1;
ELSE
    iPhaseDwell := 0;
    iLastObservedPhase := iObservedPhase;
END_IF;

CASE iObservedPhase OF
    0:
        xSawPhase0Mon := TRUE;
    1:
        xSawPhase1Mon := TRUE;
    2:
        xSawPhase2Mon := TRUE;
    3:
        xSawPhase3Mon := TRUE;
END_CASE;

IF (iScenarioCaseInternal = 2) AND xFaultPulseIssued AND (iObservedPhase = 0) AND
   (NOT fbMain.xBeltForward) AND (NOT fbMain.xStartLamp) AND
   (NOT fbMain.xQ1) AND (NOT fbMain.xQ2) THEN
    xFaultInterruptPassMon := TRUE;
    iScenarioCaseInternal := 3;
    xFaultScenarioStarted := FALSE;
    xFaultPulseIssued := FALSE;
END_IF;

IF (iScenarioCaseInternal = 3) AND (iRepeatPulseCount > 0) AND (iRepeatPulseCount < 3) AND
   (iObservedPhase <> 2) THEN
    xBehaviorFailMon := TRUE;
END_IF;

IF xObservedDone AND (NOT xDoneLast) THEN
    xSawDoneMon := TRUE;
    iCycleCountInternal := iCycleCountInternal + 1;
    CASE iScenarioCaseInternal OF
        1:
            iNextScenarioAfterReset := 2;
            xResetPending := TRUE;
        3:
            iNextScenarioAfterReset := 4;
            xResetPending := TRUE;
    END_CASE;
END_IF;
xDoneLast := xObservedDone;

IF (iScenarioCaseInternal = 4) AND (iObservedPhase = 900) AND xObservedError AND xObservedTimeoutFault THEN
    xTimeoutErrorPassMon := TRUE;
    xTimeoutFailPassMon := TRUE;
    iErrorPhaseLatched := 900;
    iNextScenarioAfterReset := 99;
    xDisablePending := TRUE;
END_IF;

IF (iNextScenarioAfterReset >= 0) AND (iObservedPhase = 0) THEN
    xSawResetReturnMon := TRUE;
    iScenarioCaseInternal := iNextScenarioAfterReset;
    iNextScenarioAfterReset := -1;
    iRepeatPulseCount := 0;
    iRepeatBaselineCycle := -1;
END_IF;

IF xObservedError AND NOT ((iObservedPhase = 900) AND xObservedTimeoutFault) THEN
    xBehaviorFailMon := TRUE;
END_IF;

IF (NOT xBehaviorPassMon) AND
   xSawPhase0Mon AND xSawPhase1Mon AND xSawPhase2Mon AND xSawPhase3Mon AND
   xSawDoneMon AND xSawResetReturnMon AND
   xFaultInterruptPassMon AND xRepeatStartBlockedPassMon AND xTimeoutFailPassMon AND
   xStartEventRequiredPassMon AND xTimeoutErrorPassMon AND
   (iObservedPhase = 0) AND (iScenarioCaseInternal = 99) THEN
    xBehaviorPassMon := TRUE;
    xBehaviorFailMon := FALSE;
END_IF;

IF (NOT xBehaviorPassMon) AND (iScanCountInternal > 800) THEN
    xBehaviorFailMon := TRUE;
END_IF;

iPhaseMon := iObservedPhase;
iCycleCountMon := iCycleCountInternal;
iResetCountMon := iResetCountInternal;
iScanCountMon := iScanCountInternal;
iScenarioCaseMon := iScenarioCaseInternal;
iErrorPhaseMon := iErrorPhaseLatched;

END_PROGRAM


CONFIGURATION Config0

  RESOURCE Res0 ON PLC
    TASK Main(INTERVAL := T#50ms, PRIORITY := 0);
    PROGRAM Inst0 WITH Main : PLC_PRG;
  END_RESOURCE
END_CONFIGURATION
