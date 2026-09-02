---
module: lung-report-accuracy-review
agent: codex
identity_kind: git_commit
identity_value: 808a289a7cb253745d0247066249fb8982454cbf
audit_date: 2026-09-02
---

# 肺癌 329/588 历史终版内容对齐复核

本表复核 Claude 在冻结生产基线 `808a289a7cb253745d0247066249fb8982454cbf`
上提出的 12 条发现。结论只描述该冻结基线；整改后的证据单列在后，不回写旧结论。

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-report-accuracy-review-01 | P1 | 肺癌指南药物提示表未按历史 10 行固定结构输出。 | fix_log.md:29 | CONFIRMED |
| lung-report-accuracy-review-02 | P1 | 既有数据库支持的 C/D 级研究性靶向药未进入病例靶向药表。 | fix_log.md:33 | CONFIRMED |
| lung-report-accuracy-review-03 | P1 | 化疗正文关闭且 CtDrug 附录未按 1B/2A/2B 过滤。 | fix_log.md:31 | CONFIRMED |
| lung-report-accuracy-review-04 | P2 | 混合送检样本的 TMB 参考值未跟随实际 TMB 测定样本。 | fix_log.md:35 | CONFIRMED |
| lung-report-accuracy-review-05 | P2 | 肺癌未检出列表错误复用 CRC 基因集。 | fix_log.md:37 | CONFIRMED |
| lung-report-accuracy-review-06 | P2 | 免疫正相关、负相关、超进展三表未列全历史固定基因集。 | fix_log.md:39 | CONFIRMED |
| lung-report-accuracy-review-07 | P2 | 禁用内容占位段落造成近空白页。 | fix_log.md:41 | CONFIRMED |
| lung-report-accuracy-review-08 | P2 | 329 缩短版模板存在孤行溢出且未覆盖综合版章节。 | fix_log.md:41 | CONFIRMED |
| lung-report-accuracy-review-09 | P3 | A 例肺癌诊疗知识前空白页来自历史源模板分页伪影。 | fix_log.md:64 | CONFIRMED |
| lung-report-accuracy-review-10 | P3 | TMB 单位缺空格且批量缺失 PD-L1 时表格未明确显示“未提供”。 | fix_log.md:43 | CONFIRMED |
| lung-report-accuracy-review-11 | P3 | 2.3 表连续同基因行重复显示基因名。 | fix_log.md:43 | CONFIRMED |
| lung-report-accuracy-review-12 | P3 | 批量提交后缺少明确成功提示和任务跳转。 | fix_log.md:43 | CONFIRMED |

## 整改后验证（不改变上述冻结基线 verdict）

- 指南 10 行、免疫 15/12/8、化疗 27/22/11、顺铂 9 行及肺癌未检出基因集由
  `backend/tests/test_lung_history_alignment.py:96` 起的确定性回归覆盖。
- TMB 测定样本来源和组织阈值 10 由
  `backend/tests/test_lung_history_alignment.py:155` 覆盖；CRC 金标样式回归保持通过。
- 329 基因表由 `scripts/align_lung_comprehensive_templates.py:185` 从治理清单生成，
  329/329 唯一且生成脚本重复运行哈希一致。
- 批量失败记录和 macOS 资源叉过滤由
  `backend/tests/test_lung_history_alignment.py:511` 与
  `backend/tests/test_lung_history_alignment.py:530` 覆盖。
- 前端批量成功提示和任务跳转位于
  `frontend/src/views/ReportGenerateView.vue:1186`、
  `frontend/src/views/ReportGenerateView.vue:1211`。
- 最终复验汇总见 `fix_log.md:49`：588 A/B/C 整本渲染全部 PASS，329 七场景
  7/7 PASS，相关回归 115 passed，肺癌 QA gate PASS。
- 首轮远端全回归额外检出 PTEN 同基因非登记事件被误纳入的问题；修复没有放宽旧断言，
  而是将固定 15/12/8 版式与 B/C 精确事件选择器分离。精确性回归 46 项通过，A/B/C
  真实输入结构合同 3/3 PASS，详见 `fix_log.md` 的 R5。

## 保留边界

329 当前只有合成边界输入，因此可以确认工程结构和确定性规则，但不能把它表述为真实
329 病例内容准确性 UAT。合成或未核实的 PD-L1 来源也不替代报告组医学签署。
