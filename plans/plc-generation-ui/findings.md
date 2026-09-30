# Findings

- 已有 web 是编译 ST 轨迹展示；没有生成 API。PROJECT 与 README 也将验证层误作产品本体，需要与用户最新意图同步。
- 本机 agy 支持 --mode plan、--sandbox、--disable-slash-commands、--json-schema、--output-format json 与有界 --print-timeout。生成结果作为草稿，Agent 自报检查不升级为本地验证证据。
- Main=LAD、FB=SCL 的分工继续保留。LAD 网络图用于审阅，不能被称为已经编译的 TIA 工程。每个 FB 调用必须处理禁用扫描，不能把 xEnable 误作不调用 FB 的门。
- 前一轮遗留资产的接续责任仍见 plans/plc-frontend/legacy-handoff.md，未删除或假定废弃。

- 真实 CLI 暴露两项适配约束：--disable-slash-commands 使 plan 模式失效；当前 provider 拒绝整数 enum，必须用 integer 类型并在接收端核对 schema_version==1。后者导致两次 UI 模型进程 exit 3 和一次最小 schema 诊断失败；修复后同一 UI 需求在 50.8 秒内返回完整草稿。
- 内置浏览器未提供 Blob 下载事件。新增导出文本预览/复制入口并实测内容可见；浏览器剪贴板 API 成功提示可见，但系统剪贴板/文件保存不作验收声明。
