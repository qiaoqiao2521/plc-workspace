# 生成前预期（冻结）
固定时间：2026-10-01，首次模型生成前。此文件不随生成结果修改。

## 场景 A 装箱输送 / FB_ConveyorPack / S7-1200 / TIA V18
原文需求：一段输送带，把箱子从入口送到末端。Enable 只允许启动；输送过程中撤销 Enable 不取消已接受命令。Start 新上升沿、无故障且无 Stop 时从待机启动，末端 AtEnd 到位停止电机并输出一拍 Done。正常 Stop 撤销当前动作；已有故障保留，解除 Stop 后 Reset 才清故障。Reset 正常时取消动作，Reset 与 Start 同拍不重启。启动那次调用不计等待，之后最多等待 8 次 FB 调用，到第8次仍不到位就锁存超时故障；到位与超时同拍按到位成功。故障后不自动重启，Start/Reset 边沿每拍消费，不能把 Stop期间按住Start 当成恢复后新启动。Main LAD 每拍调用 FB，硬件地址未定，不要编造。

|ID|生成前验收预期|
|---|---|
|A01|FB 名称、CPU、TIA 和任务一致；Main LAD 每拍无条件调用一个持久 FB 实例。|
|A02|只有 Idle、Enable=1、无 Error、无 Stop、Start 新上升沿才能启动。|
|A03|运行后 Enable=0 继续输送，Motor/Busy 继续为真。|
|A04|AtEnd 停 Motor/Busy，Done 当拍为真、下拍为假，回到可待机状态。|
|A05|正常 Stop 取消动作，无故障；已故障 Stop 不清 Error/TimeoutFault，Stop 与 Reset 同拍也不清。|
|A06|解除 Stop 后新 Reset 上升沿清故障；正常 Reset 取消动作；Reset 与 Start 同拍不重新启动。|
|A07|启动扫描等待计数=0；随后第1至7次未到位仍运行，第8次未到位锁存超时。|
|A08|第8次等待 AtEnd=1 时到位优先，不报超时；故障后不能自动重启。|
|A09|Start/Reset 历史每扫描更新；Stop 期间 Start=1 后松 Stop 且持续 Start=1 不启动。Reset 被 Stop 消费后持续按住不应清故障。|
|A10|I/O 输入 Enable/Start/Stop/Reset/AtEnd，输出 Motor/Busy/Done/Error/TimeoutFault；无虚构硬件地址。|
|A11|规格/I/O/SCL/LAD/检查互相一致，检查结论对应生成物；模型自报通过不等于编译或形式证明。|
|A12|导出结果可读并包含审阅资产；更改需求后旧工程导出失效。|

## 场景 B 双缸夹紧 / FB_ClampPair
原文：先夹紧，再推进，最后同时松开退回；既要求任意时刻 Stop 都保留故障等待 Reset，又要求 Stop 同拍清除所有故障。气缸到位开关、阀型、超时、CPU/TIA 和复位后位置均未定，先不要自行假设。

|ID|生成前验收预期|
|---|---|
|B01|明确指出 Stop 保留故障与同拍清故障互相冲突，要求用户选择。|
|B02|澄清到位反馈、阀型/掉电或停止行为、各阶段超时及时间基准。|
|B03|澄清 CPU/TIA、复位后的允许位置和动作。|
|B04|未澄清前不生成伪确定的可投产逻辑；若预处理阻止生成，第二次预算留空。|

## 附加 UI
空/短需求有可理解提示；编辑旧需求后旧结果不可导出；任务导入/导出可读；错误/取消/刷新恢复可继续；390px 宽规格、长代码、LAD 网络可读。

## 静态逐扫描参考序列
所有未列输入为0，Enable 默认1。扫描0全部低建立边沿历史。扫描1 Start=1 启动等待=0；扫描2 Start=0、Enable=0 应继续；扫描3至8无AtEnd，扫描8是第7次等待；扫描9无AtEnd才超时。变体扫描9 AtEnd=1 应成功 Done=1；扫描10 Done=0。运行中 Stop=1 应取消；故障后 Stop=1、Reset新沿应保持故障，随后 Stop=0、Reset仍1应不清，Reset归0再新沿才清。Idle 时 Reset与Start同拍均新沿应不运行；Stop时Start新沿后持续按住松Stop不应运行。

没有 TIA/PLCSIM 时，不给编译/仿真/设备通过结论。逐扫描实际一栏仅是生成代码静态推演，并非设备执行。
