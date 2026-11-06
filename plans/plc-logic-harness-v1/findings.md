# Findings — PLC Logic Harness v1

核对日期：2026-11-06。对象：`qiaoqiao2521/plc-workspace`，`master@4089870acb6a70acaf5bd0ca196d9d7ed88b1690`。
本文件区分源码/文档事实、方案判断与尚未验收的能力。原计划 S0 未重跑工具；后续 S1 的实际执行记录单列于下方，不与基线事实混用。

## SpecMesh 的实际边界

已读取 [SpecMesh README](https://github.com/qiaoqiao2521/specmesh/blob/main/README.md) 和 [规范 SPEC.md](https://github.com/qiaoqiao2521/specmesh/blob/main/SPEC.md) 的目标、最小文件系统、职责、工作流及复用/审查规则。

规范版本为 v1.1.0；README 中 v1.3.0 是可选运行时分发版本，不能混为一谈。规范要求从 `AGENTS.md` → `PROJECT.md` 渐进读取，并用 `plans/<task>/{task_plan,findings,progress}.md` 保存复杂任务。SpecMesh 不接管实现、模型调度或 Harness Loop。本计划不安装其可选运行时，不修改 SpecMesh 仓库。

## PLC 已有能力与限制

| 来源 | 本次实际确认 | 不能由此推导 |
|---|---|---|
| [PROJECT.md](../../PROJECT.md)、[AGENTS.md](../../AGENTS.md) | 已有 Main LAD / FB SCL 方向、规范 ST 与抽象扫描契约；模型与工具验收应分开 | 历史测试记录是本轮重新验收 |
| [SCL_CLOSED_LOOP.md](../../docs/SCL_CLOSED_LOOP.md) | 现有路径加载知识与原程序，调用 matiec，使用固定合同，允许有限源码修复；文档明确在线 mcode/CM 与 TIA 尚未验收 | 固定夹具回归证明真实模型会按诊断修复 |
| [candidate-validation.py](../../web/scripts/candidate-validation.py)（本轮读 1–220 行） | 命名行为合同是 `conveyor-12-v1`；真实编译之后可执行固定扫描；无 profile 时 `scan_contract=not_run`，但总 `status` 仍可为 `pass` | 所有新任务均有行为测试 |
| [mcode-workflow.py](../../web/scripts/mcode-workflow.py)（本轮读 160–305、330–文件末尾） | 未决规格阻断生成；工具报告来源关联；工具 pass 后进入文本审阅，全部审阅通过可成为 `reviewed_draft`；修复不允许修改冻结测试与需求 | `reviewed_draft` 等同逻辑、Siemens 或机器验收 |
| [generation-model.js](../../web/generation-model.js) | LAD 结构只有串联 contacts 的 rung 与 FB call；提示词明确并联/定时器等尚不支持；现有校验说明它只是显示/传输校验 | 已有通用 LAD 图生成、导入或执行 |
| [DECISIONS.md](../../docs/DECISIONS.md) | 输送带合同与抽象核心的 Enable/Reset 行为不得混套；历史对抗测试曾发现独立预期被实现派生值污染的问题 | 来自同一 IR 的两份产物一致就足以自证正确 |

上述路径可在固定基线查看：`https://github.com/qiaoqiao2521/plc-workspace/tree/4089870acb6a70acaf5bd0ca196d9d7ed88b1690`。本文相对链接方便接续；实现后应结合基线识别差异。

## 直接影响方案的判断

1. 首先收紧**判定范围**，不是先增加审阅 Agent。当前文档没有声称工业验收已完成；问题在于下一步应避免把编译级总 pass 沿用为新“逻辑已验证”的入口。
2. LAD 最大缺口是可检查的实际逻辑图与产物级行为验证，不是再增加一个 SCL FB 调用示意。先做一个串并联启停样例，再扩状态/计数。
3. 同源生成解决一致性维护，不自动证明需求正确或两个后端实现正确。独立预期、错误变体、实际产物执行不可省略。
4. 保留现有源码检查路径；新增 IR 只负责明示支持的生成子集。不承诺任意 SCL↔LAD 自动翻译。
5. 不强绑博途与“不借鉴博途”是两回事。平台格式、版本和运行语义只有完成对应核实/实验后才进入能力声明。

## S1 实施核对

实施基线为 PR #4 合并提交 `69793f43e9f52d73248c9f0116c8b60efdd12eff`。上方源码表是原计划基线事实，下面是此次新增结果：

- `verification-policy.py` 明确定义目标及必选检查，检查器生成分项报告，工作流与桥接重新计算门禁；不再把无范围的总 pass 当成逻辑通过。
- 无行为合同的真实编译返回 `target=scl_compile`，行为、LAD/SCL 对照和 TIA 均为 not_run；行为验收为 false。选定输送带合同后，scan_contract 变为必选，不能临时豁免。
- 同一份原八次等待源码可编译，但不满足十二次行为合同，必须拒绝；十二次候选的五场景/42 次原生调用通过。缺工具保留 unknown，不能和源码行为 fail 混为一谈。
- SIGTERM 原先抛出的 InterruptedError 可能被 Python subprocess 的 selector 当作系统中断吞掉。改为可可靠解栈的取消路径，实际信号测试确认 worker 已回收；编译已完成的事实保留，但取消、超时和崩溃都不产生当前验收。
- 新报告关联既有需求指纹；源码相同但需求变化也拒绝旧报告。旧报告仍可打开和导出，当前控制器不接受它作为新门禁证据。
- 页面使用本次完成的受信工作流上下文区分有效验收和历史记录；导入文件自称 reviewed_draft 或 acceptance=true 不会恢复本次验收。

本轮可运行 checkout 与编译器可用，已执行新检查；原计划“无 checkout/未执行”的限制应按其历史范围理解。真实在线 mcode/CM 与 TIA 仍未运行。离线验收中的模型应答和浏览器 API 是显式夹具，不能证明在线模型会正确生成或修复。

复验入口：`SIM_IEC2C=/absolute/path/to/iec2c SIM_MATIEC_LIB=/absolute/path/to/matiec/lib npm --prefix web test`，以及 `npm --prefix web run build`。真实工具使用 matiec `3a41303bcb4e50403417bc39c63f88981d7d961e`。门禁矩阵、取消和恢复回归均在现有 `web/scripts/test_*` / `test-generation.mjs` 内；浏览器另检查编译级、行为级、失败、缺工具及取消结果的分项展示、导出、重开和编辑后失效。

## 调查报告的使用方式（计划依据）

用户提供的《工业PLC代码生成架构（LAD与SCL）及确定性验证工程研究报告》作为方向输入：需求约束、确定性构建、编译反馈、扫描测试、形式验证边界与人类工程责任。

本轮未重新核实其中的供应商版本/工具数量、SIMATIC SD 支持矩阵、论文准确率、许可条件或参考实现完整源码；这些不得写成本仓库已实现、已适配或确定可复用的事实。报告的“近100%”不作为产品验收口径。也不把其整套大型工业交付流程一次搬入首版。

本计划不采纳先前答复中“同一 IR 就能证明两出口等价”的过强推断：证明需要明确模型、假设、范围及独立证据；有限测试只支持所测范围。

## S0 计划阶段限制（历史）

- 只检查远端已提交基线和上表所列范围，未检查用户本机的暂存、未暂存、未跟踪文件或外置工程资产。
- 容器尝试只读克隆时无法解析 github.com，未取得可运行 checkout；后续使用已连接 GitHub 读取，不据此宣称本地构建或测试通过。
- 未运行 SpecMesh 可选运行时、matiec、PLCverif、mcode/CM、TIA、PLCSIM 或实机检查；本次是文档计划，不产生新的 PLC 正确性证据。
- 当前没有新的供应商选型结论，没有调整既有定时任务，没有自动合并或发布任何控制程序。
