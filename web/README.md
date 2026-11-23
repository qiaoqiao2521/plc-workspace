# PLC Workspace frontend

Requirements → state/I/O review → local AI generation → current SCL checks/repair → draft export. Existing compiled-ST replay is in `validation.html`, supporting the generator’s quality. See [current SCL loop](../docs/SCL_CLOSED_LOOP.md) for compiler setup, the 12-call conveyor acceptance and evidence boundaries.

## Run

Node 24 and Python 3.10+; install the pinned Three.js dependency with `npm --prefix web ci`. Configure a model API in the page or give the task to an external Agent.

```sh
npm --prefix web run build
npm --prefix web run dev
```

Open http://127.0.0.1:8766. The Python bridge listens only on loopback. **API 生成** calls the configured OpenAI-compatible Chat Completions service; **Agent 接管** exposes constrained stage packets to a local external Agent. Neither needs CM/Paperclip or a model CLI. Both use the same PLC controller, tools, repair limits and evidence gate. One workflow runs at a time, with two reviewer calls allowed concurrently. Configuration readiness is not a live provider test.

For a static preview without generation:

```sh
python3 -m http.server 8768 --bind 127.0.0.1 --directory web/dist
```

The UI detects missing `/api/capabilities`, explains how to start the local bridge and keeps Agent task/result handoff available. A static public website cannot run the controller or contact the visitor’s local service. No model credentials or local server code are included in the static asset output.

## Generation protocol

- `GET /api/config`: redacted API config; `POST /api/config`: update Base URL, model, optional key, request timeout and JSON mode. Omitted key is retained only for the same endpoint; `clear_key: true` clears it. A failed save preserves the previous valid config.
- `POST /api/generate`: `{request}`; returns a job identifier. The controller builds prompts from the request; a legacy `prompt` field cannot change its instructions.
- `POST /api/agent/jobs`: `{request}`; returns a task ID and task token. With the Bearer token, read `/api/agent/jobs/<id>/packets` and post `{packet_id,input_sha256,answer}` to `/answers`. The controller validates and consumes each packet once.
- `GET /api/jobs/<id>`: running/complete/failed/cancelled, with `finished` after cleanup. Completed jobs include a result and scoped evidence; failed jobs may retain `candidate_result` without acceptance.
- `POST /api/jobs/<id>/cancel`: cancel the current task and poll until `finished`.
- All POSTs require JSON, same-origin browser requests and `X-PLC-Workspace: 1`. No secrets are placed in URLs, exported engineering or browser draft storage.
- `request` binds brief and state draft with a SHA-256 fingerprint and request ID. Edited requirements invalidate old results. Imported records never confer current acceptance.

For Agent control, load [plc-workspace-control](../.agents/skills/plc-workspace-control/SKILL.md) and use `python3 web/scripts/plc-agent.py workflow --request task.json`, or `workflow --attach` for an existing page task. Keep its stdin session open; it emits current packets and consumes structured answer lines. `doctor`, `prepare --brief`, `status` and `cancel` cover setup and recovery without a token file or another scheduler.

Full API/Agent setup, answer format, provider limits and cancellation semantics: [execution protocol](../docs/PLC_AGENT_WORKFLOW.md).

Requirements are saved in browser storage only on explicit save. API settings and Agent tokens are separate in-memory configuration. The bridge retains the last eight jobs in memory; `--runtime-root /outside/repo/runtime` keeps request, knowledge, stage answers, candidate revisions and tool evidence outside Git. Its default is the system temporary directory, which is subject to cleanup. API credentials travel only through the controller's stdin and the provider authorization header. Server restart requires configuration again unless supplied through `PLC_API_*` environment variables.

## Engineering output

SCL can be downloaded per file. LAD shows simple series contacts/coils or periodic FB call bindings; unsupported logic stays in notes/questions. LAD Markdown and structured engineering JSON are review artifacts, not TIA project files. Exported/imported candidates still need independent compilation, scan checks and Siemens acceptance. Changing a process never inherits the example’s proof.

## Checks and example data

```sh
npm --prefix web test
```

JavaScript checks cover trace assertions, request/source binding and engineering recovery; Python tests cover process failures, cancellation, HTTP origin checks and workflow repair gates. Set `SIM_IEC2C` and `SIM_MATIEC_LIB` to run the real compiler/scan regressions as well. Model responses in automated workflow tests are fixtures; live model acceptance is separate. Earlier agy/browser acceptance is recorded in [the plan](../plans/plc-generation-ui/progress.md).

The build verifies canonical source/formal evidence hashes and generates the repository example payload directly from ST. Existing traces contain six scenarios / 42 actual FB calls. To regenerate them after core changes:

