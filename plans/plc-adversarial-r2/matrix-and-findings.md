# plc-adversarial-r2 — 修复前后矩阵与发现

日期：2026-09-26/27。对象：plc-workspace @ master cf37971（验证链 scope 文件干净）。
登记：CapMesh exp-da2a4f55f6876751b86ea28e（mutation，attempts 6 / corrections 3，实际用 4 attempts）。
判定表（先于变体固化）：`plans/plc-adversarial-r2/oracle/expected-behavior.md`。
诚实声明：实现已读，非盲测；预期全部从 scan-contract v0.3（sha256 a9b0e239…）文本推导。

## 发现（按严重性）

| # | 严重性 | 发现 | 机制 | 责任层 |
|---|---|---|---|---|
| F1 | 高（安全相关语义漏检） | 阈值切零冻结计时器：等待中 N→0 时 timer 保持旧值，恢复正值后提前到期甚至立即误报超时。违反 F2「Zero disables counting and keeps timer zero」+ F1。所有既有层（扫描 25/驱动/形式 31@300s/驱动差分）全部放过 | M1 | 无（修复：P32 + 原生回归） |
| F2 | 高（命令生命周期漏检） | Reset 接受从上升沿退化为电平：停止释放后保持的 Reset 被当作新接受，CommandAborted 提前清除。违反 C3+E3。所有既有层放过；160 组合矩阵单拍结构上无法区分沿/电平；断言 P6 以 xResetAccepted 为基准与实现共模 | M2 | 无（修复：原生回归；形式侧经反例证实 EoC 单状态断言不可表达，撤回了首版错误 P33） |
| F3 | 中（证据验收缺口） | 正向断言集被削弱（删 P29–P31，31→28）后刷新七步全过并成功发布；发布 README 硬编码声称「31-assertion conjunction」与实际 28 不符；负控件验收（恒假断言必须被拒）无法覆盖正向削弱 | M3 | 刷新门禁验收条件（修复：required-assertions 门禁 + 发布文本派生） |
| F3a | 高（复审证实，2026-09-27） | 首版 required-ID 门禁只防删除不防削弱：保留全部 32 个 ID、表达式全部改 TRUE 后真实形式门禁 pass（复审人独立实证；本轮独立复现同结果，见 evidence/P1）。"削弱断言集无法再通过"的原表述不成立。复审人未跑完整发布流、未声称发布复现——本轮补跑完整发布流：修复后门禁在形式步 BLOCKED，刷新中止，哈希核验未发布 | M3 变体（保留 ID 改恒真） | 门禁校验粒度（修复：逐行钉定表达式 + 基准更新规则 + TRUE 削弱回归） |
| F4 | 信息（环境事实） | 当前机器下 nuXmv 60s 默认预算不足以完成 31/32 断言正向联合证明（历史 ~47s，现需 ~100-160s）；形式 unknown 需 300s 扩展归因 | — | 环境预算（未改默认值，如实记录） |
| F5 | 信息（本次实验自身） | 首版 P33 被修复后基线反例证伪（EoC 提交后记忆=本拍输入，断言恒假）；V5b 首次重建锚点放错使变体无效；required-ID 门禁首版使"整集替换"式负控件被提前 BLOCKED（exit2），破坏刷新流的负控件验收路径——真实运行暴露后，负控件改为在完整必需集上**追加**恒假断言（求解器拒绝路径不变，「删减削弱」与「追加假断言」分别由 ID 门禁与求解器两条路径验证）。三者在交付前发现并纠正，原始日志保留 | — | 实验质量过程 |

## 修复前矩阵（交付体系 @ cf37971）

