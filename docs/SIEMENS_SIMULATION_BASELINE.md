# 西门子官方仿真实现与仓库补充基线

研究日期：2026-11-26。对照实现：master@5693589844173aab6f075402242aff533a401863。

本文件把官方已公开的实现、产品与版本约束、本仓库的现状、后续设计建议分别记录。资料索引见 [siemens-reference-index.json](../web/data/simulation/siemens-reference-index.json)，当前可执行入口见 [PLC_SIMULATION.md](PLC_SIMULATION.md)，已执行的 native / OIP 验收见 [原始接入记录](../plans/plc-composable-simulation/progress.md)。

**结论：PLC 执行、设备行为、机械运动、交互显示、自动化判定应该有明确边界，并通过同一组信号与时钟闭环。** 西门子的 C# 输送带和 Pick and Place 案例给出了可核对的工程参照；本仓库适合保留现有云端快速验证，再增加可选、版本固定的 Siemens 工程验证通道。[S01][S02][S03]

本次交付为官方资料研究、能力对照和设计补充。Siemens 软件、官方下载工程包、Windows worker、AX 工具链和 WinCC HMI 均未在本轮安装或执行；索引不是运行时适配器。下文的“建议”“拟议”“待实现”不进入现有 supported 能力，也不改动既有 PLC 合同。

## 1. 官方产品分别解决什么问题

| 层次 | 官方实现 | 核心用途与边界 | 仓库对应位置 |
|---|---|---|---|
| PLC 调试 | S7-PLCSIM Standard | 虚拟 CPU、SIM 表、输入序列和事件；具体功能取决于实例类型。[S09][S24] | 原生 FB 的有限调用验证是另一种执行范围 |
| PLC 联合仿真 | S7-PLCSIM Advanced | C++ / C# API、实例、I/O、同步及虚拟时间。[S10][S13] | 未来可选的厂商运行时后端 |
| 设备行为 | SIMIT | 可参数化组件、驱动/传感器模型、耦合、脚本与模型生成。[S04][S06] | 当前七种原子设备及未来设备模板 |
| 机械运动 | NX Mechatronics Concept Designer；案例中的 Unity build | 接收命令、计算机械响应、回传反馈；与设备行为模型协作。[S02][S03] | 当前合成 plant、OIP/Jolt 物理世界及三维快照 |
| 应用程序测试 | Test Suite Advanced / Application Test | 安排输入、运行 CPU、独立断言；自动管理或复用实例。[S18][S19][S20] | 固定用例、首反例、源码绑定报告 |
| 通信系统测试 | Test Suite / System Test | 经 OPC UA 观察变量，受采样和发布周期影响。[S21] | 未来通信观察测试，与扫描测试分开 |
| 工程自动化 | TIA Portal Openness | 工程操作与 Test Suite 执行接口。[S22][S23] | 未来 Windows 工程 worker |
| ST 单元测试 | SIMATIC AX / AxUnit-ST | CLI、测试夹具、本地执行及 CI 集成。[S28] | 可评估的另一条单测工具链 |
| HMI 验证 | WinCC Unified + PLCSIM | 对实际 HMI 工程进行通信、变量和报警验证。[S30] | 现有三维操作面板不承担此验收 |
| 生产虚拟控制器 | SIMATIC S7-1500V | 在 Industrial Edge 上部署的控制器产品。[S31] | 不列为本仓库的仿真后端 |

这张表是职责对照，不是兼容性承诺。把同一个场景接到不同后端后，必须继续保留后端名称、指令支持、时间含义和判断范围。

## 2. 最值得研究的官方完整实现

### 2.1 C# 输送带闭环：109739660

已读 Getting Started V1.0.2，09/2025；工程基线为 TIA V20 / PLCSIM Advanced V7.0。第 44–65 页说明实例管理、符号 I/O、同步回调、输送过程和落箱故障；第 55 页的闭环顺序是读取 PLC 输出、计算 plant、回写传感器输入。[S01]

文档第 11 页列出两个不同的下载包：

| 内容 | 文档列出的文件 |
|---|---|
| TIA 工程 | 109739660_PLCSIM_ADV_ApplicationExample_v1.0.0.zip |
| Visual Studio / C# 联合仿真 | 109739660_PLCSIM_ADV_COSIM_APPL_v1_0_2.zip |

