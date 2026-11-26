# PLC Agent execution protocol

The workbench has two model connections: **direct API configuration** and **external Agent control**. Both enter the same PLC-specific controller, `plc-workflow.py`; neither can issue verification verdicts or change the frozen contract. CM/Paperclip, mcode and the earlier CLI adapters are no longer runtime dependencies. The change concerns model access, not the supported PLC instruction set.

## Ordered gates

| Stage | Role | Required output and gate |
|---|---|---|
| 1. Analyze request | Engineer | Explicit specification, observable obligations and blocking questions. No executable logic yet; no invented process decisions. |
| 2. Review specification | Supervisor | Approve/reject/unknown with evidence. Unresolved questions and contradictions still block even if the supervisor approves. |
| 3. Freeze and generate | Engineer | The controller freezes the approved request, specification, verification goal and independent contract. The answer is a source candidate or the selected bounded IR proposal. |
| 4. Check the candidate | Controller and actual tools | Compile the captured SCL and run the selected fixed behavior contract. S2 also executes the serialized LAD graph. Tool failures remain failures; missing or unsupported checks remain unknown. |
| 4a. Scan semantics review | Semantic reviewer | After required tools pass, review persistent state, edges, simultaneous inputs and output timing against the supplied requirements and evidence. |
| 4b. Interface review | Interface reviewer | Concurrent separate review of I/O, SCL/LAD agreement, invocation model and unsupported claims on the same frozen candidate. |
| 5. Final review | Same supervisor role | Review the request, current candidate, actual tool evidence and both reviews. Unsupported review claims cannot override the contract. |
| 6. Deliver or retain | Program gate | Only required checks plus all reviews can produce a scoped `reviewed_draft`. Failed, cancelled or unknown candidates remain reviewable without current acceptance. |

The controller creates each stage packet and checks the answer's schema and input SHA-256. The supervisor is the same **role**, with complete current inputs supplied on each call; there is no hidden conversation or persistent model session. Separate review calls do not establish statistically independent failure modes. Project knowledge and original SCL are supplied as stage data with recorded provenance. No prompt, approval vote or Agent instruction can replace a programmatic gate.

S1 freezes `scl_compile` or `scl_behavior` as the goal. The explicitly selected `latch-start-stop-v1` additionally requires `lad_scl_compare`. Both controller and local bridge recompute the required-check gate. A compile-only draft remains behavior-unaccepted. Changed requirements, source, IR or LAD invalidate old evidence; imported records remain historical. There is no industrial-accepted state, automatic device download or physical I/O write.

## Direct API connection

```sh
npm --prefix web ci
npm --prefix web run build
npm --prefix web run dev
```

Open http://127.0.0.1:8766 and fill in **API 地址、模型、API Key** in the page. The base URL is the service prefix, for example `https://provider.example/v1`; the adapter appends `/chat/completions`. It implements OpenAI-compatible Chat Completions, not every vendor's native API. A local compatible model server can use loopback HTTP without a key; remote endpoints require HTTPS and a key. URL credentials, query strings and fragments are rejected.

Each stage is a fresh non-streaming request, with the full answer schema and no tools. JSON output defaults to `json_object`; a service without that option can use the explicit `none` setting. Local schema checks still apply in either mode. Refusals, truncated output, tool calls, multiple choices, invalid JSON and redirects fail closed; there is no automatic provider switch or retry.

Configuration lives in the local server's memory. The browser receives only non-secret fields and `api_key_set`; the password input is cleared on submit. Omitted keys are retained only for the same endpoint. Changing the endpoint requires its own key, and a rejected save leaves the old configuration intact. “清除密钥” removes it. Nothing is saved in a repository config, browser draft or engineering export. A configured indicator means configuration passed local validation, not that a real provider was contacted.

For terminal startup the optional environment variables are `PLC_API_BASE_URL`, `PLC_API_MODEL`, `PLC_API_KEY`, `PLC_API_TIMEOUT` and `PLC_API_RESPONSE_FORMAT`. The bridge passes configuration to its controller through stdin, never argv or runtime records, and removes `PLC_API_KEY` from the child environment. Use the page if shell configuration is unnecessary. Server restart requires configuration again unless it is supplied through the environment.

