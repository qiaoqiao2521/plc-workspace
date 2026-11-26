# Open Industry Project 接入

本目录把固定版本的 Open Industry Project（OIP）接成可由 AI、CLI 和本仓库 HTTP 服务调用的外部仿真后端。上游源码及依赖安装在仓库外；项目里只保存适配器、来源、许可、组装配方和验证证据。

当前已经实际接通两条执行路径，报告分别标明验证对象：

| 入口 | 实际执行对象 | 结果能说明什么 |
| --- | --- | --- |
| `catalog` / `assemble` | OIP 原生零件声明及组装、严格项目校验 | 零件可查询，真实项目可由原子操作组装、读取 |
| `upstream-tests` | OIP 自带 start-stop-motor 示例及其 PLC | 此固定版本的上游示例测试可运行 |
| `native-test` | 本仓库冻结的 SCL/ST → matiec → GCC → 持久 FB 实例，驱动 OIP/Jolt 场景 | 此份源程序在声明场景、时钟与断言下的闭环结果 |
| `export` | 场景文件、原始程序、来源和可选的匹配证据 | 可带到独立工作台审阅、重跑的 ZIP 文件 |

`native-test` 没有挂载 OIP 自带的 PLC 执行器。适配器拒绝含第二份 OIP PLC 程序的场景，`Motor` 来自本仓库实际编译的 FB，`AtEnd` 来自 OIP 真实物理传感器。所有结果保留 `siemens_acceptance=not_run`、`hardware_acceptance=not_run`；当前自动化检查没有运行 OIP 图形界面的视觉验收。

## 固定来源与安装

