# CM Codex 用户评测：草稿流程可用，生成质量尚不能验收

2026-10-01；受评版本 `daf225336fd0d0a51a065f9876305e2cee3b026b`。用户要求 CM 中的 Codex 模仿真实用户输入需求并自行评测。CM 任务 `875f0dcb` 的执行绑定为 `codex_default / codex`；使用独立 Chromium 会话，真实填写、点击生成、查看五个页签、下载、导入、编辑和刷新。主 Agent 独立检查下载物，并追加离线扫描复核。

**结论：需求 → agy → 规格/SCL/LAD 审阅与导出已经可用。清晰输送需求的选定扫描行为符合预期；冲突双缸需求虽然得到澄清问题，却仍生成了未经确认的动作逻辑，并包含两个可复现的扫描反例。当前可作工程草稿工具，不能授予生成质量或 Siemens 工程验收通过。**

## 先固定预期，再生成

[生成前预期](user-eval/expectation.md) 在第一次模型调用前冻结；结束哈希仍为 `eb76e72087ecfa992443c54d9d87595a54aa3072067b77668511a3a52b3e7620`。

|真实用户场景|页面报告耗时|实际结果|验收边界|
|---|---|---|---|
|装箱输送：Enable 仅启动、Stop 保留故障、Reset 同拍不重启、8 次等待超时、到位优先、每拍消费边沿|80.9 秒|1 个完整 FB，1 个无条件周期调用 LAD 网络，I/O 输入输出各 5 项；工程/SCL/LAD 文件实际下载成功|CM Codex 静态推演一致；主 Agent 的规范化 ST 原生运行 16 个观察点一致；未做 TIA/PLCSIM|
|双缸夹紧：Stop 故障策略自相矛盾，阀型/反馈/超时/复位位置/CPU/TIA 未定，要求先不假设|55.5 秒|明确提出 7 个待确认问题；同时生成可驱动两阀的完整 FB，仍可导出|不满足“先不要自行假设”；两个扫描反例，见下文|

完整代码作为**有意保留的受评样本**：

- [FB_ConveyorPack.scl](user-eval/candidates/FB_ConveyorPack.scl)，SHA-256 `1ba2fd331d00e58748dce9086334ca96368a5fc308cc4bcd3e6235d4d883c49f`。
- [FB_ClampPair.scl](user-eval/candidates/FB_ClampPair.scl)，SHA-256 `3c3f3c01a6a647374d9966bd61ffb7998c159252e10d31a68e0d70b45623fcd0`。

样本没有进入 `02_src/st`，也没有继承仓库核心的 32 条断言证明。

## 发现与最短复现

### 高：提出澄清后仍擅自决定机械控制

