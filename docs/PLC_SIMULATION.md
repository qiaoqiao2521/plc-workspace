# 可组装 PLC 仿真

仿真是需求到工程工作台的一个验证入口。人通过三维设备、端口和逐扫描轨迹观察动作，Agent 通过同一 HTTP / CLI 组装场景、运行候选、注入故障和读取反例。每次运行绑定具体源码与具体场景，既有工程中的历史“通过”记录不授予本次验收。

## 启动与页面

Node 24、Python 3.10+、GCC 和已安装的 matiec 是原生执行依赖。与现有生成检查使用同一工具链：

```sh
npm --prefix web ci
npm --prefix web run build
SIM_IEC2C=/absolute/path/to/matiec/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
npm --prefix web run dev
```

打开 `http://127.0.0.1:8766/simulator.html`，或从工作台“仿真验证”进入。生成结果也可通过“在仿真中验证”交接原始 request/result。手机宽度下入口仍可见。运行目录在仓库外；无需配置模型 API Key 即可使用仿真。

页面提供组件目录、添加/删除、参数与位置编辑、类型化接线、PLC 输入/输出绑定、场景导入/导出、三维观察、单步/连续播放、设备故障、固定用例与失败定位。设备颜色、动作、端口状态和轨迹来自同份服务快照；调整镜头和刷新绘制不执行 PLC。更改场景会使旧实例失效，需重新创建，避免将旧证据套到新接线。

静态部署可展示编辑界面，但没有 `/api` 时不能执行原生 PLC。旧 `simulation.html` / 8767 服务保留为历史八拍候选的专用演示；本次统一入口为 `simulator.html` / 8766，不复用旧候选冒充当前工程。

## 支持合同与设备

| Profile | 源码与合同范围 | 固定用例 |
|---|---|---|
| `conveyor-pusher-v1` | 新的合成输送、伸缸、缩缸单元；每阶段第十二次等待超时 | normal、jam、sensor-failed、stop-restart、fault-reset |
| `conveyor-12-v1` | 工作台现有十二次等待输送合同 | 同上 |
| `conveyor-8-demo-v1` | 明确标识的历史八次等待候选 | 同上 |
| `latch-start-stop-v1` | 现有 BOOL 启停基准，Motor 输出 | normal、stop-restart |

生成器目前可交接已明确选择的 `conveyor-12-v1` 或 `latch-start-stop-v1` 工程。新推料模板是独立合成场景，不表示生成器已经支持任意工艺、多文件调用或 S3/S4 指令。详细示例合同在 [`web/data/simulation/contract.md`](../web/data/simulation/contract.md)。

原子组件为 switch、lamp、motor、conveyor、photoeye、cylinder、workpiece。目录返回其 BOOL/REAL 输入输出、参数范围和可注入故障。最多 64 个组件；组件输入只能有一个写入者，连接必须类型兼容，设备计算图禁止循环。一个 PLC 输出可驱动多个已声明输入，支持添加指示灯等组合。不能仅移动模型就暗中创建电气连接。

合成设备的速度单位为归一化行程/扫描；位置参数用于视觉布局，运动/感知由显式连线决定。一拍严格按“采样反馈 → 执行持久 FB 一次 → 发布输出 → 推进设备”进行。设备在本拍末到位，要到下一拍才成为 PLC 输入。播放间隔只影响观看速度，不赋予真实时间语义；TON/TOF/TP、厂商运行时、多任务、掉电保持不在该执行范围。

## Agent 操作

加载仓库的 [`plc-workspace-control`](../.agents/skills/plc-workspace-control/SKILL.md) 项目技能。以下命令从仓库根执行，地址选项放在 `simulate` 之前：

```sh
python3 web/scripts/plc-agent.py doctor
python3 web/scripts/plc-agent.py simulate catalog
python3 web/scripts/plc-agent.py simulate templates --output /tmp/plc-templates.json
python3 web/scripts/plc-agent.py simulate create --input /tmp/plc-create.json
```

