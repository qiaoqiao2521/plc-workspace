# PLC Workspace frontend

Static Chinese scan observatory. Six curated scenarios replay 42 invocations of the actual canonical ST compiled with matiec. The browser displays recorded inputs/outputs; it does not implement a second PLC state machine or connect to hardware.

## Run locally

From the repository root (Node 18+ and Python 3):

```sh
npm --prefix web test
npm --prefix web run build
python3 -m http.server 8766 --bind 127.0.0.1 --directory web/dist
```

Open http://127.0.0.1:8766. No npm dependencies or install step. The five-file static output contains no server functions, external fonts, analytics, account data or tool binaries.

## Refresh traces

Use the existing native toolchain; paths are explicit and machine-specific:

```sh
python3 web/scripts/export-traces.py --iec2c /path/to/iec2c --matiec-lib /path/to/matiec/lib
npm --prefix web test
npm --prefix web run build
```

The exporter compiles canonical ST in a temporary directory and checks published formal evidence hashes. `build` rejects stale canonical source or formal evidence. If ST changes, refresh its verification evidence and regenerate traces before building. Curated scenario text and independent behavior tests must be reviewed with contract changes. The checked-in JSON is a deliberate public demonstration artifact, not a live runtime log.

Playback, previous/next scan, range seeking, row seeking, scenario selection and JSON export work entirely in-browser. Playback speed changes only presentation timing, never scan results. Exports contain selected recorded data and source hashes, not simulator inputs.

## Cloudflare preparation (not deployed)

For Pages, repository root remains the root; build command: `npm --prefix web run build`; output directory: `web/dist`. No Functions directory. Workers Static Assets can serve the same directory without a Worker script. No account identifier or deployment credentials are stored here. Existing account use must be inspected before a later deployment.

Official limits checked 2026-09-30: Pages 100 projects/account, free 500 builds/month; Workers static requests free and unlimited, dynamic requests on Free share an account-level 100,000/day allowance. Hosting two websites alone does not require a new account.

- https://developers.cloudflare.com/pages/platform/limits/
- https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/
- https://developers.cloudflare.com/workers/platform/limits/

This UI exposes Linux/offline evidence only. It is not TIA, PLCSIM, real-machine or F-safety acceptance.
