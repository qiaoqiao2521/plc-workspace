# FB specifications — v0.3

`FB_MainSequence` owns continuous block enable and a repeating sequencing command. `scan-contract.md` defines behavior; `00_meta/interface-contract.yaml` lists all typed I/O (interface version 0.2.0).

Static state: phase, scan timer, current timeout reason, timeout diagnostic history, command-aborted memory and previous Enable/Start/Reset input levels. All snapshots/conditions/next values are TEMP and initialized before use. No output is used as internal memory.

Every call performs snapshot → derive → compute → commit → publish. Each public output is written once. The instance must be called even while disabled; conditional EN/IF call suppression is not the business enable mechanism.

xBusy/xValid describe the enabled healthy FB, including idle. xCommandBusy describes active sequencing. xDone remains the cycle marker, not terminal execute-Done. xTimeoutFault describes the current error reason; xTimeoutDiagnostic is history cleared on enable rising. Reset affects healthy commands only; error recovery uses disable/re-enable. xEStop is an external inhibit, not an F function.

Existing names/types remain, with five new outputs. Existing callers must maintain Enable and observe the new error recovery and edge rules. Instance DB layout, real sub-FB handshakes, physical mapping, retention and TIA final acceptance require integration verification.
