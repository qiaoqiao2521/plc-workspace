# Frontend fixes and ZCode retest — 2026-10-01

## Scope and baseline

User requested the other code defects fixed before repeating the evaluation with ZCode. Canonical PLC source and the previous deliberately unaccepted candidates are unchanged. The frozen [expectation](user-eval/expectation.md) remains the oracle; no requirements were rewritten to match generated output.

## Code changes accepted

- Added **打开工程草稿**, independent of preparing a new task. Validate the exported request and result, recompute its fingerprint, then restore the original pair atomically. Existing **导入 Agent 结果** still requires exact current task binding.
- File-imported engineering remains unverified even if its file labels itself a repository example or reports passing checks. Requirement edits invalidate restored exports.
- Normalize redundant model LAD title prefixes for both rendering and Markdown export. Preserve original candidate contents.
- Added optional local ZCode adapter using an existing stable `resources/glm/zcode.cjs`, with explicit permission mode/tool denial, disposable cwd, bounded process control, strict JSON parsing and shared schema/request binding checks. Default agy invocation remains available.
- Provider labels reflect the chosen CLI. A present executable means CLI availability, not authenticated model-service or quality acceptance.

## Verification

13 JavaScript tests and 8 Python bridge tests passed. ZCode process tests are synthetic: valid JSON response accepted; prose, wrong shapes and explicit error rejected. Build and canonical projection check passed.

Actual browser operations:
1. Opened the old exported repository example from a blank page, refreshed, opened it again. Original requirements/source restored; checks panel explicitly says new engineering unverified.
2. Edited the restored requirement: previous engineering export disabled.
3. Opened the actual previous CM evaluation's exported conveyor engineering. LAD rendered one network prefix; Markdown preview also had one prefix.
4. At 390px viewport, document scroll width 375px; all three handoff buttons stayed within the page.

## Actual ZCode runs

Both runs used CLI 0.16.5 from an already installed stable runtime, selected through the loopback browser bridge. This is direct ZCode generation, not a CM TaskHub dispatch or a ZCode-driven browser evaluator. CM's installed TaskHub has no ZCode slot; no global CM provider/policy was changed.

|Run|Demand|Configured budget|Observed result|Semantic verdict|
|---|---|---|---|---|
|1|A: original conveyor requirement; S7-1200 / V18; cyclic flow draft|180s|Process timed out; no accepted engineering; editable form recovered|UNKNOWN, no candidate to check|
|2|B: original conflicting double-cylinder demand; no CPU/TIA/flow assumptions|180s|Process timed out; no accepted engineering; editable form recovered|UNKNOWN; B01–B04 not established|

The first two generation runs used plan mode with tool denial. These live runs used the inherited 10s transport overhead beyond the advertised model budget. Final code removes that extra process allowance for ZCode (agy retains its own internal timeout plus transport allowance); a delayed-process regression proves the ZCode limit is enforced. The A structured I/O field was empty in this retest; named input/output requirements remain in its unchanged natural-language text. Therefore these are the same acceptance scenarios, not an identical byte-for-byte request replay. No retries or semantic successes are hidden in these two rows.

Run 3: a separately counted 60s diagnostic used edit mode with the same tool denial and asked only for `{"ok":true}`. Actual CLI exit 0 and response `{"ok":true}`; model connectivity for this small task is established. This is not a PLC benchmark.

Following that diagnostic, the adapter switched to the previously proven edit mode while retaining tool denial; child Node thread-pool defaults were limited locally (existing environment overrides preserved). Both parameters changed, so the diagnostic does not isolate the timeout cause. Run 4 repeated B: timeout, no accepted candidate, form recovered. Run 5 repeated A with the complete previous structured brief (including I/O); its displayed fingerprint `18bf58ff6388` matched the original A engineering. This also timed out with no accepted candidate; the editable form recovered.

Total real CLI invocations: **5** (four engineering attempts at configured 180s, one diagnostic at 60s). The diagnostic succeeded; all four engineering attempts timed out. No new SCL/LAD candidate was available for semantic comparison. This does not establish either model superiority or correction of the previous Stop/Done counterexamples.

Evidence screenshots are owner-local under this chat's `work/plc-user-eval/`: `reopen-fixed.jpg`, `zcode-A-timeout.jpg`, `zcode-B-timeout.jpg`, `zcode-B-edit-timeout.jpg`, `zcode-A-edit-timeout.jpg`. Raw CLI session metadata/logs stay outside Git.

## Remaining boundary and handoff

The frontend defects above are fixed. Generated-engineering semantic acceptance with ZCode remains unresolved until it returns an actual candidate; the earlier Stop/Done counterexamples must not be declared fixed by changing provider. Site checks still display model reports and the separately bound repository example, with no automatic new-candidate compilation gate. Root Codex owns the next step: investigate the existing local ZCode service/runtime path, then repeat the same frozen scenarios and independently check any returned source. No Siemens or physical PLC acceptance, cloud deployment, or CM-native ZCode integration is claimed.
