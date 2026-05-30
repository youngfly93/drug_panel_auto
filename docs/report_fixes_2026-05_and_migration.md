# 报告修复记录（2026-05）与多 panel 迁移指南

> 本文归档 2026-05 一轮针对 **crc_358_msi 金标模板报告**的缺陷修复，并说明每项
> 修复**迁移到其它 panel 模板**的难易。配合 `docs/onboarding_new_panel.md`、
> `docs/panel_package_spec.md` 使用。

## 一、修复清单

| # | Commit | 问题 | 修复位置 | 层级 | 迁移性 |
|---|--------|------|----------|------|--------|
| 1 | c5f6e9b | 2.1 表「未见突变」基因名被加蓝色下划线（应纯黑）| `template_renderer._restore_variant_detail_table_style` | **core** | 自动 |
| 2 | a5731d1 | 2.1 基因变异检测结果未按频率高→低排序 | `field_mapper._build_variants_2_1` | **core** | 自动 |
| 3 | 73a3930 | 1.检测结果小结未按频率排序 | `_field_mapper_targeted_drugs._build_targeted_drug_tips` | **core** | 自动 |
| 4 | 72bd571 | 免疫小结计数与 3.3 明细不一致（CLNSIG 白名单误筛）| `template_bridge_358.build_immune_variants` | **bridge** | 共享 enhancer 的 panel 自动 |
| 5 | dc8e500 | 脚注「药物相关 N 个」与 2.1 表不一致 | `template_bridge_358.enhance_report_data` | **bridge** | 共享 enhancer 的 panel 自动 |
| 6 | fc2300f | 免疫表缺条件脚注（TMB-H 加 FDA 句 / TMB·MSI 不一致加生物标志物独立性句）| `template_renderer._apply_immune_table_notes`（独立处理器）+ panel.yaml 注册 | **core 处理器 + panel.yaml** | 需在新 panel.yaml 列出处理器 + 同款免疫表 |
| 7 | 4338666 | 第三部分「1.基因变异解析」引导段 ❖ 装饰符红色（应黑）| `template_renderer._recolor_part3_intro_marker`（underlines_and_styles 末步）| **core** | 自动（同款 ❖ 标记）|
| 8 | 4338666 | DNMT3A/FLT3 基因解析不全（兜底）| `panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml`（gene_sections）| **panel 数据** | 逐 panel/逐位点策展 |
| 9 | 7f042f1 | 2.1 药物解析：药物列表未两端对齐、同位点重复抬头 | `template_renderer._render_part3_formatted` | **core** | 自动 |
| 10 | 7f042f1 | 药物关联分析缺「该样本检出{基因}…{类型}突变。」变异描述开头 | `mutation_description.build_variant_lead` + `gene_knowledge.build_drug_analysis_sections` | **core** | 自动 |
| 11 | b6cb7ae | FLT3 c.2537G>A 靶向药物未带出 | `panels/crc_358_msi/rules/crc.yaml`（reviewed_variant_overrides）| **panel 数据** | 逐 panel/逐位点策展 |
| 12 | 973053b | 签名图浮动错位/格式差；选无签名图的人静默空白 | `template_renderer._render_inline_signatures` + `report_generator._resolve_signature_image_fields` | **core** | 自动（同款检测者/审核者签名区）|
| 13 | 30b4cfa | 5.参考文献为模板写死的静态列表，正文引用的 PMID 不呈现 | `template_renderer._rebuild_reference_section`（处理器）+ `gene_knowledge.build_reference_lookup` + `template_bridge_358` 写 `reference_lookup` + panel.yaml | **core 处理器 + bridge + panel.yaml + 数据** | 见下「半自动」 |
| 14 | 214918f | 基因检测列表首列加粗（应与其它列一致）| `template_renderer._compact_gene_list_tables` | **core** | 自动 |

> 配套：每项均有回归测试（`backend/tests/test_report_regression.py`、
> `test_golden_template_pilot.py`）。

