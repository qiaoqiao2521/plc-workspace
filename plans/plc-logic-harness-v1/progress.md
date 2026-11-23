# Progress — PLC Logic Harness v1

## Current

2026-11-23：用户授权“你来做，做好推”，以 `master@984bf841f8eb969770acb6fc4fc6e605d43fcf93` 为基线完成 S2 的确定性实现与离线复验。新增显式 `latch-start-stop-v1` 合成启停合同、小型 BOOL IR、SCL / 实际 LAD 图双输出、独立执行与预期、有限 IR 修复、页面审阅/导出/重开及自动回归。

**S2 的确定性代码和离线工具检查完成；真实在线 mcode/CM 规格→IR→生成→修复仍未验收。** S1 在线开放项保留；S3/S4 未开始。未改规范 FB_MainSequence、原输送带控制源码或现场配置，不授予 TIA / PLCSIM / 实机 / 安全验收。

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

- S1：真实 mcode/CM 的当前源码生成、检查、修复在线回合及在线取消链路。
- S2：沿用现有 mcode/CM 补一次真实在线规格→IR→双输出→实际检查，以及真实诊断驱动的修复/取消记录；不得用夹具关闭。
- S3：按原合同增加输送带有限状态与扫描计数，完成两种产物行为对照。
- S4：有明确需求和环境后，单独验证最薄 TIA 适配；不是前三项的默认依赖。

## Next

本轮止于用户授权的 S2 确定性闭环，继续保留 S1/S2 在线验收开放项。取得现有 mcode/CM 运行环境后，使用同一个启停基准完成真实生成、失败诊断、修复与取消验收，再决定是否开展 S3；不要安装替代编排平台或扩大指令集。基准通过只覆盖明示合同，不替真实设备决定工艺或功能安全策略。
