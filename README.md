# PLC Workspace

让人输入需求或工艺流程，由 AI 整理状态机、I/O 与约束，生成 **Main LAD / FB SCL** 工程草稿，再验证该工程的扫描行为与逻辑。

验证工具与抽象顺控示例负责约束 Agent 的质量；产品入口是需求到工程的生成工作台。

## 本机运行

需要 Node 24 和 Python 3.10+。先安装锁定的 Three.js 依赖；启动后可直接配置模型 API，也可由外部 Agent 接管任务。

```sh
npm --prefix web ci
npm --prefix web run build
npm --prefix web run dev
```

打开 http://127.0.0.1:8766，选择一种接入方式：

1. **直接 API**：在页面填写 Base URL、模型和 API Key，保存后点击“API 生成”。支持 OpenAI 兼容 Chat Completions；本地兼容模型也可接入。密钥只保存在本机服务内存，重启后重新配置。
2. **Agent 控制**：让 Agent 加载仓库的 `plc-workspace-control` Skill。点击“Agent 接管”后复制说明，Agent 通过 CLI 领取阶段、提交答案并等待检查/修复；无需工作台配置模型密钥。

两种方式都经过需求分析、规格审阅、生成、真实工具检查、有限修复和最终审阅。工程仍可审阅与导出。CM/Paperclip、mcode 和公司 ID 已从运行要求中移除。

本次 SCL 的真实 Linux 检查需配置 `SIM_IEC2C` 和 `SIM_MATIEC_LIB`。工作台提供“输送带 12 次等待验收”，将原程序、专业资料、编译/逐扫描反馈和有限修复循环接入同一任务。见[当前 SCL 闭环](docs/SCL_CLOSED_LOOP.md)。缺工具时保留候选与原因，不放行。

本机控制器约束两种接入：未决工艺阻断生成，必选检查的 fail/unknown/not_run 不放行，Agent 不能修改冻结的验收预期或签发工具通过。默认整条任务不限时，API 请求默认 120 秒超时；同时处理一份工程并支持取消。服务只监听本机。API 生成会把需求、原程序和阶段资料发送给所选模型服务，可能产生调用费用；“已配置”仅表示配置有效。详见[执行规范与 Agent 接口](docs/PLC_AGENT_WORKFLOW.md)。

公开静态网站没有本机桥接时，可导出 Agent 任务并导入对应结果。云端生成服务尚未接入。

## Agent 的 Skill、CLI 与工作流

[plc-workspace-control](.agents/skills/plc-workspace-control/SKILL.md) 随仓库提供。支持项目技能的 Agent 可加载它；其他 Agent 可以直接读取这个文件。它指导 Agent 调用同一个 CLI，不要求特定客户端或编排服务。

```sh
# 检查已启动的本机工作台
python3 web/scripts/plc-agent.py doctor

# 用已导出的任务开启持续会话
python3 web/scripts/plc-agent.py workflow --request /outside/repo/task.json
```

CLI 通过逐行 JSON 与 Agent 交互：输出当前阶段包，接收结构化答案，直到返回最终结果。页面已有的任务用 `workflow --attach` 接管，凭据只经该进程 stdin 传入并留在内存。直接从需求启动时，也可用 `prepare --brief brief.json` 建立请求。具体步骤与取消方式由 Skill 说明。

**Skill 指导如何工作，CLI 负责接入，PLC 控制器执行门禁。** 分析、规格审阅、实际编译/行为检查、有限修复和最终裁决仍是同一条工作流；Agent 不能靠改提示词绕过检查。

## 当前能力

- 中文需求、流程顺序与逐状态动作/完成条件编辑。
- 直接模型 API 或外部 Agent 按相同阶段门禁生成、审阅结构化规格、I/O、SCL 和 LAD 网络草稿。
- 请求与结果绑定需求指纹；需求变化后旧结果过期。
- SCL 文件、LAD 网络规格与工程草稿导出。
- **启停自锁合成基准**：AI 提议受限 BOOL IR，程序生成包含真实串并联逻辑的 LAD 图和 SCL；分别执行后对照固定预期。该路径只支持明确选择的基准，不将它套用到任意工艺。
- [验证与回放](web/README.md)：仓库已有 FB_MainSequence 的 6 个实际 ST 场景。
- [可组装仿真](docs/PLC_SIMULATION.md)：当前工程源码驱动开关、灯、电机、输送、光电、气缸与工件；三维组装、单步、故障注入、独立用例和逐扫描反例共用一套原生执行服务。Agent 可通过同一 CLI 操作，可选 Open Industry Project 物理复核。

普通任务的 LAD 仍为简单串联触点/线圈与周期 FB 调用网络的审阅表示。启停基准新增内部 LAD 图及其独立执行入口，仍不是 TIA 可导入工程。默认流程对当前 SCL 运行支持范围内的 Linux 编译，选择输送带合同后执行其固定扫描；仓库示例的 27 项扫描测试、32 条断言不适用于任意新工程。TIA、PLCSIM 和实机验收由 Windows 工程侧完成。

## 运行可组装仿真

配置既有 `SIM_IEC2C`、`SIM_MATIEC_LIB` 后，启动上面的同一工作台服务，从“仿真验证”进入 `http://127.0.0.1:8766/simulator.html`。生成结果可直接点击“在仿真中验证”，也可从模板开始组装。仿真无需配置模型密钥。

```sh
python3 web/scripts/plc-agent.py simulate catalog
python3 web/scripts/plc-agent.py simulate templates --output /tmp/plc-templates.json
```

四种明确合同、场景 JSON、完整 CLI/HTTP 动作和可选 OIP 安装见[仿真说明](docs/PLC_SIMULATION.md)。交互观察、固定用例通过、OIP 上游自测与当前源码驱动物理场景分别留证；新入口不恢复旧工程验收，也不授予 TIA/PLCSIM/实机验收。实际测试记录见[接入进度](plans/plc-composable-simulation/progress.md)。

西门子官方同类实现、版本矩阵、模型与时钟约束及后续接入顺序见[官方仿真基线](docs/SIEMENS_SIMULATION_BASELINE.md)。[机器可读来源与缺口索引](web/data/simulation/siemens-reference-index.json) 供 Agent 复核；它是研究资料，未注册或执行 Siemens 后端。

## 复验启停双输出

不依赖在线模型即可运行明确标注的确定性基准，检查本机生成与验证链：

```sh
SIM_IEC2C=/absolute/path/to/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
python3 web/scripts/check-latch.py --example --output /outside/repo/fresh-latch-run
```

检查后在页面“打开工程草稿”载入输出目录的 `engineering.json`，可审阅 SCL、LAD 图、逐项结果并导出。`--example` 是手写 IR 夹具，不调用 AI；重开记录只显示历史证据，不恢复本次会话验收。已记录一次实际 Agent 按 Skill/CLI 完成启停基准的首轮生成；远端模型 API 和实际 Agent 诊断修复仍需单独验收，本地协议夹具不替代它们。静态任务的 IR 交接和完整边界见[双输出说明](docs/SCL_CLOSED_LOOP.md#s2启停自锁双输出)。

## 接续入口

- [PROJECT.md](PROJECT.md)：产品意图、现状与边界。
- [前端与本机生成](web/README.md)：请求格式、运行和导出。
- [扫描契约](projects/FB_MainSequence/01_specs/scan-contract.md)：已有核心的准确语义。
- [语义验证](validation/tests/README.md)：真实编译 ST 与形式门禁。
- [容器验证环境](docs/validation-setup.md)：原有 Windows/Linux 工具链步骤。
- [架构](docs/ARCHITECTURE.md)：生成入口与验证层之间的关系。