本轮仅核对文档，没有下载、审计或执行这些 ZIP。第 58 页仍引用较早的 co-sim v1.0.0 包名，个别页脚也保留旧版本；文档版本、文档列举的包名和实际下载包需分别核验。直链曾返回 404，检索入口优先使用稳定 Entry 链接。[S01]

对仓库的启发：将实例和符号管理放在后端，将设备行为放在 plant，将场景、时钟、期望和报告作为独立输入。示例是接口使用材料；适配器仍需自行处理异常、失联和取消，不能把示例中省略的错误处理当作可交付实现。官方案例中的毫秒定时也不能覆盖我们已冻结的 8/12 次 FB 调用合同。

示例开启的是默认模式周期事件，收到回调不意味着 PLC 已冻结等待 plant；确定性锁步需要依据同步 API 另外配置和验证。[S01][S13] 示例中按名称连接实例和人工下载工程的步骤，也不证明无人值守编译下载已经完成。后端必须验证实际加载产物、初始状态及实例所有权。

### 2.2 三维整机闭环：109758943

已读 Pick and Place V1.0.3，01/2026。该版本组合为 SIMIT 11.3 SP1、PLCSIM Advanced 7.0 Upd1、NX MCD 2412、TIA / WinCC V20 Upd4，另提供 Unity build 路线。文档列有 TIA、SIMIT、MCD 和三维模型附件；“Unity build”不能据此推定为可再分发的 Unity 工程源码。[S02]

官方分工可概括为以下闭环，图中没有加入本仓库的新 API：

~~~mermaid
flowchart TD
  T["TIA 工程"] --> P["PLCSIM Advanced"]
  H["WinCC HMI"] <--> P
  P <-->|命令与反馈| S["SIMIT 设备行为"]
  S <-->|速度与位置| M["MCD 或 Unity 运动模型"]
~~~

它对当前设计最直接的提醒是，位置、速度、单位和耦合周期需要明确归属。案例第 32 页说明，在 MCD / Unity 负责位置计算时可删除 SMG 生成的速度积分器；第 38 页则给出关闭光栅的故障试验。[S02]

由此推导的仓库规则是：每个运动自由度只由一个模型推进；3D 渲染消费已计算的状态。设备故障应作用于模型或反馈，最终由独立断言判断 PLC 的反应。

### 2.3 组件、自动组装与 CI 的配套材料

[S05] 的 TankX / CTE 示例用参数、状态、端口、人工覆盖和动态显示说明如何定义设备类型，适合作为未来组件规格的参照。

[S03] 的虚拟调试指南说明 HWCN 导出、Openness、SMG、XLSX 和匹配模板之间的关系。对本仓库而言，AI 可以从明确符号和已知模板提出组装候选，随后由确定性的类型检查与绑定检查冻结场景；缺失的地址、单位或设备语义应保持未决。

[S26] 的 Jenkins 示例采用 CI 主机与 Windows automation desktop 分工；[S27] 另有 Test Suite Code Coverage 的 Add-In / CLI。覆盖率示例的实测软件是 2024 文档中的 Windows 10 / TIA 17、18，不能将其二进制直接标为 V21 兼容；工程转换应在可丢弃副本评估。

## 3. 版本与能力矩阵

这里记录的是实际查到的版本，不宣称它们都是各产品最新版本。旧案例用于理解架构，目标平台支持以选定产品的对应手册和 Readme 为准。

