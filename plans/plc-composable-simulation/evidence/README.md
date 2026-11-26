# Browser verification evidence

`browser-smoke.mjs` is an optional end-to-end smoke test against the actual repository HTTP service. It creates its own loopback server and temporary engineering fixtures, uses the configured matiec/GCC toolchain, and checks the rendered UI through Chromium. It does not replace simulation responses, advance the device model in JavaScript, or grant Siemens acceptance.

## Reproduce

Build the repository first with `npm --prefix web run build`. Install Playwright separately in a test environment and provide a Chromium executable or the browser installed by Playwright. Neither is an application dependency.

Set these environment variables for the test process:

| Variable | Purpose |
| --- | --- |
| `SIM_IEC2C` | Absolute path to the actual matiec `iec2c` executable. Required. |
| `SIM_MATIEC_LIB` | Path to the matching matiec `lib` directory. Required. |
| `PLC_BROWSER_PLAYWRIGHT` | Optional module name or absolute package directory resolvable by Node `require`. Defaults to `playwright`. |
| `PLC_BROWSER_CHROMIUM` | Optional Chromium executable. Defaults to the browser installed by Playwright. |
| `PLC_BROWSER_PYTHON` | Optional Python executable. Defaults to `python3`. |
| `PLC_BROWSER_EVIDENCE_DIR` | Optional output directory. Defaults to a new OS temporary directory. |
| `PLC_BROWSER_PORT` | Optional loopback port. Defaults to an available port. |
| `PLC_BROWSER_OIP` | Set to `1` to require the real OIP test through the UI. Otherwise this check is explicitly `not_run`. |
| `PLC_OIP_CHECKOUT` | Clean installed OIP checkout at the pinned source-index commit, when the OIP check is enabled. |

Run from the repository root, or pass the script's absolute path from another directory:

```sh
node plans/plc-composable-simulation/evidence/browser-smoke.mjs
```

The script launches an isolated, credential-free test service and software-rendered Chromium; the source and program fingerprints remain bound to real compiler output. The normal verification command `npm --prefix web test` does not run this optional browser test.

## Recorded checks

The JSON result records the checks actually completed by the run. Coverage includes the seven atomic device types in the default ten-component scene, native single-step execution, injection and removal of a plant fault, independent pusher assertions, replay, the latch profile's reduced controls, typed addition of a lamp, scene export and reimport, a 390 px mobile layout, and the generation page's visible simulation entry.

The engineering flow checks exact source transfer without historical verification or workflow records, re-executes the source, and optionally sends that same source to OIP's physical scene. A deliberate 12-to-8 timeout mutation must fail the independent jam case at scan 9; the UI must locate that first counterexample. An invalid engineering fingerprint must show a visible import error and retain the last valid engineering object. Changing the requirements must disable the old candidate's simulation action and clear its handoff.

The final two checks run without native tools and from a static-only server. Both must leave execution disabled and scan count zero. These conditions are not turned into an animation or a verification pass.

## Files

- `browser-smoke-result.json`: executed checks, browser version, source fingerprint and any failure.
- `browser-pusher-case.json`: native pusher test returned by the HTTP API.
- `browser-counterexample.json`: actual failing trace and first mismatch for the intentionally changed program.
- `browser-oip-current-engineering.json`: OIP physical review of the same captured engineering source, when executed.
- `simulator-desktop.png`, `simulator-mobile.png`, `simulator-counterexample.png`: browser screenshots of the scene, mobile layout and first counterexample.
- `generation-import-error.png`: engineering page after rejecting a changed request fingerprint.

Local machine and temporary execution paths are redacted from saved JSON; source hashes, scene hashes, program identity, assertions and measured values are retained. The screenshots show the repository's Three.js rendering. The separate OIP report records headless physical execution and retains `visual_render: not_run` for the upstream OIP editor.
