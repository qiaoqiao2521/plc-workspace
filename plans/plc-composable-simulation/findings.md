# Findings

## 基线事实

- `web/index.html` 已有固定输送仿真入口；`generation.css` 在 800px 以下隐藏导航，移动端仅提供回放链接。
- 8766 生成桥与 8767 固定仿真分离，前者未公开仿真能力。
- 旧仿真真实编译执行历史八拍输送源码，不能代表当前 `conveyor-12-v1` 工程。
- `NativeRuntime` 可以复用；原有 `__CURRENT_TIME` 未推进，不能因此承诺真实 TON 语义。
- 当前生成器已有独立预期、来源绑定和分项门禁，仿真接入不能绕过或覆盖它们。

## 外部复用

Open Industry Project 官方仓库提供 Part SDK、Three.js/Jolt 设备场景、无头命令行和项目测试；桌面 MCP 与无头 CLI 是不同入口。本轮按实际克隆的固定提交开发，不依赖网页文档推定兼容。

上游来源、许可、固定提交和已运行命令保存在 `integrations/open-industry-project/`，不复制整仓上游到项目记忆。

## 需要保留的区别

场景组装正确、PLC 编译成功、独立断言通过、OIP 项目测试通过和 Siemens 验收是不同结果。没有测试的上游成功退出码不能获得本项目的仿真通过状态。渲染插值只显示执行快照，不能推进逻辑。

## 实现后的实际发现

- 只看 PLC Motor=0 不足以判定设备停止。类型合法的 Enable→电机旁路会让真实设备继续转；独立用例现在同时检查 PLC 动作输出、设备实际命令/运行状态、气缸互锁，错误接线在第 2 拍被检出。
- 不带 State 的输送/启停接口不能显示“状态 null”。UI 隐藏未提供的状态，保留实际 I/O，并以可读事件显示变化。
- 原生单拍 watchdog 不能限制一个 500 拍的慢批次。整批默认 30 秒，每次调用取剩余预算与单拍 2 秒中较小者，超时保留已完成轨迹并终止该实例。
- `export_trace` 的 not_run 是证据范围，不是文件导出失败。CLI 成功交付轨迹返回 0，轨迹仍不授予独立用例验收。
- OIP 原生物理世界实际在正常源第 5 拍看到 Done；8/12 次合同分别在第 9/13 拍超时。将 8 次源标为 12 次不会改写程序，实际断言失败。
- OIP 当前版本确实会在零测试时退出 0，适配器实测保留 not_run。专用报告策略回归已加入现有 CI，避免以后把退出码当验收。
- 进程终止必须展开 finally。实际在 native worker 已加载运行时发送 SIGTERM，OIP adapter 以 error/退出 2 返回，Node 与独立 worker 全部消失；没有将清理成功当程序通过。

旧规范 ST、生成器的固定启停/输送合同、历史八拍源码与投影未改。新推料是独立且明示的合成合同。升级上游前需更新固定来源索引并重新实测接口，当前文档不承诺浮动版本兼容。

## 西门子官方参照与设计补充

完整来源和版本见 [官方仿真基线](../../docs/SIEMENS_SIMULATION_BASELINE.md)，机器索引保存 32 个来源和 15 项 proposed 缺口。

- 109739660 给出 Advanced V7 / TIA V20 的 C# 输送带闭环；默认模式周期事件不是冻结锁步。示例中省略的异常处理、按名称复用实例及人工工程下载仍需适配器补足。
- 109758943 的 2026 Pick and Place 案例把 PLC、设备行为、机械运动分层，提供 MCD / Unity build 路线；据此提出位置单一计算来源、明确单位与耦合周期。
- Advanced V8 已明确列入 S7-1200 G2；Supported 表与未限定代际的 Unsupported 措辞需要合读。Test Suite 两个 MLFB 排除是另一层约束。
- Advanced V8 API 与旧 API 的接口兼容、Runtime Manager 对旧 API 的兼容是不同问题。Openness V21 又有独立的 net48 / 程序集迁移要求。
- 工艺 Stop、CPU STOP、freeze、故障消除、确认、重启需保持各自语义。API 覆盖 PLC 输出会影响结果可信度，报告需同时追踪程序命令、施加值和实际反馈。
- SIMIT 类型/实例、宏、ACI 与 CONTEC 提供可组装参考；V11.2 宏不能递归嵌套，材料拓扑也不能直接当控制 DAG 或完整物理模型。
- Test Suite Application Test、OPC UA System Test、AX 单测、HMI 和代码覆盖率分别对应不同验证范围。条件 RUN / WAIT 结束仍需断言；覆盖率不替代正确性。
- 新索引是研究与后续设计资料，所有 Siemens 执行状态为 not_run。它不注册 backend、不修改现有 schema、不改变已有合同或通过状态。
