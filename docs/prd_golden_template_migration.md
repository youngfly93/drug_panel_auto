# Golden Template First 迁移 PRD

## 1. 背景

当前报告生成链路已经具备 Web 上传、动态表单、Panel Package、规则引擎、QA、reference diff gate 和部署能力，但 CRC358+MSI 报告仍反复出现返修：分页空白、表格样式漂移、TMB/MSI 文案冲突、药物表缺失、免疫/NCCN 表误报、患者信息注入不稳定等。

这些问题的共同根因是：代码同时承担了数据计算、业务规则、Word 版式修复和客户报告结构对齐，导致修改点分散，返修很难被一次性收敛。

本 PRD 提出 `Golden Template First` 迁移：以报告组确认过的正确报告作为视觉母版来源，把动态区域抽象成受控变量、循环表格和规则输出。代码只负责生成 `report_context` 和执行少量必要 DOCX 技术后处理，模板负责结构和版式。

## 2. 目标

1. 以 CRC358+MSI 为试点，建立一条可灰度启用的 golden-template 生成路径。
2. 保留现有 legacy 生成路径，避免迁移期间影响当前生产能力。
3. 将“正确报告对齐”从人工目测改为可复跑的内容、表格、视觉、样式验收。
4. 为后续其它 panel 提供可复制的模板迁移规范。

## 3. 非目标

1. 不重写 Web 平台。
2. 不把患者姓名、样本号、报告编号或任何患者级数据写入仓库模板。
3. 不把复杂业务判断写进 Word 模板。
4. 不在第一阶段替换所有 panel。
5. 不用大量 post-processor 继续弥补模板结构问题。

## 4. 核心原则

1. **模板负责版式**：页眉页脚、章节顺序、表格样式、静态说明文字尽量来自 golden template。
2. **规则负责数据**：变异过滤、证据等级、TMB/MSI 判断、药物推荐、NCCN/免疫表均由 Python/YAML 生成。
3. **上下文负责交付**：渲染前必须生成可审计的 `report_context.json`。
4. **后处理只做技术兜底**：目录刷新、字段刷新、批注/修订痕迹清理、空段清理，不承担业务内容修补。
5. **所有样本级差异必须规则化**：禁止按患者、样本号、日期、单个变异做硬编码。

## 5. 用户与场景

| 用户 | 场景 | 成功标准 |
|---|---|---|
| 报告组 | 提供正确报告母版 | 能明确标注哪些区域动态、哪些静态 |
| 研发 | 新增或维护 panel 模板 | 不需要改大量 Word 后处理代码 |
| 测试 | 对照正确报告验收 | 能复跑同一套 diff gate |
| 生产操作员 | Web 生成报告 | 与旧路径一样上传 Excel、补患者信息、下载报告 |

## 6. 方案概览

新路径分为五层：

1. **Golden Source**：报告组确认的正确报告，仅作为本地模板种子输入，不直接提交含患者数据的原始文件。
2. **Template Seed Builder**：本地工具将 golden source 清洗成模板种子，替换患者级字段，检查残留敏感 token。
3. **Panel Template Declaration**：在 `panels/<panel_id>/panel.yaml` 声明 golden template、状态、处理器链和验收策略。
4. **Context Builder**：复用现有 `FieldMapper + Enhancer + RuleEngine`，输出可审计 `report_context`。
5. **Golden Renderer**：使用 docxtpl 渲染模板；按模板声明选择最小 DOCX 后处理链。

## 7. 数据分层

| 类型 | 示例 | 处理方式 |
|---|---|---|
| 标量变量 | 姓名、性别、年龄、样本号、报告编号、日期、诊断 | `{{ patient_name }}` 等 docxtpl 变量 |
| 循环表格 | 2.1 变异表、2.2 药物目录、NCCN、免疫表 | 模板保留样式行，代码生成 rows |
| 条件块 | HLA 表、特殊说明、空表隐藏 | 模板使用简单条件，复杂判断在 context 前完成 |
| 规则文本 | TMB/MSI 科普、药物提示、基因解析 | Python/YAML 输出最终段落 |
| 静态内容 | 公司介绍、免责声明、癌种基础知识 | 模板保留 |

## 8. 第一阶段试点范围

试点 panel：`crc_358_msi`

试点样本：本地 reviewed CRC358+MSI Excel，不提交仓库

参考报告：报告组提供的本地正确报告，不提交仓库

必须纳入验收的问题：

1. 患者信息完整进入封面和基本信息表。
2. 体细胞变异计数为 8，药物相关变异计数为 4。
3. FBXW7 不误入靶向药物表。
4. 2.1 表包含 TP53、KRAS、APC、APC、SETD2、EPHA2、FANCI、ATM 等正确行。
5. 2.2 药物目录生成 7 个上市药物行。
6. TMB 汇总表和 3.1 正文一致，均为 6.5/TMB-L/水平较低。
7. MSI 文案与正确报告一致。
8. NCCN 表不得误报 FGFR1/2/3。
9. 免疫表不得误报 POLE、ALK；DDR 仅展示符合规则的基因。
10. 不出现 page 45 这类近空白页。
11. 前 6 页结构和视觉接近正确报告。
12. 输出报告不含批注、修订痕迹、患者种子残留或 debug 文本。