The request timeout defaults to 120 seconds and accepts 1–600 seconds; it is a network I/O timeout. The workflow has no wall-clock deadline by default; `--timeout SECONDS` bounds the whole task when desired. One workflow runs at a time, with its two review calls allowed concurrently. A task can make several model requests and incur the chosen provider's charges. Requirements, original source and stage evidence are sent to that provider when API generation starts.

## External Agent control

Select **Agent 接管** without configuring an API key. The page starts one controlled task and provides task-specific connection instructions. An external Agent on the same computer can read the currently available packets and submit structured answers. No particular Agent product, scheduler or MCP server is required.

### Preferred Skill and CLI entry

The same project Skill also supports finite `plc-agent.py simulate` requests for scene assembly, captured-source execution, faults, cases and trace export through the 8766 bridge. This simulation path does not answer generation-stage packets or confer generation acceptance. See the [simulation action protocol](PLC_SIMULATION.md) for exact payloads and the optional OIP bridge.

Load the repository's [plc-workspace-control Skill](../.agents/skills/plc-workspace-control/SKILL.md). It tells the Agent how to keep one CLI session open and answer each stage. The Skill is repository-scoped; agents that do not discover this folder can read its file explicitly. It is not a global personal-skill installation or a second workflow engine.

```sh
python3 web/scripts/plc-agent.py doctor
python3 web/scripts/plc-agent.py prepare --brief /outside/repo/brief.json
python3 web/scripts/plc-agent.py workflow --request /outside/repo/task.json
```

`prepare` accepts confirmed brief data (or `{brief,states}`) and emits the same validated, fingerprinted request used by the page. Save that JSON outside the repository before passing it to `workflow`. It does not infer process choices. To use a nondefault local address, put `--url http://127.0.0.1:PORT` before the command.

For a page-created task, run `workflow --attach` and write the page's `{job_id,agent_token}` JSON to **stdin's first line**, keeping the process alive. The CLI temporarily disables terminal echo where supported and keeps the credential in process memory. Do not pipe one line and close stdin, put the token into command arguments, or save it as configuration. No private token file is introduced.

The CLI emits one JSON object per line with `type`: `started`, `packets`, `answer_accepted`, `answer_rejected`, or `finished`. On `packets`, use the supplied instructions/data/schema and write one `{packet_id,input_sha256,answer}` JSON line per answer back to the same process. Rejected answers can be corrected; an acceptance event only confirms receipt of that answer. Empty waits are normal during native checks. The terminal event includes the actual job snapshot, including any retained failed candidate.

Write `{"command":"cancel"}` to request cancellation, then wait for `finished`. EOF, Ctrl-C and unexpected transport failure also initiate bounded cleanup; if cleanup cannot be confirmed, the CLI reports that uncertainty rather than success. `status JOB_ID` and `cancel JOB_ID` support follow-up. No CLI command runs model shell commands or changes PLC expectations. The same Python controller remains the sole owner of stage advancement and verification verdicts.

### Underlying local HTTP protocol

| Request | Body / authorization | Response |
|---|---|---|
| `POST /api/agent/jobs` | `{ "request": ... }` | `202` with `job_id` and a one-task `agent_token` |
| `GET /api/agent/jobs/<id>/packets` | `Authorization: Bearer <agent_token>` | `status`, `finished`, and pending `packets` |
| `POST /api/agent/jobs/<id>/answers` | Bearer token; `{ "packet_id": "...", "input_sha256": "...", "answer": { ... } }` | `{ "accepted": true }` for a schema-valid stage answer |
| `GET /api/jobs/<id>` | Local connection | Current outcome, candidate and actual verification evidence |
| `POST /api/jobs/<id>/cancel` | `{}` | Cancellation requested; poll until `finished` |

