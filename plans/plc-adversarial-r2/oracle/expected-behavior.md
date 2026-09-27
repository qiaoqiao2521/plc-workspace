# 独立逐扫描判定表 — plc-adversarial-r2

日期：2026-09-26。对象：plc-workspace @ master cf37971（工作树含无关脏文件，验证链文件干净）。
唯一依据：`projects/FB_MainSequence/01_specs/scan-contract.md` v0.3
（sha256 a9b0e239dc064fd4aa23aa98d5ff445b736de09f493dddd04f9213fcf9d161ca）。

**诚实声明（非盲测）**：写本表前已完整读过 `02_src/st` 全部 9 个文件、
`validation/` 全部脚本与测试、既有 lab 的 V1–V8 矩阵。本表条款全部从契约文本推导，
未从实现或旧 oracle 复制判据；凡契约文本与实现可能不一致处，以契约文本为准。
正因实现已读，本表的"预测"标注为知情预测，不是盲测预言。

记号：每行 = 一次 FB 调用（扫描）。前态 = 调用前的实例内部状态
（phase/timer/timeoutFault/diagnostic/aborted/enablePrev/startPrev/resetPrev）。
N = uiStepTimeoutScans 本拍输入值。错误原因 = xTimeoutFault 当拍值。

## 0. 契约关键条款索引（本表引用）

- A1（Invocation ownership）：每扫描恰一次调用，禁用也必须调用；状态在实例，不在输出。
- B2（Enable FALSE）：Init、timer=0、当前 Error/TimeoutFault 清除、Valid/Busy=FALSE、动作全断；
  忙命令取消报 CommandAborted（仅该拍可见，下一禁用拍清除）。
- B4（Enable rising）：新诊断会话，清除历史超时诊断；当拍新检出故障仍记录。
- C2：使能时既有故障/非法相位压过一切命令迁移；停止永不应答故障。
- C3：健康 Reset 仅在 Stop/EStop 释放后的**上升沿**被接受；Reset 是业务重初始化。
- C4：Stop/EStop/保持中的 Reset 抑制动作与正常迁移；健康序列回 Init；被取消步当拍不产生新超时。
- C5：Init+InitDone+Start 上升沿进 Transport；忙相每拍至多前进一次；**完成在到期拍获胜**。
- D1：Start/Reset 边沿记忆每拍更新（含禁用/停止/故障拍）；被忽略的请求被消费、不排队。
- D2：保持 Start 跨停止/复位/再使能不能重启；停止释放本身不恢复被中断步。
- E3（CommandAborted）：忙命令被禁用/Stop/EStop/Reset 取消时置位；使能期间保持，
  直到被接受的 Start 或健康 Reset；禁用取消可见一拍后随下一禁用拍清除。
- F1（Scan-count timeout）：进入相位 timer=0；其后等待拍 N>0 时 prev+1>=N 到期：
  第 1..N-1 拍保持，第 N 拍提交 Error+超时原因+诊断+动作断电。N=1 首个等待拍到期。
- F2：阈值逐拍生效：减小可立即到期、增大延长等待、**切零禁用计数且 timer 保持为零**。
- F3：完成仍获胜。F4：TimeoutFault=当前超时原因；TimeoutDiagnostic=历史；
  停止/复位/禁用不擦除诊断，新 Enable 会话清除。非法相位报 Error 但**不得虚报超时**。

## 1. M1 判定表：运行中阈值切零再恢复正值（条款 F1/F2/F3/C5）

前提序列 S0：调用1：enable=1, init=1, start=1（↑）, N=8 → 后态 phase=1, timer=0（F1 进入置零）。
调用2..4：全 FALSE 输入（等待拍），N=8 → timer=1,2,3；phase 保持 1；belt_forward=1；
无错误（prev+1=4 < 8）。

| 拍 | 输入 | 前态(phase/timer) | 预期后态 | 错误原因 | 动作输出 | 依据 |
|---|---|---|---|---|---|---|
| 5 | N=0（其余 FALSE） | 1 / 3 | phase=1，**timer=0** | FALSE | belt=1，q1=q2=0 | F2"切零禁用计数且 timer 保持为零" |
| 6 | N=0 | 1 / 0 | phase=1，timer=0 | FALSE | belt=1 | F2 |
| 7 | N=2（恢复正值） | 1 / 0 | phase=1，**timer=1** | FALSE | belt=1 | F1：prev(0)+1=1 < 2，继续等待 |
| 8 | N=2 | 1 / 1 | **phase=900，timer=0**，error=1，diagnostic=1 | **TRUE** | 全动作断电，valid/busy/command_busy=0，command_aborted 保持 | F1：prev(1)+1=2>=2 到期 |
| 9 | N=2, enable=1（其余 FALSE） | 900 / 0 | phase=900，error=1，diagnostic=1 | TRUE | 全断 | C2 故障保持 |

**完成同拍获胜（对照）**：拍 7' 改 N=2 且 transport_done=1：后态 phase=2（完成获胜，F3/C5），
timer=0，无错误（TimeoutReached 定义含"非完成拍"）。
**减小立即到期（对照）**：拍 5' 改 N=2（timer=3）：prev(3)+1=4>=2 → 当拍 900（F2 减小立即到期；
已被原生 test_live_timeout_reduction 覆盖，本轮仅回归）。