`/tmp/plc-create.json` 可只指定 `{"template":"conveyor-pusher-v1"}`，也可提交 `{program,scene}`。templates 的输出内每个条目已含可复制编辑的 program 和 scene。不要将包含 label/cases 的整个模板对象当成 create 请求。

创建返回 `session` 后，可以执行：

```sh
python3 web/scripts/plc-agent.py simulate step --session SESSION_ID --input /tmp/plc-inputs.json
python3 web/scripts/plc-agent.py simulate run_case --session SESSION_ID --input /tmp/plc-case.json --output /tmp/plc-case-result.json
python3 web/scripts/plc-agent.py simulate export_trace --session SESSION_ID --output /tmp/plc-trace.json
python3 web/scripts/plc-agent.py simulate close --session SESSION_ID
```

inputs 文件形如 `{"inputs":{"Enable":true,"Start":true,"Stop":false},"count":1}`；case 文件形如 `{"case":"normal"}`。输入电平保持，Start 脉冲需随后设 false。单次 count 为 1–500。最多同时八个实例，各自拥有独立持久 FB 和设备状态；轨迹上限 2000 拍，达到上限须导出并新建实例。

不带 `--output` 时 stdout 是 `{"type":"simulation","action":"...","result":{...}}`；带 `--output` 时文件中直接是完整 result，stdout 为摘要。无裁决的成功查询/创建返回 0，测试 fail 返回 1，unknown/not_run 返回 2。`export_trace` 成功交付文件返回 0，但交互轨迹内仍为 not_run（异常终止为 unknown），因为观察本身没有独立测试裁决。

## 统一 HTTP 动作

GET 支持 `/api/sim/catalog`、`templates`、`integrations`。其余使用 `POST /api/sim/<action>`，JSON 对象并带 `X-PLC-Workspace: 1`；服务只监听 loopback，跨来源写入被拒绝。CLI 自动处理这些协议字段。

| 动作 | 输入 | 主要输出 |
|---|---|---|
| `catalog` / `templates` | `{}` | 组件、支持合同、模板、工具能力 |
| `create` | template、scene、program，或 engineering | session、snapshot、源码和场景哈希 |
| `inspect` | session | 当前快照、可用用例、轨迹长度 |
| `step` | session、inputs、可选 count | 执行后的快照与批次轨迹 |
| `inject_fault` | session、device、fault、active | 故障后的设备快照 |
| `run_case` | session 与 case；或创建配置与 case | 独立测试的状态、checks、first_failure、完整 trace |
| `export_trace` | session | 冻结源码、场景、哈希、轨迹及观察范围 |
| `close` | session | 实例清理结果 |
| `integrations` | `{}` | OIP 固定版本和安装/工具状态 |
| `oip_catalog` | 可选 parts 数组 | 上游真实原子组件目录 |
| `oip_assemble` | `{}` | 使用上游脚本组装并验证的输送场景，project_id |
| `oip_test` | 可选 program 或 engineering、project_id | 当前 native PLC 驱动 OIP 设备的独立报告 |
| `oip_self_test` | `{}` | 上游自己的 IEC 子集示例测试，独立范围 |

`run_case` 用现有 session 时，复制其冻结源码与场景另建实例，结束自动清理，不改动观察会话。首反例在 `first_failure`，含 scan、断言名、expected、actual 和当拍 snapshot。错误、缺工具、崩溃或扫描超时没有通过裁决；被终止实例仍可导出已有轨迹。

## 场景与源码身份

场景 schema 为 `plc-scene.v1`。组件包含 id、type、position、parameters；connections 使用 `component.port` 引用；bindings.inputs 将 PLC 输入绑定到设备输出，bindings.outputs 将 PLC 输出绑定到设备输入列表。完整例子见 [`conveyor-pusher.scene.json`](../web/data/simulation/conveyor-pusher.scene.json)。