| 已核对资料 | 明确结论 | 接入时要固定的内容 |
|---|---|---|
| Advanced V8.0 产品页与 V21 CPU 表 | 已加入表列的 S7-1200 G2；Unsupported 段仍写 S7-1200 和 CPU 151xV(F)。原文代际措辞需结合支持表理解。[S07][S08] | 家族、代际、订货号、固件、运行时与更新号；不使用笼统的“支持 1200” |
| Advanced V8.0 API 手册 | V8 API 接口与旧 API 不兼容，但 V8 Runtime Manager 可兼容旧 API。[S10] | runtime_version 与 api_version 分别记录 |
| Advanced 产品与安装说明 | 技术上限 16 实例；产品页的单浮动许可证为同时启动 2 实例。OS / 虚拟化支持依赖对应 STEP 7 版本，排除 Windows Home。[S07][S11] | 实际授权、OS、资源、实例数；上限不等于授权数 |
| Test Suite V21 Update 1 | 要求 STEP 7 Professional V21；SystemManaged 使用 Advanced V8，ExternallyManaged 最低 V4。[S17] | 外管最低版本不保证支持新 CPU |
| 同上，Application Test | 排除 G2 订货号 6ES72161ML500XB0、6ES72171MM500XB0。[S17] | 此项只写入 Test Suite 能力，不扩大为整个 Advanced 的限制 |
| Test Suite V20 执行文档 | SystemManaged 无需单独 Advanced 许可证；ExternallyManaged 要相应有效许可证。[S18][S19] | 此许可结论保留 V20 标签；V21 部署时复核其许可文件 |
| Openness V21 迁移文档 | 仅 .NET Framework 4.8；旧应用需重编译，程序集拆分，Copy Local=False。[S23] | 版本专用 Windows worker、安装的程序集；不包装成通用 Linux / .NET 8 TIA 库 |
| PLCSIM V21 普通界面 | 序列最小间隔 5 ms，Sequences 不支持 Advanced 实例。[S24] | UI 与实例运行时分别判断 |
| AX 2510 文档及 FAQ | 使用 AxUnit-ST；旧 AxUnit 支持已于 2024-05 结束。FAQ 另列 2610 迁移章节。[S28][S29] | 选择实际发行版后核对 CLI 和包迁移，不照搬旧教程 |

G2 表明确列出 1212C、1214C、1216、1217 以及 1212FC、1214FC；把排除段的 S7-1200 理解为传统代际，是结合 G2 单列结构和 V8 产品说明作出的解释，并非排除句的逐字措辞。[S07][S08] 支持 CPU 表给出的总体固件范围不是每种 CPU 任意固件都可用的保证；修改工程固件后，需要按文档重新建立相应实例。[S08] V21 比较表的 TCP/IP 脚注也区分普通 UI 与 Advanced 实例，不能因为在同一界面中创建，就认为能力相同。[S09]