## 9. 交付物

| 交付物 | 路径 | 说明 |
|---|---|---|
| PRD | `docs/prd_golden_template_migration.md` | 本文件 |
| 模板种子构建工具 | `scripts/build_golden_template_seed.py` | 从本地 golden source 生成清洗模板种子 |
| Panel 模板声明 | `panels/crc_358_msi/panel.yaml` | 声明 golden template pilot |
| 模板清单 | `panels/crc_358_msi/templates/README.md` | 说明模板文件不含患者数据 |
| 生成路径支持 | `reportgen/*`, `backend/*` | 支持按 panel template id 选择模板和 processor |
| 验收文档 | `docs/crc358_golden_template_acceptance.md` | 第一阶段验收方法 |

## 10. 技术实现要求

### 10.1 Panel template id 解析

Web 和 CLI 传入 `template_name` 时，应支持两种形式：

1. 文件名：`aligned_template_with_cnv_fusion_hla_FIXED.docx`
2. panel template id：`crc_358_msi_golden_template_v0`

如果传入的是 panel template id，系统应通过 `PanelPackage.resolve_template_file(template_id)` 解析，不再默认拼接 `templates/`。

### 10.2 Template-level processors

`panel.yaml` 允许模板声明自己的 `processors`：

```yaml
templates:
  - id: crc_358_msi_golden_template_v0
    file: panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx
    status: pilot
    processors:
      - blank_page_cleanup
      - toc_refresh
      - final_refresh_cleanup
```

如果模板未声明 `processors`，沿用 panel 级 processor 链。

### 10.3 Golden template seed builder

构建工具必须：

1. 接收本地正确报告路径。
2. 输出到 `tmp/golden_template_seed/` 或指定路径。
3. 替换患者级 token 为占位符或空值。
4. 检查敏感 token 残留。
5. 输出 `manifest.json`，记录输入 hash、输出 hash、替换项、残留检查。
6. 默认不把生成模板写入可提交目录，除非显式传入 `--allow-commit-output`。

### 10.4 质量门禁

迁移后必须跑：

1. Panel package validation。
2. Template contract validation。
3. reviewed CRC358+MSI 样本生成。
4. reference diff。
5. PDF/PNG 渲染检查。
6. 患者数据残留扫描。

## 11. 里程碑

| 里程碑 | 内容 | 通过标准 |
|---|---|---|
| M0 | PRD + 干净分支 | 基于 `origin/main`，无旧分支脏改动 |
| M1 | 模板选择和 processor 分层 | 可通过 `template_name=crc_358_msi_golden_template_v0` 解析模板 |
| M2 | Golden seed builder | 能从本地正确报告生成清洗种子并输出 manifest |
| M3 | CRC358 context diff | 生成 `report_context` 并定位 TMB/2.2/NCCN/免疫差异 |
| M4 | Golden template 变量化 | 标量字段和核心表格完成模板化 |
| M5 | 视觉验收 | 生成 PDF 无异常空白页，前 6 页接近正确报告 |
| M6 | 灰度接入 Web | Web 可选择 legacy/golden 两条路径 |
| M7 | 多样本回归 | 至少 3 个样本通过核心 QA |

## 12. 验收标准

第一阶段 PR 不要求 golden template 全量替代生产模板，但必须满足：

1. 新分支不污染当前旧分支工作区。
2. PRD、模板清单和验收文档完整。
3. panel template id 可解析。
4. template-level processors 可生效。
5. seed builder 可运行并能阻断患者数据残留。
6. 旧模板生成路径不回退。
7. 测试覆盖模板解析和 seed builder 基本行为。

正式切换生产前必须满足：

1. reviewed CRC358+MSI 样本与正确报告的强 diff 通过。
2. 两个额外 CRC358+MSI 样本通过核心 QA。
3. Web 端灰度生成与下载正常。
4. 无患者数据、批注、修订痕迹进入仓库模板。

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Word run 拆分导致变量失效 | 渲染失败或变量残留 | 使用 docxtpl 变量检查和模板契约 |
| 表格循环破坏分页 | 出现空白页/跨页错乱 | 样式行克隆，视觉 diff gate |
| 正确报告含患者数据 | 数据泄露 | seed builder 残留扫描，禁止提交原始报告 |
| 规则和模板重复判断 | 后期维护困难 | 复杂逻辑只在 Python/YAML |
| 新路径影响旧生产 | 生产回退风险 | golden template 使用 `pilot` 状态和显式选择 |

## 14. 决策

采用“同仓库、新分支、新生成路径、灰度接入”的方式推进。当前分支为：

`codex/golden-template-pilot`

本 PRD 是该分支的执行依据。第一阶段以基础设施迁移为主，不直接提交含患者级内容的 golden source。
