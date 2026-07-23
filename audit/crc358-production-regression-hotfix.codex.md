---
module: crc358-production-regression-hotfix
agent: codex
identity_kind: git_commit
identity_value: c07266e5955d6d8ec764a351a87d8e1cc6e41887
---

# CRC358 生产内容回归热修审计（Codex）

本审计只覆盖冻结业务提交 `c07266e5955d6d8ec764a351a87d8e1cc6e41887`。
项目负责人明确要求本轮由 Codex 自审，不要求 Claude 配对审计。病例文件仅用于受限的
Linux 候选验证；Git 中只保留脱敏别名、规则 selector、聚合计数与内容哈希。

## 发现表

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| crc358-production-regression-hotfix-01 | P0 | iyun129 的报告退步源于 Git 版本回滚。 | 诊断时生产进程 cwd、`REVISION` 与 `origin/main` 均为 `9d2280e1…5fd5`；旧版与当前版对同一脱敏病例的结果分别为 7/18 与 5/15，证明是同一新版本中的规则解释回归，而非 watchdog 或 Git 回滚。 | REFUTED |
| crc358-production-regression-hotfix-02 | P0 | pending 的基因级 LoF 规则可以无条件覆盖已审核的精确位点规则。 | `reportgen/rules/targeted_drugs.py:23-105` 统一计算 selector specificity；精确 c./p. 位点优先，只有同等 specificity 冲突才由 blocked 规则 fail closed。FieldMapper 与 CRC358 bridge 均调用同一选择器。 | REFUTED |
| crc358-production-regression-hotfix-03 | P1 | BRCA1/PMS2 的恢复会把同基因任意变异都扩大成 PARP 获益。 | `panels/crc_358_msi/rules/drugs.yaml` 只恢复 BRCA1 `c.505C>T/p.Q169*` 与 PMS2 原始输入 `c.1273delT/p.S425Lfs*23`；宽泛 LoF 行仍为 `needs_review/runtime_eligible:false`。正例、同基因反例和 specificity 冲突均有回归测试。 | REFUTED |
| crc358-production-regression-hotfix-04 | P1 | FLT3 p.G846D 被重新恢复为临床获益药物。 | 新金标准要求 FLT3 行 `benefit_count: 0`；审核凭据明确“研究提示，不恢复为临床获益药物”。Linux 候选的 18 个运行时段落为 14 获益、3 慎用、1 研究，研究段即 FLT3。 | REFUTED |
| crc358-production-regression-hotfix-05 | P1 | FieldMapper、2.1 表后处理和 Part3 仍可能对同一 selector 得出不同结论。 | `reportgen/core/_field_mapper_targeted_drugs.py:355-373` 与 `reportgen/core/template_bridge_358.py:1325-1363` 使用同一选择器；bridge 还在匹配前从 `variant_site` 拆出 c./p.，并在补行前复核最终胜出规则。定向测试与发布 QA 均通过。 | REFUTED |
| crc358-production-regression-hotfix-06 | P1 | 可以把历史报告差异标记为 `report_group_approved`，但不绑定当前审核文件。 | `scripts/check_historical_golden_release.py` 现在要求有效 receipt ID、当前 receipt、契约自身 SHA 绑定及精确 normalized diff SHA；缺任一项即失败。新增反例覆盖缺 receipt、契约未绑定和差异漂移。 | REFUTED |
| crc358-production-regression-hotfix-07 | P2 | 当前 CRC358 审核凭据与实际知识文件字节一致。 | `report_group_crc358_regression_restore_20260723` 覆盖 32 个 CRC358 工件，声明 bundle 与实算值均为 `2688bce6…9302`；严格知识门禁 `PASS`、issues=0。 | CONFIRMED |
| crc358-production-regression-hotfix-08 | P2 | 本热修会顺带放行尚未完成二审的候选知识。 | CRC358 仍保留 13 条 Part2 与 9 条 Part3 pending 行，运行时全部 fail closed；知识门禁的临床状态仍因 pending 行和病例 UAT 不足为 `BLOCKED`。 | REFUTED |
| crc358-production-regression-hotfix-09 | P2 | CRC301 或既有 7.16/7.20 工程修复被本热修冲刷。 | 发布 QA 对 CRC358、CRC301 和肺癌试点分别执行 golden reference/candidate/repeat diff，全部 PASS；业务提交未修改 CRC301 规则、模板或肺癌 Panel 文件。 | REFUTED |
| crc358-production-regression-hotfix-10 | P2 | 冻结提交具备工程发布质量。 | 后端全量 `642 passed, 4 skipped, 0 failed`；Ruff、`git diff --check`、严格知识门禁、历史契约注册和完整 release QA Gate 全部 PASS。 | CONFIRMED |
| crc358-production-regression-hotfix-11 | P1 | 工程 PASS 等同于完成 10 例报告组病例 UAT。 | 金标准与知识门禁仍明确记录病例级 UAT 未完成；本轮只能按项目负责人已授权的 CRC358 有限发布执行，不能描述为全库医学/UAT 完成。 | REFUTED |
| crc358-production-regression-hotfix-12 | P1 | 审计完成时该提交已经在生产运行。 | 审计冻结时生产仍为 `9d2280e1…5fd5`；部署和部署后活实例验收是后续独立发布步骤。 | REFUTED |