```sh
python3 web/scripts/export-traces.py --iec2c /path/to/iec2c --matiec-lib /path/to/matiec/lib
npm --prefix web run build
```

## Hosting later

Pages build: `npm --prefix web run build`; output: `web/dist`. Pure static hosting includes generation UI, schema, sample and replay but no Python bridge. Online generation requires a separately authorized cloud service. Account/domain/deployment remain unverified.

Official limits checked 2026-09-30 remain in the [earlier hosting findings](../plans/plc-frontend/findings.md). No account change or Cloudflare deployment was performed.

## Engineering recovery

**打开工程草稿** restores the request and result from an exported engineering JSON, including the original request identity. It recalculates the fingerprint and validates both assets before changing the displayed engineering. **导入 Agent 结果** remains restricted to the currently prepared request. Neither import path inherits verification from a file. Editing a restored requirement still invalidates its exports. Save-draft continues to preserve requirements only; export the engineering before reload to preserve generated results.

LAD numbering is supplied once by the viewer/exporter; redundant model title prefixes are stripped for presentation only, without rewriting original candidates.

### Task timeout and cancellation

The default `--timeout 0` imposes no whole-task deadline. Set a positive number of seconds to bound the task. The API request I/O timeout is separately configurable (default 120, range 1–600). Cancellation revokes acceptance, unwinds native checks and wakes all waiting Agent stages; an API wait that cannot exit receives a local process-group kill after five seconds. This does not cancel remote provider billing or stop an independently owned Agent process. A disconnected page keeps its task/cancel controls and can retry polling without starting a second job.

## Visible conveyor simulation

Build the site, then run the fixed recorded conveyor FB through the existing native compiler:

```sh
npm --prefix web run build
python3 web/scripts/simulation-server.py \
  --iec2c /absolute/path/to/iec2c --matiec-lib /absolute/path/to/matiec/lib
```

Open **http://127.0.0.1:8767/simulation.html**. Requires GCC and the existing matiec library/compiler. This service is separate from the 8766 AI generation bridge; no model calls are made. Use a different port for the earlier static-only preview. Static hosting cannot run the simulation API; it shows an unavailable-service message.

Start performs one FB call with Start true; subsequent step/play calls release it. Enable withdrawal does not cancel this sample's accepted command. Stop applies on the next requested scan. Reset is one input pulse; two pulses without an intervening release scan remain a held signal. “重建 PLC 与工件” initializes a new native instance and plant, not a Reset input.

The view executes the **recorded agy conveyor candidate**, not arbitrary output from the current generation job. The 3D viewport uses locally built Three.js with orbit/zoom, default/top views, steel rollers, motor, parcel, photoeye and status lights. Its render loop never calls PLC APIs or advances the plant; position interpolation and roller motion are presentation only. If WebGL fails, the native controls and scan trace remain available.

Startup captures the original SCL bytes and all static assets into an immutable in-memory snapshot, checks that the download matches, and compiles those captured bytes. Served static assets and JSON API responses carry `X-PLC-Snapshot`; new sessions also report `asset_snapshot_sha256`. Editing/rebuilding or removing `web/dist` after startup cannot change the running source or pages. To load a new version, rebuild, restart the simulation service and refresh the browser page. Siemens syntax is adapted for matiec without changing transitions. Position/speed are synthetic: one energized call advances 20%; continuous playback waits 500ms between requests. The eight-call timeout does not mean eight seconds. Done is a single scan pulse preserved in the trace. This does not establish LAD execution, TIA/PLCSIM, mechanics or industrial acceptance.

Run the nine native simulation tests as part of the existing frontend suite:

```sh
SIM_IEC2C=/absolute/path/to/iec2c SIM_MATIEC_LIB=/absolute/path/to/matiec/lib npm --prefix web test
```

Without these variables native simulation tests are explicitly skipped, not passed. Build products and compiler logs/libraries remain outside tracked source. Research and acceptance details: [simulation plan](../plans/plc-simulation/task_plan.md).

## 启停双输出基准（S2）

页面可显式载入固定 `latch-start-stop-v1`，展示同一 FB 逻辑的 SCL 与实际串并联 LAD 图。只支持此 BOOL 合成合同；已有自由需求和原程序修改继续保留 SCL 路径。新图不是 Siemens 导入格式。完整运行、静态 IR 交接、真实工具范围与在线未验收边界见[闭环说明](../docs/SCL_CLOSED_LOOP.md#s2启停自锁双输出)。导出工程保留 IR、图和证据；重开只恢复历史，修改撤销旧验收。无产物的结构失败 IR 仍可诊断与导出。
