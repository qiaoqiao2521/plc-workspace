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

## 2026-09-22 — Verification scope completed after adversarial variant pass

An adversarial pass (isolated copies beside the checkout; no product behavior changed) built seven wrong-implementation variants of the canonical FB — timing boundary offset, abort-over-fault priority, unconsumed Start edge, early state commit, diagnostic-history erasure, false timeout reason on invalid phase, doubled timer increment — plus one branch-order variant that proved equivalent, and ran the shipped scan suite, native driver, projection-drift gate and formal case against each.

Confirmed gaps and the minimal fixes, all contract-derived, none weakening an existing check:

- Invalid phase reporting a false timeout reason passed every shipped layer. New native test `test_illegal_phase_reports_no_timeout` (the formal layer cannot see it: corrupt phases are unreachable from an initialized instance, so a related assertion would be vacuous).
- Edge-memory updates (P27), CommandAborted clearing on an accepted Start (P28), and the absolute scan-count boundary — no early expiration, N=1 on the first waiting call, +1 per waiting call (P29–P31) — were pinned only by native tests, so formal "pass" did not cover them. The added assertions now catch those variant classes formally (counterexample indices confirm P30, P27, P31, P28 hit their intended classes).
- The branch-order "completion loses to timeout" variant proved behaviorally equivalent (0 divergences in 20,000 cross-implementation scans): `FC_MainSequence_TimeoutReached` already excludes `xStepDone`, so completion priority is structural, and P9–P11 plus the native deadline test cover the real bug class.
- Tool budget: the strengthened conjunction needs about 47 s on the reference machine, so the gate's default backend timeout moved from 30 s to 60 s. Verdict semantics are unchanged; unknown (including timeout) still returns 2 and never passes. At the shipped 60 s budget three wrong variants time out instead of reporting a violation (at an extended 300 s budget all three are reported as violated, including one that also timed out under the old 26-assertion model). The native suite is decisive there regardless.

Counts updated accordingly (25 scan tests, 31 assertions). Evidence directories were re-bound to the regenerated projections; older v0.3 runs are superseded in place, v0.2 remains historical.

## 2026-09-23 — Independent review found two gaps; timing assertions rewritten contract-derived

An independent review of the uncommitted fixes accepted the caught cases and found two defects in the new verification itself.

- [P1] The rewritten P29–P31 still left the general deadline unpinned: P30 only forced the N=1 boundary while P29/P31 referenced the implementation's own `xTimeoutReached`. A variant that delays expiry only at threshold 31 passed every shipped layer. P29–P31 are now contract-derived obligations: the deadline is computed from the threshold input, the prior timer and the completion levels, `xTimeoutReached` never gates a check, and the `prevTimer+1 >= N` deadline is written overflow-free (`prev < 65535 AND prev >= N-1`, with the prev = 65535 wrap state matching the typed addition on both sides). The late31 variant is regression V8 in the lab; it is caught by P30 and by the native boundary sample at N=31. Sampling breadth in native tests is defense in depth only — the general rule is carried by the formal quantifier, not by an extra special case.
- [P2] `refresh_evidence.sh` recorded the negative-control outcome without enforcing it. The script now hard-fails before publishing unless every positive layer reports an explicit pass and the negative control is rejected in the same run (gate exit 1 and verdict "fail"); stubbed-gate control-flow tests for exit 0, exit 2 and verdict-pass outcomes confirm non-publication.

Re-review the same day confirmed both fixes and corrected the overflow rationale: a busy step can never enter a scan with prior timer 65535 (with N = 0 the timer is held at zero; with N > 0 the deadline expires at prior timer N-1 <= 65534 at the latest), so the P29-P31 exclusion at prev = 65535 is vacuous on contract-obeying execution and only keeps the assertions exact for test-only injected timer values.

No product behavior changed. The "coverage completed" claim is scoped to what the variant regression actually demonstrates: each known wrong-implementation class is caught by a named check, not that the verification is exhaustive.