## 方法保真与限制

| id | mandated 方法 | actual method_status | verdict | evidence |
|---|---|---|---|---|
| crc358-production-regression-hotfix-M01 | 修复必须在隔离分支完成，不能污染原始脏工作树 | 独立 worktree 与分支 `codex/crc358-regression-hotfix-20260723`；业务提交父提交精确等于生产基线 `9d2280e1…5fd5` | FAITHFUL | `git show --no-patch --pretty=%P c07266e` |
| crc358-production-regression-hotfix-M02 | 患者资料不得进入 Git | 提交仅含 Python/YAML/测试与审计元数据；无 xlsx/docx/png、storage、签名、环境文件或凭据 | FAITHFUL | `git show --name-only c07266e` |
| crc358-production-regression-hotfix-M03 | 医学恢复必须限制到审核过的精确事件 | 仅恢复两个历史精确 selector；FLT3 研究-only；其余 pending 行继续阻断 | FAITHFUL | `drugs.yaml` 与 golden contract |
| crc358-production-regression-hotfix-M04 | 发布前必须使用生产同款 Linux/LibreOffice 生成并做阻断视觉 QA | 工作树阶段候选已验证 QA PASS；冻结提交的精确 SHA 候选、签名、金标 diff 和部署后活实例验收仍待发布阶段完成 | PENDING | 后续外部 release manifest |

## 冻结凭据

- 业务提交：`c07266e5955d6d8ec764a351a87d8e1cc6e41887`。
- 全量回归：`642 passed, 4 skipped`。
- 发布 QA Gate：`PASS`；凭据 SHA256
  `6c8c2d3cd38d9e20a1024758ec00d192f22327c33328a69f5b3ad4f865c2d8cd`。
- 严格知识门禁：`PASS`；凭据 SHA256
  `ad5964afdc899e23ab51e9414e160d37d08ecb3f6f9257a56ce2710f12dde3cf`。
- 历史契约注册：`PASS`；凭据 SHA256
  `3470eaf51376b27adad0a76f8cef9eabeebc46a9de6f654ccbf1eb603923dafc`。
- 医学边界：报告组既有二审与本次回归反馈已结构化绑定；22 条 pending 知识与
  10 例病例 UAT仍未宣称完成。

## 裁决

- 工程热修：**PASS**。
- CRC358 知识恢复范围：**PASS（精确 selector、有限发布）**。
- 全库医学完成度 / 10 例病例 UAT：**BLOCKED，未冒充完成**。
- 生产切换：**待精确 SHA Linux 候选、GitHub required check 与部署后活实例验收**。
