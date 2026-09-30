# PLC Workspace

让人输入需求或工艺流程，由 AI 整理状态机、I/O 与约束，生成 **Main LAD / FB SCL** 工程草稿，再验证该工程的扫描行为与逻辑。

验证工具与抽象顺控示例负责约束 Agent 的质量；产品入口是需求到工程的生成工作台。

## 本机运行

需要 Node 18+、Python 3.10+、已配置的 `mcode` 和运行中的本机 CM/Paperclip。使用已有本机公司 ID，不需要安装 npm 依赖。

```sh
npm --prefix web run build
npm --prefix web run dev -- --mcode /absolute/path/to/mcode \
  --cm-company EXISTING_COMPANY_ID --workflow-root /outside/repo/runtime
```

打开 http://127.0.0.1:8766 ：输入需求 → 整理步骤 → 审阅规格 → AI 生成工程 → 查看 SCL / LAD → 导出草稿。

本机桥接点击生成才启动严格流程：需求分析 → 监督审阅规格 → 生成 → 并发检查扫描语义与接口 → 同一监督者裁决。AI 角色只使用 mcode，由已有 CM/Paperclip 调度；未决工艺阻断生成，fail/unknown 不放行。不设生成时限，同时处理一份工程，支持取消。只监听本机，生成结果不会写进规范 PLC 源码。已配置模型仍可能通过其服务商处理需求，不代表本地离线推理。详见[执行规范](docs/PLC_AGENT_WORKFLOW.md)。

公开静态网站没有本机桥接时，可导出 Agent 任务并导入对应结果。云端生成服务尚未接入。

## 当前能力

- 中文需求、流程顺序与逐状态动作/完成条件编辑。
- 本机 mcode 按分阶段门禁生成、审阅结构化规格、I/O、SCL 和 LAD 网络草稿。
- 请求与结果绑定需求指纹；需求变化后旧结果过期。
- SCL 文件、LAD 网络规格与工程草稿导出。
- [验证与回放](web/README.md)：仓库已有 FB_MainSequence 的 6 个实际 ST 场景。

LAD 当前为简单串联触点/线圈与周期 FB 调用网络的审阅表示，尚不是 TIA 可导入工程。新生成代码待运行它自己的检查；仓库示例的 27 项扫描测试、32 条断言不适用于任意新工程。TIA、PLCSIM 和实机验收由 Windows 工程侧完成。

## 接续入口

- [PROJECT.md](PROJECT.md)：产品意图、现状与边界。
- [前端与本机生成](web/README.md)：请求格式、运行和导出。
- [扫描契约](projects/FB_MainSequence/01_specs/scan-contract.md)：已有核心的准确语义。
- [语义验证](validation/tests/README.md)：真实编译 ST 与形式门禁。
- [容器验证环境](docs/validation-setup.md)：原有 Windows/Linux 工具链步骤。
- [架构](docs/ARCHITECTURE.md)：生成入口与验证层之间的关系。
