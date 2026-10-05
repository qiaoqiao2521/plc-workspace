# Progress — 2026-10-06

Current: verified native conveyor simulation. Owner: root Codex.

Done:
- Fixed historical agy SCL compiled with existing matiec/GCC, per-session native instance, immutable captured-source compilation and HTTP asset snapshot; no product ST changes.
- Interactive plant, step/play/pause, Stop/Reset/Enable, jam/sensor failure, one-scan Done and bounded trace; responsive 390px layout.
- 13 JS and 26 Python checks pass, including 9 real-native/API simulation tests; none skipped with compiler environment set. Projection drift check passes. Static build emits 15 assets; Python syntax and diff checks pass.
- Real isolated Playwright interaction: scan 6 reaches 100% with Motor=0/Done=1; next scan clears Done. Jam timeout on scan 9 (startup + eight waits), Stop+Reset retains fault, released/new Reset clears fault. Continuous playback reaches a single Done row with no fault; pause stops scan advancement; 390x844 has no horizontal viewport overflow. Runtime screenshots outside Git under the task shell's work directory.
- Lifecycle fix: whole immutable asset snapshot and single-read captured SCL passed directly to compilation. Regression verifies post-start edits/deleted build directory, existing/new sessions, and changed source before compilation.
- Actual main-entry isolated acceptance also passes after changing the canonical sample and deleting rebuilt assets: existing/new sessions Motor=1 and download/page match frozen bytes. Restarted live service; browser startup and downloaded-source hash match pass.
- Independent startup negative test: isolated script/source fixture with stale download content rejected before serving, actual exit 1.
- Initial browser automation attempts used the wrong run-code callback signature; no successful checks were attributed to those calls. Correct `(page)` callback used for accepted interactions.
- Reviewed actual upstream test code and docs; did not execute upstream OpenPLC/Docker or Open Industry Project locally. No vendor compilation, hardware or safety claim.

Remaining: no implementation work for this bounded local demo; vendor/hardware acceptance and arbitrary-candidate execution remain outside the delivered scope. Publication identity is tracked by Git rather than duplicated here.

Issues / retained work: existing untracked material, harness, Windows mapping, vectors and imported validation config remain under [legacy handoff](../plc-frontend/legacy-handoff.md), root Codex owner. They lack provenance, semantic or target-environment evidence; preserved rather than silently published or discarded. Runtime lock remains local.

Next: reviewed generated candidates can receive explicitly supported execution adapters later; arbitrary SCL uploads and automatic acceptance are not implemented.