**M1 预测（知情）**：若实现把"切零"实现为"冻结 timer"（等待拍 N=0 时 timer 保持 3 而非清零），
则拍 7/8 的到期时刻提前——拍 7 即 3+1>=2 → 当拍 900，违反 F2/F1。
现有层预测：漂移门=拦截未同步（非语义检出）；原生扫描=漏（无运行中切零测试，
test_zero_disables 仅从 N=0 起步）；驱动=漏（N 恒 8）；形式 31=漏（P17/P29/P30/P31 均以 N>0
为前提，无"N=0 → timer=0"义务）；5000 差分=同源失明。→ 预测系统级 missed。

## 2. M2 判定表：Reset 接受必须以本拍上升沿为前提（条款 C3/D1/E3）

前提序列 S1：
- 调用1：enable=1, init=1, start=1（↑）, N=8 → phase=1, timer=0。
- 调用2：stop=1 → C4 取消：phase=0，command_aborted=1（E3），动作全断。

| 拍 | 输入 | 前态(resetPrev/aborted/phase) | 预期后态 | 依据 |
|---|---|---|---|---|
| 3 | stop=1, **reset=1（↑）** | 0 / 1 / 0 | reset **不被接受**（C3：停止未释放）；phase=0；command_aborted=**1**（E3 保持） | C3/C4/E3 |
| 4 | **stop=0, reset=1（保持，无新沿）** | 1 / 1 / 0 | reset 仍**不被接受**（C3"仅在上升沿"）；phase=0；command_aborted=**1**（E3：未被接受的 Reset 不清除） | C3/E3/D1 |
| 5 | reset=0 | 1 / 1 / 0 | command_aborted=1（保持，E3：直到被接受 Start 或健康 Reset） | E3 |
| 6 | start=1（↑）, init=1 | 0 / 1 / 0 | **start 被接受 → phase=1**，command_aborted=0（E3） | C5/E3 |

**D1 消费语义（对照）**：拍 4 中 reset 保持已被拒绝消费；拍 6 的重启只能来自 Start 新沿，
与 reset 无关。**禁用路径（对照）**：调用2' 改 enable=0：command_aborted=1 该拍可见，
调用3' enable=0 → command_aborted=0（B2/E3，已有 test_disable_abort 覆盖，仅回归）。

**M2 预测（知情）**：若实现把 Reset 接受条件从"上升沿"退化为"电平"（xResetRise 误作 xReset），
拍 4 即被"接受"：command_aborted 提前清零、清除请求逐拍生效——违反 C3/E3。
共模面：P6 以 xResetAccepted 为基准、P27 只钉"记忆=上拍输入"、P23 仅忙相——
预测原生=漏（无保持 reset 跨停止释放的 aborted 断言）、形式 31=漏 → 系统级 missed。
（160 组合矩阵每例仅单拍且 resetPrev 恒 0，无法区分沿/电平，预测漏。）

## 3. M3 判定表：证据发布验收条件（对象=刷新门禁，条款=发布验收准则）

发布成功的**必要**条件（来自 refresh_evidence.sh 声明的验收 + 证据 README 的声明内容）：

| # | 场景 | 预期判定 | 违反时的后果 |
|---|---|---|---|
| N1 | 负控件（单条恒假断言） | 必须 gate exit 1 且 verdict=fail，否则中止 | 假证据发布 |
| N2 | 负控件 unknown/超时/缺结果 | 必须中止（不得当通过） | unknown 冒充通过 |
| N3 | 正向形式 unknown/缺 result.json | 必须中止 | — |
| N4 | **正向断言集被削弱（如删除 P29–P31）但余集可满足** | **必须拒绝发布**；发布文本声称"31 断言联合满足"与实际不符 | **弱化证据冒充全量验收** |
| N5 | 真实未发布验证 | 比较 04_reports/ 与 docs/verification/ 目标哈希未变，非仅脚本打印 | 脚本打印≠未发布 |

**M3 预测（知情）**：N1–N3 已有显式检查（预测通过）；N4 无任何检查——
gate 只验证"正向 pass + 负控被拒"，不验证被满足的断言集等于契约要求的属性集；
发布 README 硬编码"31-assertion conjunction"。→ 预测：删除 3 条期限断言后
七步全绿并成功发布，发布门禁 missed。

## 4. 基线预期（正常实现必须满足）

S0 序列（M1 前提）与 S1 序列（M2 前提）按上表逐拍成立；
基线五层（漂移门/扫描套件/原生驱动/形式 31/工具套件）全绿；
负控件被拒（gate exit 1, verdict fail）。

## 5. 契约歧义记录（不择有利解释）

1. E3"保持直到被接受的 Start 或健康 Reset"：取消拍本身即置位；被接受的 Reset
   （若发生）在同一拍先置位（busy AND abort 分支优先）后由下一拍清除路径处理。
   本表 M2 只依赖"**未被接受的** Reset 不得清除 aborted"，不受该歧义影响。
2. F2 恢复正值后从 prev=0 重新计拍：契约"Entry sets timer=0"之 Entry 指进入相位；
   切零期间 timer 保持为零，恢复后按 F1 以当前 prev 继续判到期——本表按此解释。
3. N=0 期间 timer 的可观察性：输出不含 timer 字段（scan_runtime 暴露 UISTEPTIMERSTAT
   为测试通道），契约义务针对内部状态；原生层经由 runtime 的 timer 读数断言，形式层
   经 uiStepTimerStat 断言，两者一致。