双缸需求未确定阀型，生成物却把 `ClampValve/PushValve` 的 TRUE 定为伸出、FALSE 定为松开/退回，并决定 Reset 回 Idle。模型同时询问这些事项，说明它识别了缺口，却没有让缺口约束动作代码。[样本第 19 行](user-eval/candidates/FB_ClampPair.scl#L19)、[第 77 行](user-eval/candidates/FB_ClampPair.scl#L77)、[第 141 行](user-eval/candidates/FB_ClampPair.scl#L141)。页面正确标为未验证草稿，但标记不等于遵守“不自行假设”。

**反例一：Stop 仍为真时夹紧。** 从初始化 Idle 开始，同拍输入 `Enable=Start=Stop=Reset=1`。Reset 分支令 nextState 保持 0，跳过 Stop 的 ELSIF；旧/新状态相等，后续 CASE 接收 Start，提交状态 10、`ClampValve=1, Busy=1`。两种相互矛盾的故障清除策略都没有授权在 Stop 下新启动动作；这也违背生成物自己的“停止保持”描述。[第 77–89 行所在分支](user-eval/candidates/FB_ClampPair.scl#L77)。

**反例二：没有原位确认却 Done。** Start 新沿 → ClampDone=1 → PushDone=1，使状态 10→20→30；下一拍 `ClampDone=PushDone=ClampHome=PushHome=0`。`(NOT ClampDone OR ClampHome) AND (NOT PushDone OR PushHome)` 为真，提交状态 40、`Done=1`。其自身注释要求等待两缸回原位，实际条件却允许只离开伸出限位就完成。[第 105 行](user-eval/candidates/FB_ClampPair.scl#L105)。这证明软件报告了完成，不证明实际机械位置。

CM Codex 独立发现未经澄清的阀假设及原位反例；Stop/Start/Reset 的三输入反例由主 Agent 追加。B 原需求没有单独指定 Start+Reset 的优先级，所以**只含 Start+Reset、不含 Stop 的行为没有另冒充一条已给定工艺规则**。

### 中：刷新后无法重新打开自己的工程

CM Codex 真实操作：下载 A 工程 → 恢复原 A 任务的 brief/states → 保存 → 刷新 → 整理同样任务 → 导入原工程。前后 brief/states 完全相同，指纹均为 `18bf58ff6388579fc6d4b6298e75aa4afaf2572ee996f04e9164bd03bccb2d5e`，但新随机 request ID 导致拒绝，页面要求重新生成。

主 Agent 用已有示例独立复现同样障碍：刷新后重新载入同需求，指纹仍为 `3034ef471407…`，导入同工程仍被拒。另直接调用现有 `makeRequest/validateResult` 确认：`same_fingerprint=true; different_request_id=true; import=rejected`。

当前保存只保存 brief/states；导入只校验结果，不恢复工程中的原 request。[生成请求与匹配守卫](../../web/generation-model.js#L29)、[草稿保存与结果导入](../../web/generation.js#L150)。匹配守卫应保留，需另建完整工程恢复入口，而不是删掉需求绑定。

### 中：生成工程还没有自己的验证入口

“检查”页只显示 Agent 自报记录和仓库示例链接。A 的 3 项均未执行，B 为未执行/未知/未执行；没有伪称编译通过，也没有把既有示例证明绑到新工程。这是诚实标示的能力缺口：实际新代码没有自动进入编译/逐扫描检查，两个 B 反例未被网站拦截。

### 低：LAD 网络编号重复

A 的网络标题含“网络 1”，页面和 Markdown 再加一次编号，显示“网络 1 · 网络 1: …”。实际下载文件也如此。影响阅读，本轮未观察到控制逻辑影响。

## 离线运行复核与复现

[复现脚本](user-eval/reproduce-counterexamples.py) 复用现有 matiec/GCC，把**记录的生成物**编译为 C 并调用持久 FB，没有另写 Python 状态机。显式适配仅移除 Siemens 声明引号/属性/version/BEGIN、局部 `#` 与注释，按声明值展开整数常量；不改布尔表达式、分支顺序或反馈条件。因此它检查适配后的扫描行为，不能证明原 SCL 的 Siemens 语法、实际 TIA 调度或物理 I/O。

```sh
python3 plans/plc-generation-ui/user-eval/reproduce-counterexamples.py \
  --iec2c /path/to/iec2c \
  --matiec-lib /path/to/matiec/lib \
  --work-dir /tmp/plc-user-eval
```

[结构化复核结果](user-eval/offline-result.json) 绑定上述两份源码哈希：A 的 16 个观察点一致，B 的两个反例均复现。**脚本 exit 0 表示成功复现已知反例；候选判定 B 明确为 fail。** 它不是发布门禁，不可据 exit 0 放行 B。

## 交互结果、预算与未验证边界

真实 UI 已确认：空/短需求提示；正确同任务结果可导入；无效 JSON 报错后可以继续；修改需求使旧导出停用；五页签和真实下载文件可读。390px 时页面宽 390px，LAD 内部 360/360，长 SCL 内部 328/759 且可横向滚动，未撑宽页面。没有真机触摸验收。

|运行|计数/结果|
|---|---|
|CM 派发|2 次登记；第一次未注册父入口导致启动前断言，零执行器/模型调用；第二次实际运行 1 个 Codex CLI 任务，CM 最终状态 done，无错误，耗时 2482.3 秒（包含整个 UI 评测与取证）|
|网站真实 agy 生成|2/2 次，均结构化返回；B 工艺质量失败。网络记录仅有两次生成 POST，没有为改善结果重试|
|主 Agent 前端基线|10 项 JS、6 项 Python 均通过；不代替本次 PLC 验收|
|主 Agent 恢复探针|第一次 Node 探针因内建 crypto 属性只读失败；改为直接使用内建 crypto 后，确认同指纹新 ID 被拒|
|主 Agent 离线扫描脚本|4 次：首次 B 的 matiec CASE 常量适配失败；展开声明常量后成功；公共脚本参数化及输出范围修正后各复核一次。最终结果见上方 JSON|

Codex 任务内部的模型推理与工具轮次不包含在网站的 2 次 agy 预算里；没有声称所有 Agent 成本只发生两次。浏览器 CLI 出现过本机线程不足、fork 失败和命令超时，恢复后取得结果。页面耗时与实际取证间隔分别记录：A/B 首次结果快照分别在点击后约 176/187 秒取得；B 的模型执行仍为 55.5 秒，不能把自动化取证滞后冒充模型超时。

未执行 TIA/PLCSIM、真机、取消正在生成的任务、模型生成失败恢复、复杂 LAD 并联/计时网络、跨多次生成稳定性或公网服务验收。当前两个样本不能推导整体模型成功率。

原始下载、截图、完整 CM 报告与工具错误记录留在本机任务 `875f0dcb` 目录；Git 仅收录合成工艺预期、候选源码、复现方法和结构化扫描结果，没有原始运行日志、模型凭据或会话状态。Conveyor 样本原有 4 处行尾空格，原样保留以维持哈希；局部 Git 属性只对该受评样本允许这些空格，产品代码规则不变。第一次 CM 任务的登记状态异常尚待 CM 维护处理，不影响本轮已完成的实际评测证据。

## 下一步

1. 关键机械接口或停止规则未决时，先完成澄清，再允许生成确定动作逻辑。
2. 提供工程文件恢复入口，保留原需求绑定与“未验证”状态。
3. 将每份新生成物接入自己的编译/扫描检查，包含本轮同拍 Stop 与原位反例；随后才接 Siemens 工程验收。

本轮未修改产品生成器和 PLC 核心。接续 owner 为根 Codex；已知问题保持开放，既有未跟踪工程材料按 [遗留交接](../plc-frontend/legacy-handoff.md) 保留。
