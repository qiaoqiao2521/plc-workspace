# Progress — 2026-10-06

Current: verified native conveyor simulation. Owner: root Codex.

Done:
- Fixed historical agy SCL compiled with existing matiec/GCC, per-session native instance, immutable captured-source compilation and HTTP asset snapshot; no product ST changes.
- Interactive Three.js 3D equipment view, step/play/pause, Stop/Reset/Enable, jam/sensor failure, one-scan Done and bounded trace; responsive 390px layout.
- 13 JS and 26 Python checks pass, including 9 real-native/API simulation tests; none skipped with compiler environment set. Projection drift check passes. Static build emits 20 assets; Python syntax and diff checks pass.
- Real isolated Playwright interaction: scan 6 reaches 100% with Motor=0/Done=1; next scan clears Done. Jam timeout on scan 9 (startup + eight waits), Stop+Reset retains fault, released/new Reset clears fault. Continuous playback reaches a single Done row with no fault; pause stops scan advancement; 390x844 has no horizontal viewport overflow. Runtime screenshots outside Git under the task shell's work directory.
- Lifecycle fix: whole immutable asset snapshot and single-read captured SCL passed directly to compilation. Regression verifies post-start edits/deleted build directory, existing/new sessions, and changed source before compilation.
- Actual main-entry isolated acceptance also passes after changing the canonical sample and deleting rebuilt assets: existing/new sessions Motor=1 and download/page match frozen bytes. Restarted live service; browser startup and downloaded-source hash match pass.
- Independent startup negative test: isolated script/source fixture with stale download content rejected before serving, actual exit 1.
- Initial browser automation attempts used the wrong run-code callback signature; no successful checks were attributed to those calls. Correct `(page)` callback used for accepted interactions.
- Reviewed actual upstream test code and docs; did not execute upstream OpenPLC/Docker or Open Industry Project locally. No vendor compilation, hardware or safety claim.

Remaining: no implementation work for this bounded local demo; vendor/hardware acceptance and arbitrary-candidate execution remain outside the delivered scope. Publication identity is tracked by Git rather than duplicated here.

Issues / retained work: existing untracked material, harness, Windows mapping, vectors and imported validation config remain under [legacy handoff](../plc-frontend/legacy-handoff.md), root Codex owner. They lack provenance, semantic or target-environment evidence; preserved rather than silently published or discarded. Runtime lock remains local.

Next: reviewed generated candidates can receive explicitly supported execution adapters later; arbitrary SCL uploads and automatic acceptance are not implemented.

3D acceptance: WebGL scene renders; orbit/zoom/top/default views do not advance scans. Native arrival scan 6 drives 3D position=1 and Done=1. Jam leaves 3D position=0 and trips Error on the eighth wait; Stop retains fault. All resources fetched from loopback (no CDN). Forced WebGL context loss retains native step/trace. Initial mobile screenshot exposed intrinsic canvas/grid clipping despite document overflow check; corrected grid min width and canvas resize style, then rechecked actual bounds. Console application errors absent; isolated QA browser emits GPU readback performance warnings during screenshots.