例如在模板上增添一只灯：

```json
{"id":"extra_lamp","type":"lamp","position":[2.6,0,2.0],"parameters":{}}
```

将它加入 components，同时把 `extra_lamp.value` 加入 `bindings.outputs.Motor` 的列表。这样会改变 scene_sha256，不改变 source_sha256。未连接的灯输入会被校验拒绝。

自带程序为 `{"profile":"conveyor-12-v1","source":"完整SCL文本","filename":"FB_ConveyorPack.scl"}`。源文件必须恰好一个、接口与选定 profile 一致；服务复用现有 SCL 适配和 matiec/GCC 编译，实际运行原生 FB，不以 Python 或浏览器逻辑代替源码。

完整工程用 `{"engineering":{"kind":"...","request":{...},"result":{...}}}` 交接。服务重新校验 request/result 的身份、未决问题与单源文件，忽略历史 verification/acceptance。源码、规范化场景和独立合同分别有 SHA-256，报告保留原始 request_id / request_fingerprint。伪装成十二拍合同的旧八拍源仍执行自己的八拍逻辑，测试会报告真实提前超时。

原生代码在独立子进程执行，默认单拍 watchdog 为 2 秒、整批 step 为 30 秒；每拍取单拍上限与整批剩余时间中较小的预算。超时保留已完成轨迹并停止该实例，其他会话仍可使用；编译也有有限超时。支持范围预检查拒绝 native pragma 和厂商扩展。这是有限源码执行隔离，不构成面向不可信互联网任意代码的多租户沙箱。

## Open Industry Project

可选安装固定上游：

```sh
python3 integrations/open-industry-project/setup.py
python3 web/scripts/plc-agent.py simulate integrations
python3 web/scripts/plc-agent.py simulate oip_assemble --output /tmp/oip-project.json
```

默认安装到仓库外缓存，也可用 `PLC_OIP_DIR` 指定固定版本 checkout。索引记录 commit、许可证和关键文件哈希；`doctor` 校验版本、被跟踪文件与依赖入口。无需把整个第三方工程复制到本仓库。源索引、安装、许可和直接运行命令见 [适配器说明](../integrations/open-industry-project/README.md)。

桥将同份捕获的 conveyor SCL 交给本仓库 native worker，把 Motor 写入 OIP 的真实输送组件，用 Jolt 步进后的光电反馈作为下一次 PLC 输入。Jolt 按 60 Hz 推进，每次控制采样推进 15 步即 250 ms；PLC 超时仍按 FB 调用计数。没有并行运行另一套 OIP PLC 来替代待验证源码。当前只支持两种 conveyor profile，推料气缸与任意设备世界映射需另增适配。

`oip_test` 不提供 program/engineering 时只验证明确标记的历史八拍源；测试当前工程务必显式传入当前对象。`oip_self_test` 测的是上游自己的示例和 IEC 子集，不能证明本工程正确。上游退出 0 但没有用例或没有断言时，本桥报告 not_run；负控应在独立副本上故意取消 Done，并验证相同断言能检出，原源码不改动。

## 复验与结论范围

```sh
SIM_IEC2C=/absolute/path/to/matiec/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
npm --prefix web test
npm --prefix web run build
python3 validation/scripts/sync-semantics.py --project projects/FB_MainSequence --check
```

OIP 真实闭环为可选较大依赖，单独执行适配器的 native-test 和 upstream-tests；小型报告策略回归不需要安装全部上游。实际本次子代理操作、浏览器、负控及回归证据记录在 [本次进度](../plans/plc-composable-simulation/progress.md)。

通过只说明该源码、场景和有限用例下满足断言。报告只授予 simulation_case，不恢复生成验收，也不授予 LAD 执行、TIA、PLCSIM、机械精度、安全或实机验收。规范 FB_MainSequence 及其历史形式证据与这些新示例分别维护。
