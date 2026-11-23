# Progress — PLC Logic Harness v1

## Current

2026-11-23：用户授权“你来做，做好推”，以 `master@984bf841f8eb969770acb6fc4fc6e605d43fcf93` 为基线完成 S2 的确定性实现与离线复验。新增显式 `latch-start-stop-v1` 合成启停合同、小型 BOOL IR、SCL / 实际 LAD 图双输出、独立执行与预期、有限 IR 修复、页面审阅/导出/重开及自动回归。

**S2 的确定性代码和离线工具检查完成；直接 API 配置和外部 Agent 控制已替换旧编排依赖，真实模型规格→IR→生成→修复仍未验收。** S1 在线开放项保留；S3/S4 未开始。未改规范 FB_MainSequence、原输送带控制源码或现场配置，不授予 TIA / PLCSIM / 实机 / 安全验收。

## 2026-11-23 S2 实测

| 检查 | 本轮结果与范围 |
|---|---|
| JavaScript | 28/28，通过，无跳过；含图连线/触点极性、产物哈希、历史导入、IR-only 失败草稿 |
| Python | 109/109，通过，无跳过；含既有 S1、真实编译/图执行、有限 IR 修复与负向门禁 |
| 正确启停候选 | 每条路径 14 命名场景 / 64 拍 + 全部 4,096 四拍输入序列 / 16,384 拍；原生 SCL 与序列化 LAD 分别符合独立预期 |
| 已知错误 | 5 类可编译语义错误均 fail，且两种输出仍相互一致；重复输出写入由结构明确 fail |
| 生命周期 | 两实例交错调用、重建初始化通过；并非掉电保持测试 |
| 修复 | 显式模型夹具交付坏 IR，真实工具拒绝，一轮修 IR 后两个产物重生并通过；预算耗尽拒绝，缺工具/混合 unknown 不修复 |
| 交付 | 真实 CLI 正/负工程载入实际 generation.js 的 jsdom DOM；节点、连线、极性逐项对应，导出/重开保留历史、修改撤销验收；API 回合为夹具 |
| 图形核对 | 从真实 CLI 工程提取并联网络 SVG，经 Inkscape 标准渲染后检查布局；没有宣称浏览器截图验收 |
| 构建/维护 | 静态 build、规范投影 `--check`、固定 actionlint 1.7.12、`git diff --check` 均通过 |

真实工具：matiec `3a41303bcb4e50403417bc39c63f88981d7d961e`、GCC 14.2.0、Python 3.12.14、Node 24.22.3。第三方编译器留在仓库外。规范 PLC 控制程序和已存证明未改；没有重新声明旧形式证明为本轮新证明。

本次独立审查发现并修复两类门禁风险：缺失 IR/LAD 产物的空指纹不能匹配成通过；必选工具 unknown 与语义 fail 混合时禁止继续自动修复。结构错误 IR 尚无产物时另保留明确 fail 的诊断草稿，避免为了展示强行补齐伪产物。共享提示词明确新图与 SCL 是同一 FB 的两种表达，无需另加调用壳。

新增 `.github/workflows/plc-logic-checks.yml`：在仓库外构建固定版本 matiec，运行模型/图展示测试、真实原生测试和门禁测试，任何 skip 都使该 CI 失败；自动构建与投影检查。修正旧发布工作流过时的 README 文字探针，检查实际维护的发布说明。推送后的远端执行状态须按 GitHub 当前记录另查，不把本地通过写作远端已通过。

复验命令：

```sh
SIM_IEC2C=/outside/repo/matiec/iec2c \
SIM_MATIEC_LIB=/outside/repo/matiec/lib \
npm --prefix web test
npm --prefix web run build
python3 validation/scripts/sync-semantics.py --project projects/FB_MainSequence --check

SIM_IEC2C=/outside/repo/matiec/iec2c \
SIM_MATIEC_LIB=/outside/repo/matiec/lib \
python3 web/scripts/check-latch.py --example --output /outside/repo/fresh-latch-run
```