| 变体 | 漂移门(未同步) | 漂移门(同步后) | 原生扫描 | 原生驱动 | 形式 | 系统结论 |
|---|---|---|---|---|---|---|
| M1 切零冻结 timer | 拦截(exit1,门禁本职) | 放行 | 25/25 OK（漏） | pass（漏） | 60s unknown→**300s pass**（漏） | **missed** |
| M2 Reset 电平接受 | 拦截(同上) | 放行 | 25/25 OK（漏） | pass（漏） | **60s pass**（漏,共模） | **missed** |
| M3 弱化断言集发布 | —（对象为刷新流） | — | 25/25 OK | pass | 28 断言 pass；负控件仍被拒 | **missed**（发布成功，README 声称 31） |

## 修复内容（全部最小化，未放宽任何判定）

1. `assertions.scl`：+P32_ZeroThresholdKeepsTimerZero（契约句「Zero disables counting
   and keeps timer zero」直接导出；N=0 且忙相等待拍时 timer 必须为 0）。
   首版 P33（Reset 接受⇒相对记忆寄存器的上升沿）被修复后基线反例（错误码 33）证伪后
   撤回——EoC 单状态断言下该义务不可表达，归原生层，properties.md 已记录理由。
2. `validation/tests/test_scan_semantics.py`：+test_zero_threshold_midwait_keeps_timer_zero
   （判定表 §1 逐拍独立预期）；+test_reset_held_across_stop_release_not_accepted（§2）。
3. `03_checks/plcverif/required-assertions.txt`（新）：初版只钉 ID——2026-09-27 复审
   证实保留 ID 改恒真可绕过（F3a）；现钉住 P1–P32 **逐行全文（ID+表达式）**，文件头写明
   基准更新规则（先改 assertions.scl → sync --write → 同一变更内镜像到本文件，门禁拒绝
   任何漂移）；`run-semantic-modelcheck.py` 在求解前逐行核验，缺失/改写即 BLOCKED exit2；
   额外断言行容忍（无法满足已被违反的必需断言，负控件追加路径不受影响）；
   `test_modelcheck_verdict.py` 单测 5 条，含"保留 ID、表达式改 TRUE"回归。
4. `refresh_evidence.sh`（lab 工具，M3 责任层）：发布 README/summary 的测试数、断言数、
   工具数从本次运行产物派生，不再硬编码（消除「发布文本与实际运行不符」缺口）；
   负控件构造改为在完整必需集上追加恒假断言（保持求解器拒绝路径，适配 required-ID 门禁）。
5. `properties.md`：P32 与"Reset 边沿义务归原生层"的边界如实记录。

## 修复后矩阵（修复后基线全绿：漂移门 PASS、27/27 扫描、驱动 pass、32 断言 @300s SATISFIED、工具 7+4）

| 变体 | 原生扫描 27 | 驱动 | 形式 | 命中检查 | 结论 |
|---|---|---|---|---|---|
| M1-postfix | **1F=新测试** | pass | **fail @300s（码32=P32）** | test_zero_threshold_midwait… + P32 | **detected** |
| M2-postfix | **1F=新测试** | pass | pass（预测空真，如实记录） | test_reset_held_across_stop_release… | **detected**（原生层） |
| M3-postfix | — | — | 形式步 **BLOCKED**：缺 P29/P30/P31（exit2） | required-assertions 门禁 | **拒绝发布**；62 个证据文件哈希前后一致（N5 核验） |
| P1-postfix（保留ID改TRUE） | — | — | 形式步 **BLOCKED**：32 行必需断言逐行缺失（exit2） | 逐行钉定门禁（F3a 修复） | **拒绝发布**（完整刷新流中止 exit1；哈希核验未发布）；修复前同副本=pass（evidence/P1） |

## 既有变体回归（重建自修复后仓库；选择依据见下）

