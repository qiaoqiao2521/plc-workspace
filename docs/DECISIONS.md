# Decisions

## 2026-09-22 — Converge scan semantics before platform work

User direction: 收敛 PLC 语义. Preserve the existing industrial workflow and sequencing path; fix execution semantics before selecting OS/TIA/PLC version combinations.

## Canonical ST and generated projections

The abstract core lives in `02_src/st`, and checker dialects/export copies are derived. This replaces manually maintained behaviorally different checker code. Generation changes syntax/packaging only; real timeout inputs remain real inputs. Revisit if a future checker cannot support a required construct, with its abstraction relation explicitly reviewed.

## Compatibility choices during the scan-order repair

Keep continuous 0→1→2→3→1 sequencing, completion priority at the timeout boundary, zero disabling scan-count timeout, and per-call sampling of the timeout parameter. These preserve the behavior already expressed by the existing helper functions. They are specific to this abstract example, not universal PLC rules.

## Historical pending question: process stop/fault policy and Enable meaning

Two domain questions have been presented to the user. No answer is inferred from elapsed time or from delegation of implementation.

- Stop/EStop may preserve Error until explicit Reset, return Init with a retained fault, or keep legacy fault acknowledgement. Reset acceptance while stop is held must be consistent with that choice.
- Enable may remain a start permission or become a continuous permission with a defined loss response.

Until answered, preserve legacy implementation and label the process contract pending. Do not claim the contradictory old fault-latch and Stop-lamp requirements have both been satisfied.

## 2026-09-22 — Official-source baseline supersedes the questionnaire

User correction: search official SCL specifications rather than ask the user to invent standard behavior. The preceding wait-for-choice approach is superseded; the delegation reply is still not a selection of the old proposed policy.

Read `SCL_STANDARD_BASELINE.md` for verified links and exact rule scopes. Siemens DA011 specifies continuous enable behavior; DA012 describes edge-triggered execute behavior. The earlier recommendation to keep start-only Enable is withdrawn. Do not claim a universal SCL Stop/Reset/fault priority: ordinary application inputs, EN/ENO and ESTOP1 safety acknowledgment are distinct.

Next align the implementation with the appropriate documented interface, beginning with DA008 internal state/output separation. Existing cyclic proof remains valid only for the unchanged candidate, not as evidence of standards compliance. This research turn changed guidance and continuity documents only.

## 2026-09-22 — v0.3 implemented after “落代码”

The user authorized implementing the official-source findings. The abstract core now separates internal state from outputs and applies continuous enable, current-error clearing on disable and timeout-history clearing on enable rising. Healthy Reset is an explicit command extension: it aborts/reinitializes a healthy sequence, but does not acknowledge an enabled block error. This supersedes the earlier proposed Reset-clears-fault policy.

Start/Reset edges are consumed on every call, even when rejected. Stop/EStop inhibit and cancel healthy motion without clearing existing errors. Enable alone cannot restart. xBusy/xValid report the continuous FB; xCommandBusy/xCommandAborted report command state; legacy xDone remains a cycle pulse. The timeout diagnostic covers timeout history only. All of these project-specific mappings are explicit in scan-contract v0.3, not presented as universal SCL language rules.

Interface 0.2.0 preserves old names/types and appends five outputs, but is behaviorally breaking and changes instance layout. Caller error recovery must issue an observed disabled call. No new Main/F layer or TIA project is invented. Tests and formal evidence validate the abstract contract; full PLCopen conformance, F safety and Siemens final acceptance remain unclaimed.