本轮已在[官方产品文档目录](https://sieportal.siemens.com/en-ww/products-services/detail/6ES7823-1FE00-0YA5)查到 Advanced V8 UPD1 的记录（Entry 110002945，05/2026），但未核验该更新的 Readme 正文；本文件的 API 依据仍固定为 V8.0 手册，不推定补丁行为。

## 4. 原子设备和可组装场景

SIMIT V11.2 使用类型与实例分离，宏封装重复连接，ACI 脚本参与仿真；该版本宏不能继续嵌套宏。CONTEC 则有独立物料连接语义，针对固定路线的离散物体，忽略质量和摩擦等属性。[S04] 这些事实提示我们，需要区分电气/控制连接、物料流转和物理接触。

**以下为仓库下一阶段建议，不是现有 plc-scene.v1 的新增字段。**

| 对象 | 建议补充的规格 | 可验证的结果 |
|---|---|---|
| 组件类型 | 稳定 type_id、版本、端口类型、参数范围、状态、初始化/更新顺序、允许故障 | 同名不同语义的组件不能静默替换 |
| 组件实例 | 类型版本、具体参数、初始状态、实例身份 | 保存并重建时得到同一初始场景 |
| 设备组合 | 对外端口、内部连接、可展开子设备、版本 | 一组输送段/光电/电机可作为单元复用 |
| 单位 | SI 或明确的合成单位、缩放、偏移、极性 | mm 与 m、rpm 与角速度不会靠名称猜测 |
| 物料 | 物体身份、路线、交接、队列、阻塞、分支 | 两条输送段之间可追踪同一工件 |
| 运动状态 | position_authority、速度来源、更新周期 | 同一位置不会被 plant 与物理引擎重复积分 |
| 图形 | 网格、颜色、标注与状态映射 | 改镜头、材质、显示帧率不改变执行结果 |

现状仍为七种原子组件、BOOL/REAL 端口、参数范围、单写入者与控制 DAG。归一化行程/扫描是当前合成模型的明确范围，不能改标签就当成毫米或秒。OIP 的 Jolt 场景承担另一种已记录的物理范围，尚未与任意七组件场景形成通用映射。

多段物流的环路与分流不能直接放开控制 DAG 校验来实现。拟新增的物料图需要自己的守恒、容量、交接和死锁检查；控制信号图继续保证更新顺序明确。

## 5. PLC 信号绑定与写入权

Advanced 的符号接口可以更新和展开标签；指定不存在的 DB 过滤项不一定报错。因此“符号表更新成功”不等于“所需端口全部存在”。[S16] API 与用户程序同时写同一输出时，API 写值可能覆盖程序值。[S15]

拟议适配器应逐个检查符号名称、数据类型、地址域、方向、单位和更新时相。默认由 PLC 写执行命令、plant 写传感器反馈；输出强制应属于单独的测试动作，并记录原因、时间和撤销过程。

报告至少区分三种量：

| 量 | 含义 | 必须发现的错误 |
|---|---|---|
| plc_command | PLC 本次真实产生的命令 | 程序逻辑错误 |
| applied_command | 经接线、故障或 override 后实际施加的值 | Enable 旁路、强制输出掩盖程序 |
| actual_feedback | 设备实际运动或传感器反馈 | 电机堵转、到位延迟、传感器卡死 |

这三个字段是拟议证据契约，不是 Siemens 原生报告格式。当前错误接线测试已实际证明，单看 PLC Motor=0 不足以保证设备停止；原始反例仍保存在既有验收记录中。

## 6. 时钟、单步和生命周期

Advanced 的 freeze 与 CPU RUN/STOP 不同；cycle-controlled 同步有不同同步点，time-controlled 推进至少请求的虚拟时间后才到冻结点。[S12][S13][S14] SIMIT 的 ACI 脚本还在所属 time slice 的模型计算之前执行。[S04] 因此动作的时相必须成为契约的一部分。

拟议时钟信息包括 FB 调用序号、PLC 周期、同步模式与同步点、requested_dt、actual_dt、plant / physics tick、渲染时间，以及仅用于超时保护的墙钟。当前 native 后端只有已声明的调用计数语义；OIP 60 Hz / 15 ticks 的物理步长不会自动给 native TON 增加厂商时间语义。

| 操作 | 拟议明确定义 |
|---|---|
| pause | 冻结仿真推进以便观察，保留 CPU 模式 |
| cpu_stop | 改变虚拟 CPU 运行模式 |
| process_stop | 写入工艺 Stop 输入，按当前 PLC 合同执行 |
| clear_fault | 解除故障注入 |
| acknowledge | 向程序提交已定义的确认事件 |
| reset | 按声明策略重置程序、设备或整场景；注明范围 |
| restart | 满足合同条件后重新开始工艺 |
| replay | 展示历史轨迹，不执行程序 |
| restore_checkpoint | 未来功能，需一致恢复 PLC、设备、物料、故障和时钟状态 |

这些动作不能因为视觉效果类似就合并。既有合同中的 Reset、Stop 和边沿规则保持原义。未来实例也要记录 owner 和创建/连接方式，只释放本次拥有的资源；多客户端场景需遵守接口的生命周期约束。[S32]

## 7. AI 可调用的自动化入口

官方已提供可编程接口：Advanced API 控制实例与信号，Openness 的 TestSuiteService / TestCaseExecutor 执行测试，SIMIT ACI 控制脚本，AxUnit-ST 提供 CLI 单测。[S10][S22][S04][S28] 本轮资料没有建立“西门子官方提供了本仓库 JSON / HTTP / MCP 协议”的依据；这些协议仍由适配层实现。

建议继续使用有限、可检查的操作序列：

1. 查询实际后端能力和版本，确认所选 CPU、指令、时间模式与场景支持。
2. 读取当前工程、符号和组件类型；生成候选绑定，缺失项保持未决。
3. 冻结源码/工程产物、场景、绑定、独立预期及版本摘要。
4. 创建隔离实例，验证工程编译/下载结果、实例身份和所有绑定。
5. 按固定场景安排输入、推进、注入故障，记录实际输出和反馈。
6. 由独立判定器产生结果，保存首反例与原始日志。
7. 清理所属实例；取消或异常仍交付已完成证据。

当前 CLI 的 catalog / templates / create / step / inject_fault / run_case / export_trace / close 已承担有限 native 范围。新索引可以由 Agent 从仓库读取，构建后作为 data/simulation/siemens-reference-index.json 随静态数据交付；它不增加 simulate 子命令，也不注册 Siemens backend。

未来能力查询应返回“未安装”“版本不匹配”“缺授权”“不支持所选模型”等具体状态，不能因另一条 native 路线可运行而把 Siemens 项标为通过。

## 8. 测试层级与独立判断

Application Test 的 RUN 可以按周期或时长推进，周期模式可附加条件，条件结束也可能只是周期预算用尽；System Test 的 WAIT 则依赖 OPC UA 观察。两者后面都需要明确判断，通信采样也可能遗漏快速瞬态。[S20][S21]

| 验证层 | 适合检查 | 不能由该层单独推出 |
|---|---|---|
| 静态规则 | 命名、接口和约定。[S25] | 程序行为正确 |
| 当前 native FB 用例 | 受支持合同内的调用、边界和状态 | Siemens CPU 时间或硬件诊断等价 |
| 原子设备闭环 | 接线、反馈、故障与程序反应 | 真实机械标定 |
| OIP/Jolt | 采用 Jolt 刚体物理的固定输送仿真场景 | 任意设备、任意工艺都已适配 |
| Siemens Application Test | 选定实例上的应用程序断言 | HMI、整机机械或现场验收 |
| OPC UA / HMI 系统检查 | 通信、显示、报警和操作 | 捕获每个扫描瞬态 |
| 实机与专项验收 | 具体硬件和机械条件下的实际结果 | 其他机器、固件或修改后的工程 |

未来 Siemens 验收的最小矩阵建议如下。它描述需要执行的测试，本轮没有把这些项记为 pass。

| 用例 | 需要的证据 |
|---|---|
| 正确基线 | 相同冻结工程与独立预期全部满足 |
| 错误输出负控 | 刻意取消 Done 或制造错误输出，原断言能失败 |
| 错接线负控 | PLC 命令正确但设备仍动作，设备侧断言能失败 |
| 卡料、传感器卡死、延迟到位 | 注入记录、检测延迟、PLC 响应和首反例 |
| 工艺停止与恢复 | Stop、清故障、确认、重新启动按合同分别验证 |
| 边界时间与同时输入 | 明确比较发生在何扫描、何同步点及允许误差 |
| 编译失败、符号缺失、读写异常 | error / unknown，保留原因和已完成步骤 |
| 中止与残留实例 | 所属资源被清理，外部实例未受影响 |
| 陈旧工程或报告 | 项目/产物/预期摘要不符时拒绝当前验收 |
| 硬件诊断事件 | 仅在后端明确支持时测试；独立于 plant 的卡料故障 |

Siemens TestResults 的汇总状态、单步断言、警告和运行异常需要分别解析。[S18][S22] 本仓库建议继续采用 pass / fail / unknown / not_run 的证据规则，不能把 API 调用成功、退出码 0 或零断言当成用例通过。用于生成实现的 Agent 也不能改写冻结预期来自证成功。

## 9. 可视化应服务于诊断

以下为体验补充建议，尚未全部实现。画面可以有材质、层次、运动与镜头，同时保持数值和因果关系可读。

| 界面区域 | 建议显示 | 对验证的作用 |
|---|---|---|
| 三维设备 | 实际状态、运动方向、工件身份、故障位置 | 发现错误设备和错误物料 |
| 信号检查器 | PLC 原始命令、实际施加值、反馈、单位和来源 | 区分代码、接线和模型问题 |
| 时序轨迹 | 输入事件、状态变化、命令、反馈、断言 | 看清“哪一步先错” |
| 用例面板 | 当前合同、后端、预期、已检查数、首个失败 | 不把播放完成误认成验证通过 |
| 回放标识 | 历史证据、当前源码是否一致、实际运行时间 | 区分回看与新执行 |
| 诊断入口 | 跳转失败拍，定位设备和信号 | 将视觉异常追溯到证据 |

视觉插值可以提高流畅度，但不能写回执行状态。未知、失联和失败需要同时使用文字与形状提示，不能只依靠颜色。页面显示的“秒”或“毫米”必须来自对应模型的单位声明。

WinCC Unified 路线用于检验实际 HMI 工程；仓库里的操作按钮和三维画面属于我们自己的交互层，二者的结果分开记录。[S30]

## 10. 对仓库的补充顺序

**以下是由官方资料和现有反例推导的工程建议。** 优先级指后续接入顺序，不代表本轮已经实现。

| 顺序 | 工作 | 完成标准 |
|---|---|---|
| P0 | 后端能力、版本、单位、写入者、运动权威与时钟契约 | 不支持的组合在运行前明确拒绝，报告能追溯全部身份 |
| P0 | 冻结工程/产物与独立预期；结构化异常 | 正确基线通过，错误变体失败，错误与缺证据不获得 pass |
| P1 | 云端 Windows worker 的最小 Siemens 路径 | 固定 TIA / Test Suite / Advanced / CPU 组合，在虚拟实例上完成编译、运行、负控与清理 |
| P1 | 设备组合、类型版本与参数库；独立故障脚本 | 可保存重建、复现故障时相、定位首个反例 |
| P1 | 独立物料拓扑与可解释视觉 | 物体交接和堵料可验证，图形操作不影响程序 |
| P2 | SIMIT / MCD 或 Unity 耦合、外管实例复用、HMI、覆盖率、AX | 每种新增范围都有自身能力检查和实际证据 |

Windows worker 是拟议的云端可选执行环境，不要求接管用户电脑；现有 Linux 路径继续服务快速组装和有限扫描验证。官方 CI 的分工提供了这种部署方式的参照。[S26] 实际采用前需要可用的产品安装、许可和选定版本，还须验证所选云 VM、网络与 Windows 用户会话中的 Runtime Manager；官方示例不保证任意云服务会话可用。[S10][S11] 本轮未创建此环境。

初次 Siemens 验收建议优先使用 SystemManaged 的新建、编译、执行与清理流程；复用 ExternallyManaged 实例应在工程身份、复位策略和状态隔离已验证后再启用。[S18][S19] 按此顺序能够先建立可信证据，再优化速度和复杂场景。

状态推进必须有对应证据：资料已读 → 适配设计 → 代码实现 → 运行时执行 → 下载产物核对 → 独立断言通过。本轮只完成前两步，不能跳级。

## 11. 资料与代码复用边界

官方下载应用示例有专门使用条款，免费获取不等于开放源代码许可。[S01][S02][S05] 本轮仓库只保存官方链接、版本、原创分析与适配建议，不打包 Siemens 工程、库或运行时。Openness 程序集应按对应版本安装解析，遵守 Copy Local=False 的官方要求。[S23]

SIMIT 的编辑器、扩展库及不同运行方式涉及各自授权。[S03][S04] 索引中的 document_review 仅表示已阅读资料；not_run 明确表示没有执行。已有 native/OIP 历史报告不重写成 Siemens 报告，不给文档研究附加产品验收结论。

## 12. 官方来源索引

所有来源均为 Siemens 官方站点；页码指文档印刷页。机器索引为同一组来源保留 URL、版本、定位与设计缺口，便于后续 Agent 复核。

| ID | 资料与版本 | 重点定位 |
|---|---|---|
| [S01] | 109739660，Getting Started V1.0.2，09/2025 | pp11–12、43–65，C# 闭环、下载包、故障 |
| [S02] | 109758943，Pick and Place V1.0.3，01/2026 | p2、pp7–12、27–32、38，条款与完整三维闭环 |
| [S03] | 109963864，虚拟调试指南 V1.0，04/2024 | pp4–5、9–10、13–19，分层、SMG、同步 |
| [S04] | 109963664，SIMIT V11.2，04/2024 | pp277–278、347、379、885–887，宏、ACI、类型、CONTEC |
| [S05] | 109771508，CTE 组件示例 V2.0，05/2024 | p2、pp6–9，条款与 TankX |
| [S06] | SIMIT 官方产品目录，检索于 2026-11-26 | 组件、库、耦合、脚本 |
| [S07] | Advanced V8.0 产品页，检索于 2026-11-26 | 兼容范围、实例与授权 |
| [S08] | V21 手册，Supported CPUs | CPU 表、脚注及排除项 |
| [S09] | V21 手册，S7-PLCSIM products | 功能对照及 TCP/IP 脚注 |
| [S10] | 109997789，Advanced API V8.0，11/2025 | pp39–43、117–118，版本与 I/O |
| [S11] | 109997788，Advanced Function Manual V8.0，11/2025 | §4.1.1 p32，平台条件 |
| [S12] | V21 Advanced API，Stop simulation | freeze 与 CPU 模式 |
| [S13] | V21 Advanced API，Cycle-controlled sync | 同步点、实际时间差 |
| [S14] | V21 Advanced API，Time-controlled sync | 请求时长与实际推进 |
| [S15] | V21 Advanced API，Synchronizing inputs and outputs | 写入优先级 |
| [S16] | V21 Advanced API，Tag list | UpdateTagList、数组与 DB 过滤 |
| [S17] | 109990057，Test Suite V21 Update 1 Readme | pp4–6、8，版本和 CPU 限制 |
| [S18] | V20 Test Suite，SystemManaged | 生命周期、许可、Inconclusive |
| [S19] | V20 Test Suite，ExternallyManaged | 实例复用、PLC_MEMORY_RESET |
| [S20] | V20 Application Test，Basic Instructions | RUN / 条件 / ASSERT |
| [S21] | V20 System Test，Basic Instructions | WAIT、OPC UA 观察时序 |
| [S22] | V20 Test Suite Openness，Execution of Test Cases | TestCaseExecutor、TestResults |
| [S23] | V21 Openness 迁移，03/2026 | net48、程序集、版本迁移 |
| [S24] | 109997161，PLCSIM V21，11/2025 | §5.3、§6.2–6.4，SIM 表、序列、事件 |
| [S25] | V20 Test Suite，Style guide | 规则检查的范围 |
| [S26] | 109801203，Jenkins V1.3，03/2023 | pp4–5，CI 与 Windows worker |
| [S27] | 109801203，Code Coverage V1.0，01/2024 | pp4–9，CLI、版本与工程副本 |
| [S28] | AX 2510，AxUnit-ST，07/2026 | 单元测试、CLI、IDE、CI |
| [S29] | AX 2510 FAQ，08/2026 | 旧 AxUnit 停止支持；2610 迁移目录 |
| [S30] | V21 WinCC Unified，03/2026 | Using PLCSIM |
| [S31] | S7-1500V 官方产品页 | Industrial Edge 生产控制器 |
| [S32] | V21 Advanced API，Interfaces for IInstances | PowerOn、接口释放、多客户端 |

[S01]: https://support.industry.siemens.com/cs/ww/en/view/109739660
[S02]: https://cache.industry.siemens.com/dl/files/943/109758943/att_1354039/v3/PickAndPlace_V1_0_3_GettingStarted_Manual_en.pdf
[S03]: https://cache.industry.siemens.com/dl/files/864/109963864/att_1277519/v1/Guideline_VC_SIMIT_PSA_MCD_V1.0.0.pdf
[S04]: https://cache.industry.siemens.com/dl/files/664/109963664/att_1277056/v1/SIMIT_enUS_en-US.pdf
[S05]: https://cache.industry.siemens.com/dl/files/508/109771508/att_1285865/v2/109771508_SIMIT_Components_with_CTE_DOC_V2_0_en.pdf
[S06]: https://sieportal.siemens.com/en-ww/products-services/10357135?tree=CatalogTree
[S07]: https://sieportal.siemens.com/en-us/products-services/10317038
[S08]: https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced/product-overview/supported-cpus
[S09]: https://docs.tia.siemens.cloud/r/simatic_et_200sp_manual_collection_zhcn_21/general-information/cpu-function-manuals/s7-plcsim-advanced/product-overview/s7-plcsim-products?contentId=NamPuBFydrH2z_BAV~vXWg
[S10]: https://support.industry.siemens.com/cs/attachments/109997789/s7-plcsim_advanced_function_manual_API_en-US_en-US.pdf
[S11]: https://support.industry.siemens.com/cs/attachments/109997788/s7-plcsim_advanced_function_manual_en-US_en-US.pdf
[S12]: https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced-api/iinstance/stop-simulation?contentId=xpY4DD5CEPbD36bvuDLXOQ
[S13]: https://docs.tia.siemens.cloud/r/simatic_et_200sp_manual_collection_zhcn_21/general-information/cpu-function-manuals/s7-plcsim-advanced-api/iinstance/events-for-iinstances/events-for-operating-state-and-cycle-control/synchronize-simulation-partner/synchronize-simulation-partner-cycle-controlled?contentId=vIvcHhua~M39XtavkHKinQ
[S14]: https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_frfr_21/comprehensive-information/cpu-function-manuals/s7-plcsim-advanced-api/iinstance/events-for-iinstances/events-for-operating-state-and-cycle-control/synchronize-simulation-partner/synchronize-simulation-partner-time-controlled?contentId=goECKFIw~_iZApUrNr~~sg
[S15]: https://docs.tia.siemens.cloud/r/simatic_et_200sp_manual_collection_frfr_21/general-information/cpu-function-manuals/s7-plcsim-advanced-api/iinstance/i/o-access/synchronizing-inputs-and-outputs?contentId=Rbys2VgIq~5zXpUSCmQ9Iw
[S16]: https://docs.tia.siemens.cloud/r/simatic_et_200sp_manual_collection_zhcn_21/general-information/cpu-function-manuals/s7-plcsim-advanced-api/iinstance/tag-list?contentId=hBsc7gQy68qzU64ITWQ0Aw
[S17]: https://cache.industry.siemens.com/dl/files/057/109990057/att_1356678/v1/Readme_TestSuite_V21_Update_1.pdf
[S18]: https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-test-suite/application-test/test-case-execution/systemmanagedplcsim-instance
[S19]: https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-test-suite/application-test/test-case-execution/externallymanagedplcsim-instance
[S20]: https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-test-suite/application-test/basic-instructions?contentId=eYc1EyBT3O0usVoTt~UvWw
[S21]: https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-test-suite/system-test/basic-instructions?contentId=uesqwYZKhe2bluStE0CNQQ
[S22]: https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-test-suite/openness-support/functions-for-application-test/execution-of-test-cases
[S23]: https://docs.tia.siemens.cloud/r/en-us/v21/readme-tia-portal-openness/major-changes-for-long-term-stability-in-tia-portal-openness-v21
[S24]: https://cache.industry.siemens.com/dl/files/161/109997161/att_1348284/v1/S7-PLCSIM_Help_en-US.pdf
[S25]: https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-test-suite/style-guide/introduction?contentId=vhrgqy0GozdTa5nmKbdkNg
[S26]: https://cache.industry.siemens.com/dl/files/203/109801203/att_1135360/v1/109801203_Cont_Int_Jenkins_DOC_V13_en.pdf
[S27]: https://cache.industry.siemens.com/dl/files/203/109801203/att_1165141/v1/109801203_TestSuiteCodeCoverage_DOC_V1_0_en.pdf
[S28]: https://docs.industrial-operations-x.siemens.cloud/r/en-us/ax/introduction/2510/components-overview/axunit-st?contentId=XxlN1XBb6OrsBqFKFMS8Xw
[S29]: https://docs.industrial-operations-x.siemens.cloud/r/en-us/ax/faq/2510/axunit-faq?contentId=ngdCgkYcTZIS1LsNl22gOg
[S30]: https://docs.tia.siemens.cloud/r/en-us/v21/compiling-and-loading-rt-unified/simulating-control-with-plcsim-rt-unified/using-plcsim-rt-unified?contentId=GuECKvKn9EBp3MfrkMcqTg
[S31]: https://www.siemens.com/en-us/products/simatic/s7-1500v/
[S32]: https://docs.tia.siemens.cloud/r/simatic_et_200sp_manual_collection_frfr_21/general-information/cpu-function-manuals/s7-plcsim-advanced-api/iinstance/interfaces-for-iinstances?contentId=fnxl36GBLhx83IO0PcUbGg
