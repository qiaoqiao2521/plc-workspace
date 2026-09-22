# SCL 官方依据与仓库差距

核对日期：2026-09-22。结论：先按官方语言、执行模型与块接口约定收敛，撤回此前让用户选择“Enable 只管启动”的默认提案。以下保留官方依据及最初差距记录；后续用户授权“落代码”后已实现 v0.3，见文末实施结果。

## 依据与适用层次

1. **语言规范**：IEC 61131-3 定义 ST 等语言的语法和语义。当前公开目录为 2025 第四版；这里只读取了官方范围说明，没有取得收费全文，不能声称审查了全部条款，也不能据此假定目标 TIA 支持第四版全部特性。[IEC 官方说明](https://webstore.iec.ch/en/publication/68533)。Siemens SCL 文档说明其赋值和控制流；普通变量赋值不会统一延迟到下一扫描才生效。[STEP 7 赋值说明，V21](https://docs.tia.siemens.cloud/r/en-us/v21/creating-scl-programs/basics-of-scl/value-assignments?contentId=o~WsW2JCP_aS9jnZee42YQ)。因此，旧值快照是本项目用来保持决策一致性的设计，不是 SCL 自动提供的事务。

2. **CPU 执行模型**：循环 OB 由系统每周期调用，周期程序可能被其他事件中断；用户 FB 是否调用、调用几次取决于调用路径。因此本项目“一实例每扫描调用一次”是调用者契约，不是任何 FB 天生具有的保证。[Siemens Cyclic OBs，S7-1200 / V20](https://docs.tia.siemens.cloud/r/en-us/v20/functional-description-of-s7-1200-cpus-s7-1200/organization-blocks-s7-1200/cyclic-obs-s7-1200)。过程映像与普通变量更新也不能混淆。[过程映像说明](https://docs.tia.siemens.cloud/r/simatic_s7_1500_et_200mp_manual_collection_enus_20/basic-information/simatic-drive-controller/configuring/process-images-and-process-image-partitions/process-image-overview)。

3. **工程接口约定**：Siemens《Programming style guide》V2.1.0，04/2025，第 43–49 页，DA008/DA010/DA011/DA012：输出集中写入、不读自身输出；连续任务采用 enable 电平使能；单次任务采用 execute 上升沿，execute 撤销不取消已启动任务。两类接口的状态和诊断清除时序不同，不能统称“Reset 清一切”。这是官方工程指南中的规则，须明确采用其接口模型，不能冒称 SCL 编译器会自动强制。[官方指南](https://cache.industry.siemens.com/dl/files/084/109478084/att_1323050/v1/81318674_Programming_Styleguide_DOC_V2_1_0_en.pdf)。指南引用 LGF 模板，但本次未取得模板源码，不声称已导入或验证 LGF。

4. **EN/ENO 与业务使能不同**：SCL 条件调用可以不执行整个 FC；这不等于已执行 FB 内部的 enable=FALSE 分支，更不能据此推导动作输出会被清除。[官方 EN/ENO 说明，V20](https://docs.tia.siemens.cloud/r/en-us/v20/programming-basics/handling-program-execution-errors/en/eno-mechanism/en/eno-mechanism-in-scl/overview-of-the-en/eno-mechanism-in-scl)。

5. **急停与确认**：STEP 7 Safety 的 ESTOP1 对停止类别和确认有专门定义。ACK_NEC=1 时，解除 E_STOP 后还需要 ACK 上升沿；ACK_NEC=0 另有防止自动重启的约束。这不能推出普通顺控 FB 的 Stop、超时故障和业务 Reset 必须采用同一规则。ESTOP1 的 E_STOP=0 表示急停，仓库 xEStop=TRUE 表示请求，不能直接照接。普通 BOOL xEStop 也不等于已实现 F 安全功能。[ESTOP1 官方说明，Safety V20](https://docs.tia.siemens.cloud/r/en-us/v20/step-7-safety-v20-instructions/safety-functions/estop1-emergency-stop/off-up-to-stop-category-1-step-7-safety-v20)。

## 实施前的具体差距（历史记录）

检查对象：`projects/FB_MainSequence/02_src/st/FB_MainSequence.st` 及现有扫描契约。

| 当前实现 | 核对结论与后续动作 |
|---|---|
| xEnable 只参与 Init 的启动条件 | 是自定义启动许可，不符合上述持续 enable 模式。撤回“推荐保留 start-only”的建议；不能把参数名字当标准行为。 |
| xEvtStart 由调用者提供单拍事件，正常循环为 0→1→2→3→1 | 这是持续顺控中含启动命令的设计，不能只改变量名就宣称整个块是标准单次 execute。 |
| xTimeoutFaultPrev 从 VAR_OUTPUT xTimeoutFault 读取；译码也读 xError/xTimeoutFault | 与 DA008 的不读自身输出规则有差距。后续将持久故障移到内部 Static，使用内部派生值译码，最后统一发布输出。当前实现不因此自动成为 SCL 语法错误。 |
| xEStop OR xStop OR xReset 合成 xResetReq | 混合了停止请求、安全状态与故障确认；尚无官方依据支持这套自定义合并逻辑。需要按接口层次拆开，而不是找一个“标准 SCL 优先级”代替。 |
| 一个 xTimeoutFault 同时承载当前错误与锁存历史 | 后续区分任务状态与诊断记录，不能把某个官方接口中的 error 清除理解成所有历史诊断都被清除。 |
| uiStepTimeoutScans 按调用次数计数 | 是明确的抽象模型，不是时间单位。没有固定周期与调用路径，就不能把 N 拍宣称为 N 毫秒。 |

## 当时确定的工程方向

以持续运行的顺控核心为依据，优先评估 DA011 的持续 enable 接口，加上明确的子命令/启动握手；这是根据现有循环行为作出的工程映射，不是标准指定了本设备的全部工艺。先做 DA008 的内部状态/输出分离，再对持续使能、子命令中止、错误与诊断生命周期进行完整映射和测试。不得只修改 enable 下降沿的一个分支就标记 PLCopen/Siemens 全面符合。

普通停机后的工步恢复、机械回原点、停止类别仍依赖真实设备和安全设计，官方语言规范不能凭空补全缺失的 Main、子 FB 和 I/O。这些设备信息确实缺失时，再提出具体问题；不再把能从官方资料查到的接口规则交给用户任选。

原 12 个扫描测试、5,000 次对照和 16 条形式断言仍只是旧候选行为的验证，不是官方规范符合性证明。本次没有变更 ST、断言、派生文件或 proof-bound 扫描契约；此前证据哈希仍对应原候选。后续行为变更必须重验。

## v0.3 实施结果

现已完成内部状态/输出分离、持续 Enable、错误与超时诊断分离、Start/Reset 上升沿消费，以及停止后的命令中止状态。xReset 仅重置健康顺控；块错误通过 Enable 撤销清除，诊断通过下一次 Enable 上升沿清除。先前建议的“Reset 清块故障”未作为标准规则实施。

新增 xValid/xBusy/xCommandBusy/xCommandAborted/xTimeoutDiagnostic。接口为 0.2.0，具体调用者迁移见扫描契约。24 个扫描测试（含 160 组控制组合及 5,000 拍对照）、8 个工具测试、26 条形式断言通过；完整 OpenPLC 示例在原生执行中第 50 拍通过。这些是抽象代码证据，不是全套 PLCopen/F 安全/TIA 验收。