`--example` 是明确手写 IR 夹具，不调用模型。检查报告及工程仍可导出；重开仅为历史记录。Chromium 在当前环境因 socket EPERM 无法启动，因此没有完整浏览器可视验收；已完成实际 DOM 与 SVG 产物检查。在线 mcode/CM 不可用，无法把夹具回合记作在线通过。

## 2026-11-22 合流历史

2026-11-22：独立核对 `master@55d720452f5d4e8c942428185d1ce069f732e15f` 与 PR #5 原始 `8096582220e18aae7df0272b57666f6be287806a`，共同祖先为 `69793f43e9f52d73248c9f0116c8b60efdd12eff`。master 已通过 [#7](https://github.com/qiaoqiao2521/plc-workspace/pull/7) 实现部分 S1；本次在 [#5](https://github.com/qiaoqiao2521/plc-workspace/pull/5) 合流，保留主干防线并统一到 `verification-policy.py`，不保留两套判定实现。S1 确定性实现与离线回归见下方；真实在线 mcode/CM 验收仍开放，S2–S4 未开始。

S0 计划已随 PR #4 合并。本次不修改 PLC 控制逻辑、扫描合同、规范 ST 或现场配置，不授予 LAD、形式化、Siemens 或实机验收。

## Done

- S1 报告 v2 分开源文件结构、编译、行为、LAD/SCL 对照和 TIA；目标及必选项由请求确定，工作流与桥接通过共享策略重新判定。
- 保留 master 的需求/源码/固定合同绑定、非空源码、空扫描结果拒绝、取消留证及损坏进度文件容错；这些能力不能被旧 PR 文件覆盖。
- 保留 PR 的固定五项检查、每项 target/required、分范围 acceptance 与前端分项展示；缺失、重复、豁免、失败、未知、未运行、旧报告均不能授予当前验收。
- 取消或失败会清除外层与嵌套工作流的有效验收，保留当前候选及已完成的工具观察。编译通过而行为未执行明确显示“编译通过，行为未验收”。
- 工程导入只恢复历史记录；需求或源码改变使旧报告失效，再次启动生成也撤销上一轮当前验收。

## 2026-11-22 独立复验

合流前的独立负向探针已复现：PR 原始版本把零扫描场景判为 pass；损坏 worker-progress 导致异常且未保存报告；本机桥接可接受空源码、缺失或改写的行为合同；取消后嵌套 workflow 残留 reviewed_draft/result/acceptance。master 分别已有相应防线，合流回归保留并扩展这些拒绝条件。

本次对两个原始分支和合流结果分别重跑：

| 检查对象 | JavaScript | Python（含真实原生） | 构建 |
|---|---|---|---|
| master `55d7204` | 18/18 | 56/56 | 通过 |
| PR 原始 `8096582` | 20/20 | 62/62 | 通过 |
| 本次合流实现 | 21/21 | 76/76 | 通过 |

三次完整测试均无跳过。使用真实 `beremiz/matiec@3a41303bcb4e50403417bc39c63f88981d7d961e`、GCC 14.2.0、Python 3.12.14、Node 24.22.3；工具在仓库外构建，未改项目依赖。合流另通过验证判定工具 10 项、投影工具 4 项及 `sync-semantics.py --check`。规范 PLC 控制程序、扫描合同、validation、container、既有候选和 package/lock 相对 master 均无改动。

前端运行真实 `generation.js` 的 jsdom DOM 回归，API 为显式夹具：编译级、行为级、行为失败、缺工具、取消五类结果均正确展示五项检查；导出、重开降为历史记录、需求编辑失效均通过；额外验证重跑失败撤销旧验收、取消等待清理完成。尝试无头 Chromium 时被环境 `socket() EPERM` 阻断，因此本次不宣称浏览器可视验收。原始 PR 的浏览器记录仍属于历史证据。

原生负向用例覆盖旧八拍阈值、真实 BOOL 类型错误、错误 Start 边沿、无限扫描 watchdog 和实际 worker 取消。修复步骤中的模型回答仍为夹具；真实在线 mcode/CM、TIA、PLCSIM、现场设备及新形式证明未执行。