All POSTs require `Content-Type: application/json` and `X-PLC-Workspace: 1`. Browser requests must be same-origin. The service listens only on `127.0.0.1`. The token goes in the authorization header, never a URL. It is shown only during the active UI task, stored in server memory, and excluded from snapshots, runtime files and engineering exports. A new task gets a new token; answers after completion or cancellation are refused.

Each pending item contains `packet_id`, `input_sha256`, `stage`, `role` and `packet`. The Agent must follow `packet.instructions`, use `packet.data`, and return exactly the object described by `packet.schema`. Echo the packet ID and hash unchanged. Unknown stages, altered hashes, extra answer fields, schema failures and credential echoes are rejected; malformed answers do not consume the packet. A successfully submitted packet cannot be replayed. Empty `packets` can mean the controller is checking source or preparing the next stage; only terminal status with `finished` indicates the task has ended.

The controller may expose the two reviewer packets together. The Agent may process them in separate sessions; the workbench cannot prove the Agent used independent models or thought processes. It can enforce packet identity, sequencing, source provenance and its own tool verdicts. Answer submission accepts a **stage response**, not the engineering. A repair packet permits only current SCL or, for S2, IR changes. It never offers a way to edit tests, expectations or authoritative pass/fail records.

Remote cloud Agents cannot reach this loopback address without an explicitly arranged local execution channel. Static hosting retains the existing task/result file handoff, but that import does not gain current verification authority. This change does not create a public remote execution service.

## Cancellation, records and recovery

The bridge signals the controller. Waiting Agent dispatches share a cancellation event, including both reviewer threads. Native validation cancellation reaps its worker process group. If an API network wait prevents the controller from exiting, the bridge kills that local process group after a five-second grace period. Cancellation revokes current acceptance and prevents new stages. It does not promise that a provider has stopped remote computation or billing; the workbench does not own an external Agent process either.

The bridge retains the latest eight jobs in memory. Requests, loaded knowledge, stage packets, answers, candidate revisions and actual diagnostics are stored outside Git under `--runtime-root`; its default is the system temporary directory's `plc-workspace-runs`. Use a persistent external directory if records must survive system cleanup. Key/token data are not written there. The last valid candidate can be recovered after a failure; recovery never upgrades missing checks.

Actual compiler/behavior failures and supported review findings may enter a bounded repair loop (default two repairs; direct controller `--max-repairs 0..5`). Unknown tool delivery stops instead of spending repair attempts. `plc-workflow.py audit --provider api --request ... --candidate ... --runtime ...` can review an existing structured candidate with API config on stdin; `audit_complete` is a read-only handoff and never establishes a new generation's acceptance.

## S2: bounded IR branch

Only an unchanged, explicitly selected synthetic `latch-start-stop-v1` brief enters this branch. The model returns a bound BOOL IR proposal; the controller deterministically produces both SCL and actual LAD graph logic. Repairs can change only IR, after which both outputs are regenerated and rechecked against fixed expectations. A tool `unknown` cannot enter automatic repair or become a pass. The graph is an internal review/execution format, not Siemens project serialization. State/count instructions, another dual-output benchmark and TIA integration remain later slices.

Implementation: [controller](../web/scripts/plc-workflow.py), [API adapter](../web/scripts/model-api.py), [Agent dispatcher](../web/scripts/agent-dispatch.py), [gate regressions](../web/scripts/test_plc_workflow.py), [Agent protocol tests](../web/scripts/test_agent_control.py). The current source/behavior and evidence limits remain in [the SCL loop](SCL_CLOSED_LOOP.md). Local HTTP and Agent-answer fixtures test the connection and gates; they do not substitute for a real configured model's generation/repair acceptance.

A separate 2026-11-23 actual Agent run followed the repository Skill and CLI for `latch-start-stop-v1`: all six stage answers were accepted, the first candidate passed actual native and graph checks, and the CLI exited successfully. No repair or cancellation was triggered in that run. This supports the observed first-generation path only; remote API services, actual Agent diagnostic repair, and Siemens/machine acceptance remain separate. Exact scope and identities are recorded in [progress](../plans/plc-logic-harness-v1/progress.md).
