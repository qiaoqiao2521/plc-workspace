# Local CLI delivery without a generation deadline

2026-10-01: user explicitly requested local mcode and ZCode with no time limit, judged by delivered artifacts.

- Keep the frozen [A/B expectations](user-eval/expectation.md) and previous complete exported requests. No automatic promotion to canonical PLC source.
- Add explicit `--timeout 0`; retain cancellation, schema checks and request/result binding. Default budget remains unchanged for ordinary use.
- Regression: 13 JS and 9 Python tests pass, including a late-result acceptance test with unlimited mode and an existing bounded-mode rejection test. Static build succeeds.
- ZCode: use the existing local CLI 0.16.5 from the installed stable CLI entry; run A then B through the same generation bridge API with timeout 0. This round is API/CLI delivery testing, not ZCode-controlled browser testing or CM scheduling.
- MiniMax Code found at the official installer path `~/.minimax-code/bin/mcode`; installed version 0.5.9. It was absent from this shell PATH. Use this existing launcher without installation/account/config changes. Headless uses `exec`, smart permission policy (not off/bypass), scratch cwd and no `--timeout` or externally imposed process deadline.
- Runtime requests, CLI sessions and raw logs remain owner-local under this chat's `work/plc-unlimited/`, outside Git.

## Real invocation ledger

|Run|CLI / case|Time|Delivery state|Acceptance|
|---|---|---|---|---|
|1|ZCode A|488.4s|Schema and binding accepted; SCL/LAD returned|FAIL: 3 of 16 observable scan checks mismatch|
|2|ZCode B|372.5s|Schema and binding accepted; SCL/LAD returned|FAIL B04: invented mechanical/Stop assumptions despite clarification request|
|3|MiniMax Code A, initial setup|178.9s|Exit 4 / STRUCTURED_OUTPUT_INVALID|Invalid comparison setup: schema was passed to validator but omitted from prompt|
|4|MiniMax Code B, initial setup|182.9s|Exit 4 / STRUCTURED_OUTPUT_INVALID|Same setup defect; do not label semantic model failure|
|5|MiniMax Code A, corrected setup|198.5s|Exit 0; schema and binding accepted|16/16 selected normalized-ST scan checks match; original SCL/TIA unverified|
|6|MiniMax Code B, corrected setup|183.4s|Exit 0; schema and binding accepted|FAIL B04: deterministic actuation and unresolved defaults|

No time-based termination was issued in any of these runs. The initial MiniMax setup error is retained rather than overwritten. Both valid adapters receive the complete frozen engineering request, the shared engineering prompt and explicit result schema. ZCode uses denied tools; MiniMax uses its smart permission policy and an instruction not to call tools. These are not equivalent security boundaries; no filesystem isolation or provider-neutral system prompt is claimed.

## ZCode independent review

A actual persistent FB calls: Start accepts state (Busy=1) but Motor=0 on the acceptance scan. AtEnd on the eighth waiting call produces Done=0, then Done=1 on the following call. The other 13 selected observable checks match; this is not full acceptance. Source SHA-256: `f64f6b68080509deb31c054fed6fdeb04aea369005da5e5519d9c5d209508d5a`.

B detects the contradictory Stop requirements, then nevertheless selects double-solenoid valves, four sensor inputs, a 5-second TIME setting, retained actuation on Stop and a Reset destination. This violates B04, even though it labels these assumptions provisional. Its own selected definition says xEnable=FALSE freezes steps; native calls show state 1→2 and advance output energized with xEnable=FALSE and clamp feedback true. This probe tests the candidate's own stated choice, not a newly imposed Stop policy on the unresolved user demand. Positive control: both Home inputs false in return state does not produce Done. TON runs under constant native time here; timer correctness is not established. Source SHA-256: `492339ee29094ccd439e14e8da94eb774d431516109d6ab780d085cfec25dce7`.

Recorded unaccepted assets/results: [ZCode fixtures](user-eval/unlimited/zcode/). Replay:

```sh
python3 plans/plc-generation-ui/user-eval/reproduce-unlimited-zcode.py \
  --work-dir /absolute/output/outside/repository \
  --iec2c /path/to/iec2c --matiec-lib /path/to/matiec/lib
```

Replay exit 0 means the named known failures were reproduced, not that either PLC candidate passed. Normalization removes quoted FB declarations, Siemens attributes/title/version/BEGIN and local # prefixes; literal constants may be folded for matiec CASE support. It does not repair Boolean logic/control flow. This is Linux compiled-ST evidence, not TIA/PLCSIM/physical-machine acceptance.

## MiniMax independent review

Corrected runs use installed MiniMax Code 0.5.9; execution metadata identifies MiniMax-M3.1-Flash-Preview, thinking variant. This evaluates that actual local configuration, not every MiniMax model. All six model invocations, including the two invalid initial setups, are accounted for above.

A matches all 16 selected observable scan checks using the same expectations as ZCode: startup output, eight-call timeout, Enable withdrawal, completion at the deadline, Done pulse, Stop/fault retention and consumed Reset/Start edges. This is bounded sampling, not full semantic proof. The first native compiler attempt failed at the brace-wrapped source header. The successful probe removes the entire preamble before FUNCTION_BLOCK, then applies Siemens-to-ST syntax normalization; the original delivered file is preserved unchanged. No Boolean/control-flow repair occurred. Neither original SCL compilation in TIA nor LAD import was tested. LAD includes two empty call placeholders, so it remains a review draft. A source SHA-256: `aa7865b0f8382d0cb64565caac203b214f74825b0ae85c81effecb3eb93044ee`.

B raises clarification questions but defaults Stop fault clearing to FALSE, selects 5/10/10-second timeouts and a 300ms hold, and emits four mechanical command outputs with deterministic transitions. This fails the frozen B04 requirement to avoid assumptions before clarification. B is rejected by static requirement review; no B native compilation or scan claim is made.

Preserved unaccepted [MiniMax fixtures and scoped findings](user-eval/unlimited/mcode/). Replay the A checks with `reproduce-unlimited-mcode.py` using the same `--work-dir`, `--iec2c`, `--matiec-lib` arguments as above. Exit 0 means only those 16 normalized-ST observations match.

All four corrected deliveries are complete; root Codex owns subsequent clarification enforcement and Siemens acceptance. No generated candidate is promoted into canonical PLC source. The original oracle and earlier fixtures remain unchanged.