复验命令：

```sh
SIM_IEC2C=/outside/repo/matiec/iec2c \
SIM_MATIEC_LIB=/outside/repo/matiec/lib \
npm --prefix web test
npm --prefix web run build
python3 validation/scripts/sync-semantics.py --check
```

固定行为只覆盖 `conveyor-12-v1` 的五场景/42 次原生调用。模型应答和浏览器 API 如使用夹具均显式标识，不作为真实在线验收。GitHub 当前工作流检查文档、发布配置及 workflow 自身，未自动执行 S1 测试；CI 通过不替代这里的本地复验。

## Remaining

- S1：使用实际配置的 API 或 Agent 完成当前源码生成、检查、修复在线回合；记录取消对本机与服务商的实际边界。
- S2：用实际配置的 API 或 Agent 补一次真实规格→IR→双输出→实际检查，以及真实诊断驱动的修复/取消记录；不得用夹具关闭。
- S3：按原合同增加输送带有限状态与扫描计数，完成两种产物行为对照。
- S4：有明确需求和环境后，单独验证最薄 TIA 适配；不是前三项的默认依赖。

## Next

本轮止于用户授权的 S2 确定性闭环，继续保留 S1/S2 在线验收开放项。配置实际 API 或 Agent 后，使用同一个启停基准完成真实生成、失败诊断、修复与取消验收，再决定是否开展 S3；不要安装替代编排平台或扩大指令集。基准通过只覆盖明示合同，不替真实设备决定工艺或功能安全策略。

## 2026-11-23 接入改造完成：API / Agent

基线 `master@39652b34e704bc4c4310cde9176ea1129e0b8724`。用户指出已不用 CM/Paperclip，授权直接配置模型 API、由 Agent 控制。旧 mcode/CM 与 agy/ZCode 执行入口已删除，`mcode-workflow.py` 更名为 `plc-workflow.py`，保留原 PLC 门禁。页面增加 API 配置和 Agent 接管，同步 README、现行协议、项目入口与计划；旧编排计划明确为历史。

- API：OpenAI 兼容 Chat Completions；独立阶段请求、完整输出 schema，无工具、重定向、自动重试或供应商切换。密钥保存在服务内存，子进程只从 stdin 收配置，更换端点不继承旧密钥，浏览器/证据/导出不保存凭据。
- Agent：任务专属令牌、控制器生成的待办包、当前输入 hash、schema 校验和单次提交。越阶段、错误 hash、重放、伪造验收和令牌回流均拒绝。没有增加新角色或通用调度器。
- 取消：两个 Agent reviewer 等待可同时退出；两个 API reviewer 都挂起时，五秒宽限后实际回收本机进程组。页面等待 `finished`，失败/取消保持候选但无当前验收。远端模型计算与计费不作取消保证。

实际执行结果（同日）：

| 检查 | 结果 |
|---|---|
| `SIM_IEC2C=... SIM_MATIEC_LIB=... npm --prefix web test` | 31 个 JS + 139 个 Python 测试通过；无跳过。Python 47.635 秒。 |
| API transport | 15 项真实本机 HTTP 测试，包含配置、消息隔离、响应拒绝、重定向与凭据边界。 |
| Agent 协议 | 9 项真实 HTTP/控制器测试，包含并发重复提交、越权/过期输入、未决阻断、坏 IR 修复与等待取消。 |
| API 完整流程 | 2 项真实 HTTP/子进程集成：坏 IR 修复后经 matiec/GCC 与 LAD 检查通过；两个 reviewer 挂起后实际触发五秒取消兜底。 |
| 构建与旧核心 | `npm --prefix web run build`、`sync-semantics.py --project projects/FB_MainSequence --check`、actionlint 1.7.12、`git diff --check` 通过。 |
| 实际页面 DOM | 配置、密钥清空/失败恢复、Agent 接管/断线重读/取消、四种 S2 结果、清理完成后解锁及导出历史失效通过；未声称完整浏览器可视验收。 |

