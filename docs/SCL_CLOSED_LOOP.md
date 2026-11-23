# 当前 LAD / SCL 的检查与修复

直接模型 API 和外部 Agent 共用的控制器现在把专业资料、原程序、生成结果和工具反馈接到同一次任务。规格审阅仍先于生成；没有新增审阅角色。模型不直接操作工程工具，由控制器捕获当前源码并运行检查。

## 运行

启动工作台后在页面配置 API，或选择外部 Agent 接管。真实检查另外需要 matiec 编译器与标准库：

```sh
npm --prefix web ci
npm --prefix web run build
SIM_IEC2C=/absolute/path/to/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
npm --prefix web run dev -- --runtime-root /outside/repo/runtime
```

`iec2c` 和 GCC 必须在运行桥接的 Linux 环境可执行；标准库目录应含 `ieclib.txt` 与 `C/`。本次验证使用 [beremiz/matiec](https://github.com/beremiz/matiec) commit `3a41303bcb4e50403417bc39c63f88981d7d961e`。构建 matiec 需要 C/C++ 编译器、make、autoconf、automake、bison、flex 和 m4；在仓库外检出该版本后运行 `autoreconf -i`、`./configure`、`make`。第三方工具不加入本项目 Git。

打开工作台，点击 **输送带 12 次等待验收**。它载入原来的八次等待程序，明确本次修改要求，选择固定的 `conveyor-12-v1` 检查合同。可在“本次修改的原程序”中审阅源码，再整理任务并生成。普通任务默认只运行支持范围内的 Linux 编译，不自动继承输送带行为测试。

## 每次任务做什么

1. 控制器读取三个项目 Skill 入口、相关规则/模板和官方依据记录，将正文及 SHA-256 放进模型输入，运行目录保存实际加载版本。原程序 `brief.source_files` 和用户选择的检查方案 `brief.validation_profile` 都计入需求指纹。
2. 规格通过后，模型交付新的完整 SCL。检查器捕获这份文件的 UTF-8 字节，记录文件哈希，做有限的 Siemens 声明语法适配，然后调用真实 matiec。
3. 选择输送带合同时，在有时限的独立进程中编译为本机程序，执行固定输入与预期。生成器和修复器不能改测试。启动调用不计等待，第 1～11 次不能超时，第 12 次才到期；到位优先；Stop 撤动作且保持 Start 不重启，释放后新的上升沿允许启动；Done 为单拍。测试不依赖原程序的私有状态变量名。
4. 编译或行为失败，把原始诊断/逐拍反例送回同一工程角色，只允许返回修正后的源码。默认最多修复两次，每次重新检查；通过后才对这份新代码进行现有并行审阅及监督裁决。有需求依据的审阅失败也可进入修复、重验和重新审阅。任何 fail/unknown 不能被监督者直接改成通过。
5. 最终文件、每轮检查、修改差异和知识来源在工作台可复核并导出。失败或工具不可用也保留当前候选；它不具有“已通过”状态。

## 文件和边界

### S1：分项证据与当前目标

新检查报告使用 `schema_version=2`，保留各项 `pass/fail/unknown/not_run`，并明确 `target`、`required_checks`、每项的对象和必选性。模型结果的传输 Schema 仍为 v1；模型不能填写或修改权威检查报告。

| 检查 | 无行为合同：`scl_compile` | 选择输送带合同：`scl_behavior` |
|---|---|---|
| `source_structure`：文件名、内容类型、唯一性和大小；不包含 PLC 逻辑正确性 | 必选 | 必选 |
| `linux_compile`：当前文件的真实 matiec 编译 | 必选 | 必选 |
| `scan_contract`：当前文件对固定合同的逐扫描行为 | 未运行，不授予行为验收 | 必选 |
| `lad_scl_compare`：LAD/SCL 产物对照 | 未接入，未运行 | 未接入，未运行 |
| `tia_compile`：目标 TIA 编译 | 未接入，未运行 | 未接入，未运行 |

总 `status=pass` **仅表示选定目标的必选检查通过**。编译任务在页面显示“编译通过，行为未验收”，不获得 `scl_behavior`。`reviewed_draft` 兼容保留，表示选定工具目标与文本审阅通过，不代表任意逻辑或 Siemens 验收。工作流的 `acceptance` 分别列出编译、受限行为、双输出对照和 TIA；未批准、失败、未知或取消时不授予当前验收。

共享的 `verification-policy.py` 从请求确定必选项；工作流和本机桥接都重新计算这些条件，不信任报告自称的总 pass、模型声明或临时豁免。必选项缺失、重复、fail、unknown、not_run、目标不匹配都会阻断对应验收。没有行为合同不会靠反复修源码补出测试；可选 TIA 未运行也不阻断独立的离线目标。

取消、工具缺失、超时和工作进程退出保留各自原因。取消会回收验证进程组；已经完成的编译证据可保留，但不能替被中断的任务授予验收。桥接用 `finished` 区分取消请求与清理完成；页面等候清理后接收保留的候选和记录。当前文件还与需求指纹关联；即使代码字节相同，改了需求也不能复用旧报告。

旧版报告仍可导入、查看和导出。导入不认证来源、不恢复当前会话验收，也不会把旧总 pass 补成新等级。当前控制器不接受旧版或不完整报告作为新任务门禁。

运行目录按任务保存 `request.json`、`knowledge.json`、`outcome.json`、`stages/` 内的阶段包与回答以及 `attempt-N/`。每轮包含 `candidate.json`、`changes.diff`、`validation.json`、检查器捕获的 `sources/`、编译日志和扫描记录；完成审阅/修复时还保存对应结果。运行证据不写回规范 PLC 源码，也不自动提交 Git。

**导出工程草稿**包含需求、最终或未通过的候选、检查报告和循环记录。**打开工程草稿**重新计算需求指纹和每份源码 SHA-256；不匹配时拒绝旧记录。匹配只说明记录与文件相连，不能认证外部文件的来源；导入明确显示“本次未重跑”。以当前代码继续修改会准备新任务，旧结果过期。

工具缺失、适配不支持、本机运行超时或崩溃属于 unknown，不能伪报源码正确或错误。Linux 适配支持有限的 FB/ST 语法，通用编译通过也不说明行为已检查。普通任务的 LAD 仍是审阅网络；S2 合成基准见下节。TIA 编译、PLCSIM、形式验证、实机及安全验收均未接入本循环。本次没有下载程序或连接现场 PLC。

## S1 兼容结果字段

| 结果 | 本次必须具备的证据 | 范围 |
|---|---|---|
| `compile_only` | 来源捕获和 Linux ST 编译通过；未选独立行为合同，扫描明确为 `not_run` | 可审阅草稿，总状态不冒称行为通过 |
| `behavior_pass` | 本次需求、每份源码、冻结 `conveyor-12-v1` 合同均匹配，且编译及扫描均通过 | 只证明该 Linux 合同的固定扫描用例；`reviewed_draft` 仍是草稿 |
| `not_accepted` | 缺失、冲突、过期、取消或工具失败 | 可保留诊断和候选，不接受历史记录或审阅意见替代检查 |

`validation_level` 仅是共享策略重算结果的兼容标签，不是另一套门禁。控制器冻结必选检查，工作流与本机桥接独立用同一判定核对报告。需要同时匹配需求指纹与源码指纹：即使文件字节未变，旧需求的报告也不能放行新任务。取消时保留已完成的编译观察，不提升验收等级；页面区分已请求取消与本地清理完成。本机 API / Agent 取消及工具清理由协议测试覆盖；不承诺停止服务商的远端计算或计费。LAD/SCL 对照、TIA、PLCSIM 和现场检查均不在 S1 范围内。

本次合流复验、原始分支的已复现缺陷及未验收范围见 [S1 进度记录](../plans/plc-logic-harness-v1/progress.md)。

## S2：启停自锁双输出

点击 **启停自锁双输出基准**，显式载入 `latch-start-stop-v1`。这是独立的合成合同：输入 Enable/Start/Stop，输出 Motor，初始静止、Start 前值为 FALSE；每拍调用同一实例，包括失能期间。有效新 Start 边沿启动并自锁；Stop 或失能当拍清除运行；被抑制的 Start 边沿也消费，保持 Start 穿过停止/失能不能重启。首次调用 Start 为 TRUE 按新边沿处理，只是本基准的约定。普通停止不是安全功能。

合同文字、接口、约束和空状态草稿固定，不能把该基准勾选到另一台设备的自由文本上。需要另一种工艺时回到普通 SCL 草稿路径。本次没有增加 Reset、计时器、扫描计数、掉电保持或物理 I/O。

模型只交付 `logic_ir` 提议，控制器检查版本、BOOL 类型、声明、初值、单写、临时变量先写后读与执行顺序。表达式只包含常开/常闭触点、串联、并联；不允许把任意代码藏在字符串里。SCL 和 LAD 由程序确定性生成。LAD 是同一块控制逻辑的另一种表达，含真实触点、分支、线圈与连线，没有用调用 SCL FB 的外壳代替逻辑。

| 检查 | S2 证据与范围 |
|---|---|
| `source_structure` | IR 子集、符号、单写、图拓扑、两个产物与 IR 对应；不证明行为 |
| `linux_compile` | 当前生成 SCL 经有限声明适配后真实 matiec 编译 |
| `scan_contract` | 编译后的持久实例对独立预期：14 个手写场景 / 64 次调用，加全部 4,096 条四拍输入序列 / 16,384 次调用 |
| `lad_scl_compare` | 读取实际序列化图执行，与同样独立预期核对，再与原生 SCL 逐拍对照；不能只凭双方一致通过 |
| `tia_compile` | `not_run`，未接入 TIA；不阻塞上述离线目标 |

五个共同错误变体（并联改串联、反转 Stop、漏停止、Start 电平误重启、提前更新边沿记忆）即使两种输出相互一致，也会被预期拒绝；重复写入在结构阶段拒绝。这些是具体反例，不是通用 AI 准确率。每条执行路径共 16,448 次调用，只证明这些有限输入和观察；不声称无界等价或现场正确性。

S2 的修复返回值只能是 IR 与说明。控制器重生两个出口、重跑原合同，默认最多两轮。必选工具结果 unknown 时停止自动修复，保留原因。报告同时绑定需求、源码、IR 和 LAD；修改任一产物或需求，旧证据不能沿用。`lad_scl_pass` 只是该受限目标与文本审阅通过后的标签，TIA 仍未验收。结构坏 IR 可保留为没有 SCL/LAD 的诊断草稿，不能获得验收。

### 离线复验与静态交接

```sh
# 确定性手写基准：没有模型调用
SIM_IEC2C=/absolute/path/to/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
python3 web/scripts/check-latch.py --example --output /outside/repo/fresh-latch-run

# 静态页面导出 task.json；模型只回同一请求的 proposal.json
SIM_IEC2C=/absolute/path/to/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
python3 web/scripts/check-latch.py --request task.json --proposal proposal.json \
  --output /outside/repo/fresh-proposal-run
```

`proposal.json` 包含 `schema_version=1`、原 `request_id` / `request_fingerprint`、`summary`、`questions` 与 `logic_ir`。未决问题、身份不符或额外字段均拒绝。该工具不替代在线规格/文本审阅；输出 `engineering.json` 用“打开工程草稿”重开，按历史记录展示。运行目录保留原 IR、真实图、源码、编译日志、`latch-traces.jsonl` 完整观察、命名场景与首个反例摘要，不把大量枚举轨迹塞进模型输入。

本次完成确定性闭环和显式模型夹具回归；另有一次实际 Agent 按仓库 Skill/CLI 完成规格→IR→双输出→实际检查→交付，首轮通过、修复 0 次。远端模型 API 与实际 Agent 诊断修复尚未验收，本机协议夹具不替代它们。S3 的状态/计数及第二个双输出示例没有展开。可选 TIA 后置。

## 回归

```sh
SIM_IEC2C=/absolute/path/to/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
npm --prefix web test
```

原生回归明确检查：旧八次程序编译通过但违反十二次合同；十二次候选通过固定扫描；故意的 BOOL 类型错误由真实编译器拒绝；修复回调交付新源码后重新编译和扫描通过。测试中的模型应答是显式夹具，不能当作真实模型 API / Agent 验收。未配置编译器的测试会明确跳过原生部分。