固定源码为 [Open-Industry-Project/Open-Industry-Project，3d888156f38974c8e2105e5e657a9f428fda3cb5](https://github.com/Open-Industry-Project/Open-Industry-Project/tree/3d888156f38974c8e2105e5e657a9f428fda3cb5)。来源、入口、`package-lock.json` 与许可文件 SHA-256 记录在 `source-index.json`。上游 MIT 许可原文保留在 `LICENSE.upstream`，完整第三方声明随上游 checkout 获取，导出包也会包含它。

要求 Python 3.10+、Git、Node.js 24+、npm；原码闭环另外需要本仓库现有 matiec/GCC 工具链。安装不需要桌面 MCP 或现场 PLC。

在仓库根目录运行：

```bash
python3 integrations/open-industry-project/setup.py --checkout /tmp/plc-oip-pinned
python3 integrations/open-industry-project/run.py --checkout /tmp/plc-oip-pinned doctor
```

没有 `--checkout` 时依次读取 `PLC_OIP_CHECKOUT`、`PLC_OIP_DIR`，再使用 `~/.cache/plc-workspace/oip/<固定提交>`。安装脚本 checkout 精确提交并执行 `npm ci`；发现现有目录版本不符、已有源码改动或目标位于本仓库内时会拒绝，不会覆盖已有项目。

## 查询、组装和上游测试

```bash
python3 integrations/open-industry-project/run.py --checkout /tmp/plc-oip-pinned catalog oip.belt-conveyor oip.diffuse-sensor oip.box
python3 integrations/open-industry-project/run.py --checkout /tmp/plc-oip-pinned assemble --output /tmp/plc-oip-conveyor
python3 integrations/open-industry-project/run.py --checkout /tmp/plc-oip-pinned --save /tmp/oip-upstream.json upstream-tests
```

组装配方在 `examples/conveyor-native.json`：一条 3 m 输送带、一个漫反射传感器、一个 0.3 m 货箱。脚本调用上游 `add-part.mjs` 添加零件，再调用 `validate-project.mjs --strict` 校验，未自行编写 `scene.json`。生成目录包含该版本的项目零件库，不依赖浮动的未来内置零件。

可以对其他已有项目调用 `upstream-tests --project /path/to/project`。当前上游在没有测试时会打印提示并以 0 退出；本适配器把这一情况标为 `not_run / no_tests`，零断言也不能成为成功。进程错误、无效 JSON、编译错误和断言失败分别保留证据，不会折叠为一个绿色结果。

## 本仓库原码驱动真实 OIP 场景

推荐显式传入冻结的当前工程程序对象：

```json
{
  "profile": "conveyor-12-v1",
  "source": "这里是完整 SCL/ST 源码",
  "filename": "FB_ConveyorPack.scl",
  "request_fingerprint": "可选的工程请求指纹",
  "request_id": "可选的工程请求标识"
}
```

```bash
python3 integrations/open-industry-project/run.py --checkout /tmp/plc-oip-pinned --save /tmp/oip-native.json native-test --iec2c /path/to/matiec/iec2c --matiec-lib /path/to/matiec/lib --program-json /tmp/frozen-program.json --project /tmp/plc-oip-conveyor
```

直接读取当前源文件也可以：

```bash
python3 integrations/open-industry-project/run.py --checkout /tmp/plc-oip-pinned --save /tmp/oip-native-12.json native-test --iec2c /path/to/matiec/iec2c --matiec-lib /path/to/matiec/lib --source web/data/simulation/conveyor-12.scl --profile conveyor-12-v1
```

省略 `--project` 会在临时目录里重新组装真实场景。省略整个程序参数则**明确使用历史 8 次等待演示源** `plans/plc-generation-ui/user-eval/candidates/FB_ConveyorPack.scl`，结果 profile 为 `conveyor-8-demo-v1`。只有 `conveyor-12-v1` 与 `conveyor-8-demo-v1` 两个接口得到支持；推料机构等其他 profile 会明确拒绝，不能套用输送场景的验证结果。

程序先通过本仓库 `simulation-core.prepare_program` 校验固定接口，再交给隔离的 `NativeWorker` 编译、逐拍调用。源文本先冻结并记录 SHA-256，Siemens 声明修饰的规范化沿用现有实现，不修改等待次数或控制分支。每一拍有 2 秒 native 执行 watchdog；HTTP 层另设整个子进程的运行预算。

### 扫描与物理时间

执行次序固定为“采样物理传感器 → 调用 FB 一次 → 将 `Motor` 写给 OIP → 前进 15 个物理步”。OIP 物理步长为 1/60 秒，示例每次 FB 调用之间前进 250 ms。首次采样前让货箱独立稳定 30 个物理步，这 0.5 秒不计为 PLC 调用。

这两个 profile 的超时单位都是 **FB 调用次数**：启动调用不计等待，8 次合同在 scan 9 到期，12 次合同在 scan 13 到期。示例的 250 ms 是明确的场景调度选择，并不宣称目标 PLC 的真实扫描周期。适配器不执行任务调度器，当前接口不支持 TON、真实时间任务、保持变量或厂商指令。固定步进便于重放，但没有验证跨平台浮点物理轨迹逐位一致。

### 独立检查与故障

三个正常源案例共有 14 个断言：正常到位、真实货箱卡住、传感器输入卡低。卡住通过 OIP `pinBody` 作用于真实物理刚体；传感器卡低只覆盖提供给 FB 的输入，报告仍保留真实传感器读数。正常流程必须实际移动货箱，收到真实到位信号，只输出一拍 Done，并在完成调用撤销 Motor、Busy 及输送带速度；故障流程检查指定等待调用数、停机和锁存。

另外会编译一个**合成负控**：在独立源副本的 FB 末尾注入 `Done := FALSE`，然后运行相同正常到位断言。原源文件不被修改，负控的源与运行时哈希单独记录；只有错误版本被同一断言检出，负控才算成功。负控错误本身不会计入原程序的失败数。

这些案例验证声明的闭环子集，Stop、Reset、边沿竞态等完整控制合同仍由本仓库对应测试覆盖；场景尺寸、摩擦、载荷和传感器安装点是演示配方，未根据真实设备标定。

## 报告与导出

所有 `run.py` 子命令输出一个 JSON 对象，可通过全局 `--save` 保存同一结果。适配器状态为 `passed / failed / not_run / error / unavailable`，统一 HTTP 层可以分别映射为 `pass / fail / not_run / unknown / unknown`，并保留原始状态。CLI 成功退出 0，断言失败退出 1，未运行、不可用或调用错误退出 2。

原码闭环报告保留原始源、规范化源、运行时源、场景、全部项目文件、配方、上游提交和锁文件哈希；包含逐拍输入、输出、真实传感器值、货箱位姿、故障状态与负控结果。上游自测和场景组装的成功不会升级原码验证等级。

```bash
python3 integrations/open-industry-project/run.py --checkout /tmp/plc-oip-pinned export --project /tmp/plc-oip-conveyor --program-json /tmp/frozen-program.json --report /tmp/oip-native.json --output /tmp/plc-oip-review.zip
```

导出包包含可在固定版本 OIP 工作台中打开的 `project/`、完整 `native/program.json` 与 `native/source.scl`、绑定和来源、许可与第三方声明、可选证据。附带证据必须与程序、profile、上游提交和场景身份全部匹配；导出或打开场景不建立新的测试结果。图形工作台用于审阅场景；本仓库原码闭环仍由这里的 bridge 执行。

## 已执行的验证

`evidence/` 保存 2026-11-26 本次实际执行的 JSON：3 种原生零件查询；真实项目组装与严格校验；上游示例 4 个测试、24 个断言；8 次与 12 次合同各 3 个原码闭环案例、14 个断言及 1 个编译负控；真实的无测试项目被判为 `not_run`。`test_reporting.py` 另验证空测试、零断言、坏格式、错误退出码和失败断言无法伪装成功。

`contract-mismatch.json` 是有意保留的失败证据：给 8 次等待的原源选用 12 次合同，卡料和传感器故障均在 scan 9 提前发生，两个要求 scan 13 的断言失败。适配器没有改写源程序来迎合所选合同。

```bash
python3 integrations/open-industry-project/test_reporting.py
```

`test_termination.py` 在 Linux 上实际启动一个含合法无限循环的合成 FB，观察到独立 native worker 已加载 `runtime.so` 并开始执行后，再对适配器进程组发 SIGTERM。`termination.json` 记录本次 0.079 秒内清理完 Node 与独立 native worker、适配器返回 `error` 和退出码 2。它只验证终止与清理机制，不是控制逻辑测试。

```bash
python3 integrations/open-industry-project/test_termination.py --checkout /tmp/plc-oip-pinned --iec2c /path/to/matiec/iec2c --matiec-lib /path/to/matiec/lib --project /tmp/plc-oip-conveyor
```

OIP 内部 `SimWorld`、项目编解码及 tag/step 接口都通过提交固定，这不是上游承诺的稳定 API。升级须改来源索引、重新核对零件参数与接口，并重跑上述证据。
