# 当前 SCL 的检查与修复

默认 mcode/CM 路径现在把专业资料、原程序、生成结果和工具反馈接到同一次任务。规格审阅仍先于生成；没有新增审阅角色。模型不直接操作工程工具，由控制器捕获当前源码并运行检查。

## 运行

沿用已配置的 mcode、现有 CM/Paperclip 公司和仓库外运行目录，再提供 matiec 编译器与标准库：

```sh
npm --prefix web ci
npm --prefix web run build
SIM_IEC2C=/absolute/path/to/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
npm --prefix web run dev -- --mcode /absolute/path/to/mcode \
  --cm-company EXISTING_COMPANY_ID --workflow-root /outside/repo/runtime
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

运行目录按任务保存 `request.json`、`knowledge.json`、`outcome.json`、原有模型调度记录以及 `attempt-N/`。每轮包含 `candidate.json`、`changes.diff`、`validation.json`、检查器捕获的 `sources/`、编译日志和扫描记录；完成审阅/修复时还保存对应结果。运行证据不写回规范 PLC 源码，也不自动提交 Git。

**导出工程草稿**包含需求、最终或未通过的候选、检查报告和循环记录。**打开工程草稿**重新计算需求指纹和每份源码 SHA-256；不匹配时拒绝旧记录。匹配只说明记录与文件相连，不能认证外部文件的来源；导入明确显示“本次未重跑”。以当前代码继续修改会准备新任务，旧结果过期。

工具缺失、适配不支持、本机运行超时或崩溃属于 unknown，不能伪报源码正确或错误。Linux 适配支持有限的 FB/ST 语法，通用编译通过也不说明行为已检查。LAD 仍是审阅网络；TIA 编译、PLCSIM、形式验证、实机及安全验收均未接入本循环。本次没有下载程序或连接现场 PLC。

## 回归

```sh
SIM_IEC2C=/absolute/path/to/iec2c \
SIM_MATIEC_LIB=/absolute/path/to/matiec/lib \
npm --prefix web test
```

原生回归明确检查：旧八次程序编译通过但违反十二次合同；十二次候选通过固定扫描；故意的 BOOL 类型错误由真实编译器拒绝；修复回调交付新源码后重新编译和扫描通过。测试中的模型应答是显式夹具，不能当作在线 mcode/CM 验收。未配置编译器的测试会明确跳过原生部分。
