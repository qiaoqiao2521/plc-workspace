# 运行对账表 — CapMesh exp-da2a4f55 与实际运行的逐项核验

应 2026-09-27 复审要求补做。结论先行：**CLI 登记只覆盖 4 个实验轮（3 探索 + 1 纠偏）**，
基线、装备、修复验证与回归运行在登记之外，靠本表与本地日志对账；此前"所有运行都计入
4 次尝试"的表述不成立，予以更正。中断与失败全部列入。登记身份/预算未作任何重置或倒填。

图例：记录位置 C=CLI attempt（exp-da2a4f55），L=本地日志/对账表（plans/plc-adversarial-r2
与 plc-adversarial-r2/results）。形式预算：D=默认 60s，E=300s 扩展（每变体至多一次）。

| # | 运行 | 结果 | 记录 | 预算 |
|---|---|---|---|---|
| 1 | 修复前基线五层（run_layers @cf37971） | 扫描25/驱动/工具 OK，形式 D=unknown | L results/baseline | D |
| 2 | 修复前基线形式扩展 | pass（31 断言） | L results/baseline/formal-300 | E |
| 3 | **C-attempt1 (E1/M1)**：漂移门(前) exit1；sync；五层 | 扫描25 OK、驱动 pass、形式 D=unknown | **C** + L evidence/M1 | D |
| 4 | E1 形式扩展（归因 missed） | **pass**（31 断言对错误实现满足） | **C** artifacts | E |
| 5 | E1 探针 S0 首轮 | 无效（漏传 enable，仪表缺陷） | L probe_S0.err | — |
| 6 | E1 探针 S0 修正版（变体+基线对照） | 触达+违反取证 | **C** artifacts | — |
| 7 | **C-attempt2 (E2/M2)**：漂移门、sync、五层 | 扫描25 OK、驱动 pass、形式 D=**pass**（共模） | **C** + L evidence/M2 | D |
| 8 | E2 探针 S1（变体+基线） | 触达+违反取证 | **C** artifacts | — |
| 9 | **C-attempt3 (E3/M3)**：植入削弱+sync | 31→28 | **C** + L evidence/M3 | — |
| 10 | E3 刷新第 1 次 | 中断（PVCLI 装备路径错误） | L refresh-run.aborted-harness.log | — |
| 11 | E3 刷新第 2 次 | **七步全过并发布**（弱化集 28 断言 pass，负控件被拒） → missed | **C** artifacts | E（正/负形式均真跑） |
| 12 | 修复应用（apply_fixes @repo + scratch 副本验证） | 单测 OK | L /tmp/fixcheck 输出留档于会话记录 | — |
| 13 | 修复后基线：工具套件+扫描 | 7+4 OK、27/27 OK | L results/fixed-baseline | — |
| 14 | 修复后基线形式 #1（含首版 P33） | **fail**（反例码33，我的断言写错） | L results/fixed-baseline/formal | E |
| 15 | P33 撤回、resync、单测复跑 | OK | L | — |
| 16 | 修复后基线形式 #2（32 断言） | **pass** | L results/fixed-baseline/formal2 | E |
| 17 | **C-attempt4 (C1/M1 纠偏)**：漂移门、sync、五层 | 扫描 1F=新测试、形式 D=unknown | **C** + L evidence/C1 | D |
| 18 | C1 形式扩展 | **fail**（码32=P32） → detected | **C** artifacts | E |
| 19 | M2 修复验证：扫描+形式 | 1F=新测试；形式 E=**pass**（预测空真） | L evidence/C2（登记外，CLI 纠偏规则不允许紧跟 detected 再开纠偏） | E |
| 20 | M3 修复验证：刷新（修复后门禁） | 形式步 **BLOCKED** exit2，中止；62 文件哈希不变 | L evidence/C3（登记外，同上） | — |
| 21 | 既有变体回归 V1/V3/V7（全层） | 扫描 F、驱动(V7 F)、形式 D=fail（码30/27/31） | L evidence/regression | D×3 |
| 22 | 既有变体回归 V2/V4/V5a（快层） | 均扫描 F | L evidence/regression | — |
| 23 | V5b 回归重建第 1 次 | **无效变体**（锚点错，扫描 OK 无意义） | L V5b-invalid-first-reconstruction-scan.log | — |
| 24 | V5b 重建第 2 次 + 扫描 | 1F=illegal_phase | L evidence/regression | — |
| 25 | 最终仓库刷新第 1 次 | 失败：负控件被 required-ID 门禁 BLOCKED（我的门禁缺陷，真实运行暴露） | L final-refresh-run.log（已被 run2 覆盖前的输出存于会话记录与 evidence/P1 关联说明） | — |
| 26 | 修复负控件（追加式）；最终刷新第 2 次 | 失败：适配脚本未含补丁（装备过期） | L final-refresh-run.log | — |
| 27 | 最终刷新第 3 次 | 成功发布：27/11/32 全绿+负控件 33 断言被拒 | L results/final-refresh-run.log | E×2（正/负形式） |
| 28 | 复审 P1 复现（复审人独立执行） | 保留 ID 全改 TRUE：门禁 pass（旧门禁） | 复审报告 | — |
| 29 | P1 独立复现（本轮）：旧门禁 | **pass**（32 TRUE 断言） | L evidence/P1/gate-before-fix-result.json | E |
| 30 | 修复：门禁逐行钉定 + required 全行化 + 单测 9 项 | OK（含"保留ID改TRUE"回归） | L validation/tests/test_modelcheck_verdict.py | — |
| 31 | P1 修复后：门禁对同一副本 | **BLOCKED exit2**（32 行全列缺失） | L evidence/P1/gate-after-blocked.log | D |
| 32 | P1 修复后：完整发布流（同一副本） | 形式步 BLOCKED，刷新中止 exit1；**哈希核验未发布**；期间第 1 次因副本 tests 过期中止于工具步（已更新重跑） | L evidence/P1/refresh-run.log | — |
| 33 | 复审后正常实现回归 | sync PASS、单测 9、扫描 27/27 | L 会话记录 | — |
| 34 | 复审后最终刷新（重绑定，含固定门禁） | 见 final-refresh-run2.log | L | E×2 |

对账结论：CLI 内 4 轮均有 begin/finish 与哈希绑定；表中34行是混合粒度的活动条目，包含登记内外操作、批量命令及刷新子步骤，不能用34减4得到登记外运行数。部分失败日志已覆盖或仅留会话记录，不能据此宣称完整原始日志全部保留。现存材料位于 plc-adversarial-r2/results 与 evidence/ 目录。
预算口径更正：**"总运行次数=4"不成立；4 仅为 CLI 实验轮数**。按表中预算标注合计至少13个300s求解器调用（不等同于13次超时后扩展，亦非完整命令级审计）
（行 2,4,11,14,16,18,19,27,29,34——每变体至多一次的约定按变体计）。
