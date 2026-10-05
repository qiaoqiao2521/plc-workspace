# PLC Workspace frontend

Requirements → state/I/O review → local AI generation → SCL/LAD draft export. Existing compiled-ST replay is in `validation.html`, supporting the generator’s quality.

## Run

Node 18+ and Python 3.10+; no npm dependencies. The selected local CLI must already be configured.

```sh
npm --prefix web run build
npm --prefix web run dev -- --mcode /absolute/path/to/mcode \
  --cm-company EXISTING_COMPANY_ID --workflow-root /outside/repo/runtime
```

Open http://127.0.0.1:8766. The Python bridge listens only on 127.0.0.1 and starts the strict mcode/CM workflow only after clicking **AI 生成工程**. `npm run dev` selects that workflow without a generation deadline; specify the existing local Paperclip company and a runtime directory outside Git. One engineering workflow is active at a time; its two review roles may run concurrently. Explicit `--provider agy` or `--provider zcode` retains the earlier diagnostic adapters, with the standalone CLI's 180-second default budget. Local CLI execution does not imply local/offline inference.

For a static preview without generation:

```sh
python3 -m http.server 8768 --bind 127.0.0.1 --directory web/dist
```

The UI detects missing `/api/capabilities`, explains how to start the local bridge and keeps Agent task/result handoff available. A static public website cannot execute agy on the server or visitor computer. No model credentials or local server code are included in the static asset output.

## Generation protocol

- `POST /api/generate`: `{request, prompt}`; returns a job identifier. Requires JSON content type, same origin and `X-PLC-Workspace: 1`.
- `GET /api/jobs/<id>`: running/complete/failed/cancelled; complete includes structured result.
- `POST /api/jobs/<id>/cancel`: cancel the current model process.
- `request` freezes brief and state draft, with a SHA-256 content fingerprint and request ID.
- [generation-result.schema.json](data/generation-result.schema.json) defines SCL files, states, I/O, LAD networks, questions and Agent-reported checks.
- Edited requirements invalidate the prepared request and disable old-result exports. Imported results must echo the current request ID/fingerprint. No model report becomes verification evidence.
- The default agy adapter uses plan + sandbox and a temporary working directory, receiving no checkout path. Do not add `--disable-slash-commands`: the installed agy warns that it disables plan mode. This is a bounded engineering adapter, not a security boundary for running untrusted programs.

Drafts are saved in browser storage only when the user clicks save. Jobs/results are in local process memory (last eight jobs) and lost on server restart. Task/model content, CLI conversation IDs and runtime logs are not committed or automatically stored by this bridge; agy itself may retain its normal local session history.

## Engineering output

SCL can be downloaded per file. LAD shows simple series contacts/coils or periodic FB call bindings; unsupported logic stays in notes/questions. LAD Markdown and structured engineering JSON are review artifacts, not TIA project files. Exported/imported candidates still need independent compilation, scan checks and Siemens acceptance. Changing a process never inherits the example’s proof.

## Checks and example data

```sh
npm --prefix web test
```

Thirteen JavaScript checks include compiled-ST trace assertions and stale/malformed-result cases; Python bridge tests exercise synthetic process failures, cancellation and HTTP origin checks. Live agy/browser acceptance is recorded in [the plan](../plans/plc-generation-ui/progress.md).

The build verifies canonical source/formal evidence hashes and generates the repository example payload directly from ST. Existing traces contain six scenarios / 42 actual FB calls. To regenerate them after core changes:

```sh
python3 web/scripts/export-traces.py --iec2c /path/to/iec2c --matiec-lib /path/to/matiec/lib
npm --prefix web run build
```

## Hosting later

Pages build: `npm --prefix web run build`; output: `web/dist`. Pure static hosting includes generation UI, schema, sample and replay but no Python bridge. Online generation requires a separately authorized cloud service. Account/domain/deployment remain unverified.