| 变体 | 扫描 27 | 驱动 | 形式@60s | 命中 |
|---|---|---|---|---|
| V1 边界晚一拍 | 1F(11) | pass(漏,已知) | **fail** | 码30=P30 |
| V3 Start 未消费 | 1F | pass(漏,已知) | **fail** | 码27=P27 |
| V7 计时 +2 | 7F | **FAIL** | **fail** | 码31=P31 |
| V2 取消压故障 | priority matrix F | — | 跳过* | — |
| V4 提前提交 | 2F（含**新测试**也抓） | — | 跳过* | — |
| V5a 诊断清除 | 2F | — | 跳过* | — |
| V5b 非法相位虚报 | 1F(illegal_phase) | — | 跳过* | — |

*跳过 300s 形式重跑的依据：断言集只增不减（P7/P20/P28 原样保留），合取式性质单调——
先前被某条断言违反的实现，加入新断言后仍被违反；原生层（本轮快层）已确认捕获不变。
V1/V3/V7 全层重跑因形式步受断言集变化影响（且 60s 即 fail，无扩展需求）。
V5b 首次重建锚点错误（无效变体，scan OK），修正锚点后重跑为上表结果；两次日志均保留。

## 预算与运行记录（含失败与中断）

- 登记：attempts 6 / corrections 3 / stability 0；实际：3 exploration（E1-E3）+ 1 correction（C1）= 4。
  C2/C3 的修复验证因 CLI 纠偏规则（必须紧跟未解决结果，而 C1 已 detected 收口）未登记为
  correction，作为修复后回归执行并在此如实报告——未倒填、未重置预算。
- 形式预算：默认 60s；扩展（300s）使用：基线修复前 1 次（pass）、基线修复后 1 次（pass）、
  M1 探索 1 次（pass→missed 证据）、M1 纠偏 1 次（fail→detected 证据）、M2 纠偏 1 次（pass 空真）。
  其余形式运行 60s 内出结果。刷新流内正/负形式为真实运行（非桩）。
- 失败/中断运行（如实计入）：M1 探针首轮缺 enable 无效（重写）；M3 首次刷新因装备路径错误
  中断（refresh-run.aborted-harness.log）；V5b 首次重建无效（invalid）；最终仓库刷新前两轮
  失败——第一轮负控件被 required-ID 门禁 BLOCKED（见 F5，真实运行暴露的修复缺陷），第二轮
  使用了未含负控件补丁的过期适配脚本（装备错误）；第三轮成功。日志均保留
  （results/final-refresh*.log、refresh-run.aborted-harness.log）。
- 每个变体的扩展诊断均不超过一次，未隐藏任何重跑。

## 未验证边界

- Reset 边沿义务的形式化：EoC 单状态断言 + comments-only 约束下不可表达（共模空真已实证），
  仅原生层覆盖；若未来 PLCverif 用例支持跨状态性质可重开。
- 原生驱动为冒烟定位（历史已知边界），未加码。
- 未知错误类不被证明不存在；本轮只覆盖三个入选机制 + 复审证实的 F3a。
- required-assertions 逐行钉定防"删/改/保 ID 恒真"，但若同仓共谋修改门禁脚本与
  基线文件本身，门禁不防——工具链完整性超出本轮验证语义边界。
- Linux 编译 ST/形式证据不等于 TIA 编译、PLCSIM、实机或 F 安全验收（仓库边界不变）。

## 下一步（一个）

把 60s 默认形式预算在本机事实环境下上调或明确记录为环境差异（刷新流与门禁在慢环境
会以 unknown 中止）；负控件的"删减样例"路径已由 required-assertions 门禁承担，无需再扩展。

## 2026-09-27 独立验收更正

完整表达式门禁已验收；进一步拒绝空白或格式错误的基准，结果记录基准SHA-256。原生回归为27项，工具回归更新为10+4项。P1既有前后62文件哈希一致，证明该次隔离发布未发生。运行表是混合粒度活动记录，不能称为完整运行计数或预算合规证明；以run-ledger.md末尾更正为准。旧实验JSON及show快照是历史记录，不代表此次修改后的适用性。Reset边沿目前由原生回归覆盖；失败的P33只证明该写法错误，不是无法通过新增前态快照或时序属性形式化的证明。