## 二、迁移性分级

**约 80% 的修复在引擎层（`reportgen/core/`、`reportgen/knowledge/`），对任何
panel「免费」生效**——只要新 panel：(a) 用相同的后处理器链（在其
`panel.yaml` 的金标模板 `processors:` 里列出对应处理器），(b) 报告结构含相同
锚点（2.1 表、Part3 各段、❖ 标记、检测者/审核者签名区、`Gene List`/`基因检测
列表` 表、`5. 参考文献` 段）。

### A. 自动迁移（core，零改动）
#1,2,3,7,9,10,12,14。处理器/字段映射对所有 panel 一视同仁，只要新模板有对应
结构锚点即可。

### B. 共享 enhancer 的 panel 自动（bridge 级）
#4,5。逻辑在 `template_bridge_358`，由 `CRC358Enhancer` 调用。
**crc_301_msi、lung_329_pdl1 与 crc_358_msi 都用 `CRC358Enhancer` → 自动继承。**
`lung_methylation`（enhancer 为空）走独立路径，**不继承**，需在其生成路径里复用
同名构建函数。

### C. 半自动（需新 panel 接线）
- **#6 免疫条件脚注、#13 参考文献重建**：核心逻辑在 core，但要在**新 panel 的
  金标模板 `processors:` 列表**里显式加上 `immune_table_notes`、`rebuild_references`
  （否则处理器不跑）。
- **#13 还需**：新 panel 的 bridge 写入 `reference_lookup` 字段（共享
  `template_bridge_358` 的 panel 自动有），且 KB 含 `参考文献` sheet。

### D. 逐 panel 策展数据（不自动）
#8,11 与 #13 的 `extra_references`：reviewed override 是**按基因+位点人工策展**的
数据（`reviewed_part3_knowledge.yaml`、`crc.yaml` overrides）。只在「KB 内容不足
以匹配终版」时才需要，**不是每个位点都要做**。每个 panel 维护各自的 override 文件。

## 三、新 panel 迁移清单

1. **enhancer**：新 panel.yaml 用 `CRC358Enhancer`（或自建 bridge 复用
   `template_bridge_358` 的 `build_*` 函数）→ 直接继承 B 类 bridge 修复。
2. **处理器链**：金标模板 `processors:` 至少包含（顺序参考 crc_358）：
   `part3_formatted_sections, rebuild_references, signature_placeholder,
   immune_table_notes, bullet_lists, signature_layout, front_matter_spacing,
   blank_page_cleanup, toc_refresh, final_refresh_cleanup, underlines_and_styles`。
   → A、C 类修复随之生效。
3. **模板锚点**：确保新模板含 ❖ 引导段、`检测者：/审核者：` 签名行、
   `Gene List for …`/`基因检测列表` 表头、`5. 参考文献` 段标题、2.1 九列变异表。
4. **KB**：`gene_knowledge_db.xlsx` 含 `参考文献` sheet（驱动 #13）。
5. **签名**：`config/signatures.yaml` 登记真人名→去背景手写 PNG（见
   `docs`/记忆 signature-system）。
6. **策展（按需）**：仅当某位点解析/药物/参考与终版有出入，才在该 panel 的
   `reviewed_part3_knowledge.yaml` / `crc.yaml` 加 override；其余靠 KB 自动出。

## 四、迁移风险点

- 新模板若**结构锚点措辞不同**（如签名行不是「检测者：…审核者：…」、参考文献
  标题不是「5. 参考文献」），对应 core 处理器会找不到目标而**静默跳过**——迁移
  时务必核对锚点文案，必要时放宽匹配。
- `lung_methylation` 等**不走 CRC358Enhancer** 的 panel：B 类（bridge）修复不
  继承，需单独接线。
- 处理器**顺序**有依赖（如 `rebuild_references` 要在 `part3_formatted_sections`
  之后、`toc_refresh` 之前，使分页/目录计入新参考文献数）。
