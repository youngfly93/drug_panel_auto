# 肺癌329+PD-L1 (lung_329_pdl1) C-beta 进展与发现（2026-05-31）

> 分支 `feat/lung-329-cbeta`。承接 docs/lung329_cbeta_assessment.md（评估）。
> **核心结论：模板结构层 C-beta 已完成且验证；但报告内容是 CRC 味的，根因在人工
> 策展层（不是模板能修的）。** 仅记录 + 留底，未做内容策展（需报告组输入）。

## 一、模板结构层：✅ 已完成并端到端验证

把 lung MVP（标量-only 空壳）升级为正式金标 `lung_329_pdl1_golden_template_v1.docx`：

- 注入 `__PART3_MARKER__`（第三部分逐变异叙述）。
- 变异/药物/免疫表转 `{%tr%}` 循环：`variants_2_1`(表6)、`targeted_drug_tips`(表1)、
  `immune_positive/negative/hyperprogression_results`(表11/12/13)。
- PD-L1(表9)标量 `pdl1_tps/cps/result`（IHC 表单录入）。
- panel.yaml：default→v1、v0 deprecated、v1 配 crc_301 同款金标处理器链、草稿护栏(status=draft)生效。

**端到端验证**（合成肺 Excel EGFR/KRAS/TP53）：CRC 流水线**自动填**变异表/药物表/3 个免疫表、
`__PART3_MARKER__` 渲染逐变异叙述、PII-clean、无残留占位、包校验 PASS。
commits：a70fce9（marker+变异/药物循环）、ea5acca（免疫循环+panel.yaml）。

## 二、🔴 但内容是 CRC 味的——根因在人工策展层（精确定位）

审真实产出（tmp/lung_v1_full/full.docx）发现：表填得对、结构对，但**叙述与药物内容
带结直肠癌信息**。逐个锁定根因：

| 现象 | 根因 | 性质 |
|---|---|---|
| **Part3 叙述引结直肠癌**（KRAS"35-45%结直肠癌"、TP53"389名Ⅲ期结肠癌"） | `config/settings.yaml:613` `reviewed_part3_overlay_path` **全局硬指向 `panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml`**，所有 panel 共用这份 CRC 人工策展 | 配置+内容 |
| **药物 CRC 味**（KRAS 耐药=西妥昔单抗/帕尼单抗=结直肠抗 EGFR 逻辑；TP53→AZD1775） | `targeted_drug_db_public.xlsx` 的 gene 级条目本身是 CRC 混合，gene 级静态、**不按癌种过滤** | 内容 |
| EGFR 药名漏出 `CIViC:Tier I - Level` 标签 | 药物字符串格式化把证据来源标签拼进了药名 | **代码 bug（可修）** |

> 基础 `gene_knowledge_db.xlsx` 是脱敏的（0 处癌种词），**不是**叙述 CRC 味的源头；
> 源头是**人工策展 overlay + 药物库条目**。lung 药物过滤 profile（settings.yaml:548，
> 匹配"肺/肺腺/nsclc"）**存在且对 CGI/CIViC 生效**（EGFR→Erlotinib 是肺有效的），但
> 管不到上面两个静态来源。

**因此 lung329-onboarding 记忆"大 panel 不建新知识库"的假设需修正**：基础 KB 可泛癌
复用，但**人工策展层（reviewed_part3_knowledge + 药物库条目）是癌种特异的**，lung 必须
有自己的，否则全局继承 CRC。

## 三、要让 lung 真正可交付，还差（内容/架构层，非模板）

1. **panel 级化 `reviewed_part3_overlay_path`**（架构/代码）：让每个 panel 用自己的
   `reviewed_part3_knowledge.yaml`，而非全局 crc_358。lung 无此文件时回退基础 KB（叙述
   变通用但不会"串结直肠癌"）。
2. **lung 人工策展内容**（内容，需报告组）：写 lung 的 `reviewed_part3_knowledge.yaml`
   （肺癌癌种叙述）+ lung 的靶向药物条目（去 CRC 抗 EGFR 耐药逻辑、TP53 研究药）。
3. **修 CIViC 标签漏出格式 bug**（代码，小，可独立修）。
4. **deferred**：NCCN 表(表2)动态 `检测结果` 列填充（静态指南内容已对）；逐药化疗
   PGx(表14-48,~35表)接病人基因型。

## 四、状态与建议

- **模板结构层成果值得留底/合并**（基础设施，不影响别的 panel；v1 是 draft、有草稿护栏）。
- **但 lung 不能直接交付**：内容 CRC 味是 deliverability 闸，且是内容/架构任务，需你/报告组
  决定（curate lung 内容 vs 接受手工改 CRC 串味 vs 先 panel 级化 overlay 让叙述变通用）。
- 未做任何内容策展（不擅自代报告组写肺癌医学内容）。