Official limits checked 2026-09-30 remain in the [earlier hosting findings](../plans/plc-frontend/findings.md). No account change or Cloudflare deployment was performed.

## ZCode and engineering recovery

To select an existing ZCode CLI (the desktop `zcode` launcher is not the CLI):

```sh
python3 web/scripts/local-server.py --provider zcode --zcode-cli /stable/path/resources/glm/zcode.cjs
```

`--node /path/to/node` can select the runtime. ZCode uses explicit edit mode, denied engineering/file/command tools, a disposable directory, and the same result schema/binding checks and time budget. Its text response must be a single JSON object; prose or malformed results are rejected. This adapter is not filesystem isolation. Selecting ZCode does not change CM's global provider or establish a native TaskHub slot.

**打开工程草稿** restores the request and result from an exported engineering JSON, including the original request identity. It recalculates the fingerprint and validates both assets before changing the displayed engineering. **导入 Agent 结果** remains restricted to the currently prepared request. Neither import path inherits verification from a file. Editing a restored requirement still invalidates its exports. Save-draft continues to preserve requirements only; export the engineering before reload to preserve generated results.

LAD numbering is supplied once by the viewer/exporter; redundant model title prefixes are stripped for presentation only, without rewriting original candidates.

### Explicit unlimited generation

Use `--timeout 0` when choosing to wait for delivery without a generation deadline. This passes no timeout to the child-process wait (and omits agy's own print-timeout argument). The default remains 180 seconds. Cancellation, single-active-job exclusion, result schema and request binding still apply. The CLI/provider may independently fail; no deadline does not guarantee a result. Polling HTTP requests are separate from the model process lifetime.

### Strict mcode workflow

For the selected industrial draft workflow, use `--provider mcode-cm --timeout 0 --mcode /path/to/mcode --cm-company EXISTING_COMPANY_ID --workflow-root /outside/repo/runtime`. The existing local Paperclip runtime must be available. Specification approval precedes generation, two text reviews run concurrently, and one supervisor role reviews the outcome. Unresolved/rejected/unknown outputs are not imported as engineering. See [execution protocol](../docs/PLC_AGENT_WORKFLOW.md) for commands, responsibilities and current verification limits. An approved text review remains an unverified engineering draft.

## Visible conveyor simulation

Build the site, then run the fixed recorded conveyor FB through the existing native compiler:

```sh
npm --prefix web run build
python3 web/scripts/simulation-server.py \
  --iec2c /absolute/path/to/iec2c --matiec-lib /absolute/path/to/matiec/lib
```

Open **http://127.0.0.1:8767/simulation.html**. Requires GCC and the existing matiec library/compiler. This service is separate from the 8766 AI generation bridge; no model calls are made. Use a different port for the earlier static-only preview. Static hosting cannot run the simulation API; it shows an unavailable-service message.

Start performs one FB call with Start true; subsequent step/play calls release it. Enable withdrawal does not cancel this sample's accepted command. Stop applies on the next requested scan. Reset is one input pulse; two pulses without an intervening release scan remain a held signal. “重建 PLC 与工件” initializes a new native instance and plant, not a Reset input.

The view executes the **recorded agy conveyor candidate**, not arbitrary output from the current generation job. The original SCL download must hash-match the execution source at server startup. Siemens syntax is adapted for matiec without changing transitions. Position/speed are synthetic: one energized call advances 20%; continuous playback waits 500ms between requests. The eight-call timeout does not mean eight seconds. Done is a single scan pulse preserved in the trace. This does not establish LAD execution, TIA/PLCSIM, mechanics or industrial acceptance.

Run the seven native simulation tests as part of the existing frontend suite:

```sh
SIM_IEC2C=/absolute/path/to/iec2c SIM_MATIEC_LIB=/absolute/path/to/matiec/lib npm --prefix web test
```

Without these variables native simulation tests are explicitly skipped, not passed. Build products and compiler logs/libraries remain outside tracked source. Research and acceptance details: [simulation plan](../plans/plc-simulation/task_plan.md).