上述 API / Agent 的模型回答均为明确脚本夹具；HTTP、控制器、编译器与 LAD 产物执行是真实运行。工具仍使用 matiec `3a41303bcb4e50403417bc39c63f88981d7d961e`、GCC 14.2.0、Python 3.12.14、Node 24.22.3。没有使用实际模型凭据或付费模型调用，不能关闭真实模型的 S1/S2 生成与修复验收。TIA、PLCSIM、机器和安全验收仍未执行；S3/S4 未开始。

## 同日追加：Skill / CLI 工作流与实际 Agent 试跑

用户进一步要求 Agent 接管以 Skill、CLI、workflow 接入。新增仓库技能 `.agents/skills/plc-workspace-control/` 与 `web/scripts/plc-agent.py`。技能指导操作；CLI 只准备同格式请求、持续收发当前阶段答案与取消；既有控制器继续拥有阶段和验收权。页面复制说明优先使用该 Skill 和 `workflow --attach`，凭据仅通过 stdin 传入进程内存，无凭据文件、任意模型命令执行或第二套编排。

CLI 的 7 项实际 HTTP/子进程集成回归全部通过，含 prepare、当前任务接管、错误答案重提、EOF/SIGINT、坏令牌不取消他人任务、重定向拒绝、凭据不外泄与真实 native/LAD 闭环。回归发现并修正了持续 stdin 打开时退出的缓冲锁问题。新增 Skill 通过官方 quick_validate；最终完整回归为 **31 个 JS + 146 个 Python 测试通过、无跳过**（Python 52.505 秒），构建与差异检查通过。此处自动测试中的模型回答仍为显式夹具。

另起一个没有继承实现讨论的实际 Agent，按 Skill 使用真实 CLI 完成固定启停任务，没有把测试回答提供给它，也没有读取测试答案填包。实际结果：

| 项目 | 记录 |
|---|---|
| job_id | `08ea8343-c95a-4f78-b6f6-a41803d38dfa` |
| 合同 | `latch-start-stop-v1`，固定 BOOL 启停合成需求 |
| 过程 | 分析、规格审阅、IR 生成、语义审阅、接口审阅、最终审阅共 6 个答案均首次接收；接口审阅由独立子会话处理既有角色包 |
| 真实工具 | matiec/GCC 编译后的持久 FB 与序列化 LAD 图分别运行独立预期，每条路径 16,448 次调用 |
| 结果 | `complete` / `reviewed_draft` / `lad_scl_pass`；四项必选检查 pass，TIA not_run，industrial_acceptance not_run |
| 修复/反例 | 仅 attempt-0，0 次修复，无反例；本轮没有触发实际 Agent 修复或取消 |
| CLI | finished=true，退出码 0，试跑服务已清理 |
| 请求指纹 | `0b21c78a1a18c1e7f128b9f7fbdad4cc43e7aef1d99c61a86844c4523ab4d583` |
| SCL 文件 | `FB_StartStop.scl`，SHA-256 `3103361a0ce84d57f0bfe8cdcdc035e32ddf08a4ddcaf94d4f4467a232a6ab7c` |
| IR | SHA-256 `3310e467bc2316bef2450d622ac0971ec9d1ec2e2d9e9ed8e0d4ae602dd22262` |
| LAD 图 | SHA-256 `1d7c659605f4cfc11404420a5a3ca344fcbcd6b15e9f93ecb755aeea6020b2a8` |

主代理复核实际 outcome、validation、阶段记录及文件哈希一致。该试跑使用当前对话 Agent 作答，不是用户配置的远端 API 模型，也不是脚本答案夹具。初始独立执行会话不能共享回环网络；在同一默认权限父进程内启动工作台与 CLI 后完成，没有变更网络隔离或提升权限。

这条记录只关闭首轮实际 Agent 成功路径的运行空白，不外推通用准确率，不把同模型审阅等同统计独立证明。远端 API 服务实际验收、实际 Agent 反例驱动修复/取消仍开放；规范核心、旧输送带合同、TIA 与 S3/S4 边界未改变。运行目录仍按现有规则留在仓库外，不提交原始运行包或凭据。
