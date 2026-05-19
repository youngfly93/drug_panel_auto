# 自动化报告系统重构实施 PRD（M6-M9）

版本：v0.1
日期：2026-05-19
状态：Draft
适用分支树：`codex/panel-platform-m4-batch-diff-gate` 及其后续分支
前置文档：

- `docs/prd_multi_panel_template_architecture.md`
- `docs/panel_platform_migration_branch_plan.md`
- `docs/panel_package_spec.md`

## 1. 背景

当前分支树已经完成 M1-M5 的关键基础能力：

- QA 报告与字段来源追踪。
- Golden case 和 reference diff。
- Panel Package loader、registry、template contract。
- CRC 358/301 package 化。
- 第二个 Panel 试点：`lung_methylation`。
- Panel Package validator 和生成前 gate。
- Web 单报/批量链路可返回 QA、diff、panel validation 信息。
- Docker 部署已调整为自包含仓库部署，不再依赖 sibling upstream 目录。

这些能力已经能显著降低“错误报告静默生成”的风险，但核心生成链路仍然存在结构性问题：

- `ReportGenerator.generate()` 仍然承载过多阶段职责。
- CRC 医学规则、模板适配、后处理逻辑仍存在交叉耦合。
- `template_bridge_358.py` 和 `template_renderer.py` 中仍有不少面向特定模板结构的逻辑。
- 新 Panel 接入虽然有 package 入口，但规则执行、输入契约、样式验收还没有完全产品化。
- Web 已能展示部分 QA/diff 结果，但还没有形成完整生产复核工作台。

因此，后续重构不应是“推倒重写”，而应是“基于当前分支树的可验证迁移工程”。

## 2. 产品目标

### 2.1 总目标

在不破坏现有 CRC 358/301 报告产出的前提下，将系统从“单一报告生成脚本 + Web 包装”升级为“多 Panel、可验收、可部署、可审计的报告生产平台”。

### 2.2 核心效果

1. 新增 Panel 时，主要通过 `panels/<panel_id>/` 配置包完成，不修改主生成流程。
2. 每次生成都能明确经历哪些阶段、每个阶段 PASS/WARN/FAIL、失败原因是什么。
3. 业务规则、报告文案、表格展示、样式要求尽量迁移到 panel rules，而不是散落在 Python 分支判断中。
4. Word 后处理器变成可声明、可排序、可测试、可幂等验证的 pipeline。
5. Web 生产流程能让测试/生产人员看到输入契约、QA、diff、阻断原因和下载结果。
6. 任意重构阶段都必须保持 CRC golden case 和至少一个 Web 生成 smoke case 可运行。

## 3. 非目标

1. 不重写整个系统。
2. 不在 M6-M9 阶段替换 DOCX 模板体系为 HTML/PDF。
3. 不在本阶段建设完整 LIMS 或客户门户。
4. 不把所有医学知识自动化生成；医学口径仍需要人工审核后进入 rules/knowledge base。
5. 不把真实客户样本提交到 Git；所有 golden case 必须脱敏或合成。

## 4. 重构原则

1. 先包裹，再迁移，再删除旧路径。
2. 每一阶段都有可运行分支、可部署 Web、可回归报告。
3. 外部调用接口优先保持兼容：CLI、Web API、batch runner 不做破坏性变更。
4. 任何涉及报告正文、字段、表格、样式的改动必须有 golden/QA/diff 验收。
5. “不能确定正确性”的场景默认阻断或 WARN，不静默成功。
6. 配置化不是把复杂逻辑写进 YAML 字符串；只有稳定、可审核、可枚举的规则才迁移到配置。
7. 保留可追溯性：输出文件必须能追溯 panel id、package version、template version、规则版本和关键字段来源。

## 5. 目标架构

后续生成链路应拆为明确阶段：

```text
GenerationRequest
  -> PanelResolutionStage
  -> PanelPackageValidationStage
  -> ExcelReadStage
  -> InputContractValidationStage
  -> FieldResolutionStage
  -> PanelRuleExecutionStage
  -> TemplateContractStage
  -> TemplateRenderStage
  -> PostProcessorStage
  -> QAStage
  -> ReferenceDiffStage
  -> GenerationResult
```

每个阶段输出统一结构：

```text
StageResult
  name
  status: PASS | WARN | FAIL | SKIPPED
  started_at
  duration_ms
  issues[]
  artifacts{}
  metrics{}
```

最终 `GenerationResult` 必须包含：

- `success`
- `output_file`
- `stage_results`
- `panel_package_validation`
- `input_contract_validation`
- `template_contract`
- `field_provenance`
- `qa_report`
- `diff_summary`
- `errors`
- `warnings`

## 6. M6：生成核心 Pipeline 阶段化

### 6.1 目标

把当前 `ReportGenerator.generate()` 拆成可测试、可观测的阶段化 pipeline，但保持外部 API 兼容。

### 6.2 实施范围

新增建议模块：

```text
reportgen/core/pipeline/
  __init__.py
  context.py
  result.py
  runner.py
  stages.py
```

核心对象：

- `GenerationContext`
- `GenerationStage`
- `StageResult`
- `GenerationPipeline`
- `GenerationResult`

迁移顺序：

1. 提取 `GenerationContext`，承载 excel path、template path、output dir、project type、panel package、excel data、report data、artifacts。
2. 提取 `StageResult`，先只记录状态和错误，不改变业务逻辑。
3. 把现有 `generate()` 内部代码按阶段包裹为私有 stage 函数。
4. `ReportGenerator.generate()` 继续作为兼容 facade，内部调用 `GenerationPipeline.run()`。
5. 在返回结果中增加 `stage_results`，Web/CLI 先不强依赖，但可透传。
6. 对失败路径做统一处理：阶段 FAIL 后停止后续阶段，返回可解释错误。

### 6.3 验收标准

必须满足：

- `ReportGenerator.generate()` 参数和主要返回字段保持兼容。
- CRC 358 golden case PASS。
- CRC 301 基础生成 PASS。
- Lung methylation golden case PASS。
- 人为制造未知 panel 时，在 PanelResolution 或 PackageValidation 阶段 FAIL。
- 人为制造缺模板变量时，在 TemplateContract 阶段 FAIL。
- 人为制造空项目符号时，在 QA 阶段 FAIL。
- `stage_results` 至少包含阶段名、状态、耗时、issues。
- Web 单报成功/失败流程不退化。

建议命令：

```bash
python -m reportgen.cli panel validate --project-root . --fail-on warn
pytest backend/tests/test_report_regression.py -q -k "golden_case_passes or crc301_panel_package_basic_generation"
pytest backend/tests/test_report_regression.py -q -k "panel_package or template_contract or qa_report"
npm run build --prefix frontend
```

## 7. M7：Panel Rule Engine 与 CRC 规则迁移

### 7.1 目标

把 CRC 358/301 中稳定的报告口径从 Python 特定分支迁移到 panel rules，使后续新增 Panel 不需要复制 `template_bridge_358.py` 模式。

### 7.2 实施范围

新增建议模块：

```text
reportgen/rules/
  __init__.py
  engine.py
  schema.py
  loader.py
  evaluators.py
```

Panel rules 建议拆分：

```text
panels/crc_358_msi/rules/
  crc.yaml
  biomarkers.yaml
  variants.yaml
  drugs.yaml
  guideline_tables.yaml
  report_text.yaml
  style.yaml
```

优先迁移内容：

1. TMB/MSI 教育性固定文案。
2. 体细胞变异计数、药物相关变异计数规则。
3. 免疫正相关、负相关、超进展相关基因展示规则。
4. NCCN/CSCO 表格行定义。
5. 2.1/2.3/3.3 表格字段映射与展示列。
6. 固定药物商品名列表。
7. 表格字体、颜色、边框、对齐等 style token。

暂不迁移内容：

- 需要复杂医学判断或外部知识库查询的算法。
- 尚未稳定的客户定制排版逻辑。
- 与 DOCX XML 结构强耦合的底层修复函数。

### 7.3 验收标准

必须满足：

- 修改 TMB/MSI 文案只需要改 `report_text.yaml`，不改 Python。
- 修改 NCCN/CSCO 展示行只需要改 `guideline_tables.yaml`，不改 Python。
- 修改免疫药商品名列表只需要改 rules 或 knowledge base，不改 Python。
- CRC 358/301 golden case 均 PASS。
- 规则 schema 校验能发现缺字段、错误类型、重复 key。
- QA 报告能记录所用 rule file 和 rule version。
- 代码中不得新增面向具体患者姓名、样本号、日期的硬编码。

建议命令：

```bash
python -m reportgen.cli panel validate crc_358_msi --project-root .
python -m reportgen.cli qa run --panel crc_358_msi
python -m reportgen.cli qa run --panel crc_301_msi
pytest backend/tests/test_report_regression.py -q -k "crc358 or crc301 or rule"
```

## 8. M8：模板与后处理治理

### 8.1 目标

把当前 Word 后处理从“渲染器内大量私有函数”治理为可声明、可测试、可幂等验证的 processor pipeline，并将模板结构/样式纳入验收。

### 8.2 实施范围

新增/强化：

- Processor registry。
- Processor dependency/order validation。
- Processor idempotency test helper。
- Template style contract。
- Table style QA。
- Optional DOCX-to-PNG visual smoke check。

建议目录：

```text
reportgen/core/processors/
  registry.py
  contracts.py
  style_assertions.py
  visual_smoke.py
```

Panel package 中声明：

```yaml
processors:
  - name: empty_table_rows
  - name: bullet_lists
  - name: variant_tables
  - name: toc_refresh
  - name: underlines_and_styles

style_contract:
  tables:
    variant_summary:
      header_fill: "00B8C8"
      body_font: "宋体"
      body_color: "000000"
      allow_underlines: false
```

### 8.3 验收标准

必须满足：

- 每个 processor 有独立单元测试或集成测试。
- 每个 processor 对同一 DOCX 连续运行两次，第二次不产生结构性变化。
- `panel validate` 能发现未知 processor、重复 processor、依赖顺序错误。
- 2.1、2.3、3.3 关键表格具备字体/颜色/下划线/边框 QA。
- 模板关键表结构变化会导致 contract 或 QA FAIL。
- 目录页码、空白页、空项目符号、未替换占位符仍被 QA 捕获。

建议命令：

```bash
pytest backend/tests/test_report_regression.py -q -k "processor or style or qa_report"
python -m reportgen.cli qa run --panel crc_358_msi --render first --render-optional
```

## 9. M9：Web 生产工作台与部署闭环

### 9.1 目标

把 Web 从“上传生成工具”升级为“报告生产复核工作台”，让生产人员能看到生成全过程、阻断原因、QA/diff 结果和部署版本。

### 9.2 实施范围

后端：

- 任务记录新增 generation id、panel id、template id、package version、rule version。
- API 返回 `stage_results`、`input_contract_validation`、`panel_package_validation`、`qa_summary`、`diff_summary`。
- 批量任务支持按 QA/diff 状态筛选。
- Reference report diff 支持按 panel/template 选择基准。

前端：

- 报告生成页展示 Panel 校验状态。
- 任务详情页展示 stage timeline。
- QA issue 按严重程度聚合。
- Diff issue 展示阻断项、警告项和人工复核入口。
- 下载区域明确区分 DOCX、QA JSON、field provenance、diff report。

部署：

- 文档化 Docker 自包含部署。
- 文档化非 Docker 部署。
- 增加发布前检查命令。
- 增加回滚步骤。

### 9.3 验收标准

必须满足：

- 从干净服务器 clone 当前仓库后可执行 `docker compose up --build -d`。
- Web 登录、上传、生成、下载、查看 QA/diff 基本流程可用。
- 无效 panel package 时，Web 展示清晰阻断原因，不生成 DOCX。
- QA FAIL 时，任务状态或详情页能提示人工复核。
- 单报和批量报告均保留旧下载能力。
- 部署文档中包含环境变量、端口、存储目录、备份和回滚说明。

建议命令：

```bash
docker compose config
docker compose up --build -d
docker compose logs -f web
npm run build --prefix frontend
python -m reportgen.cli panel validate --project-root . --fail-on warn
```

## 10. 全局验收标准

M6-M9 完成后，整个分支树必须满足以下标准：

### 10.1 正确性

- CRC 358 + MSI golden case PASS。
- CRC 301 + MSI golden case 或基础生成 PASS。
- Lung methylation golden case PASS。
- LZ258792 回归样例相对当前最佳报告无 P0/P1 回退。
- 所有报告无未渲染占位符。
- 所有报告无空项目符号。
- 关键计数字段与表格行数一致。
- TMB/MSI 文案与 panel rules 一致。
- NCCN/CSCO 表格输出与 panel rules 一致。

### 10.2 可配置性

- 新增 Panel 的最小路径是新增 `panels/<panel_id>/`，不改 `ReportGenerator.generate()`。
- 新增模板版本只改 panel package，不改主流程。
- 固定报告文本、指南表行、药物展示列表能通过 rules 维护。
- `panel validate` 能作为上线前必跑 gate。

### 10.3 可观测性

- 每次生成有 `generation_id`。
- 每次生成有 `stage_results`。
- 每次生成有 `field_provenance`。
- 每次生成有 `qa_report`。
- 有 reference report 时自动生成 `diff_report`。
- Web 能查看关键失败原因。

### 10.4 可部署性

- 干净 clone 当前分支后能构建前端。
- 干净 clone 当前分支后能以 Docker 自包含方式启动 Web。
- 不依赖开发机上的 sibling upstream 目录。
- `storage/`、上传文件、生成报告、真实客户样本不进入 Git。

### 10.5 安全与合规

- golden case 使用合成或脱敏数据。
- QA、日志、diff 默认不暴露真实姓名、病理号、身份证等隐私字段。
- 默认管理员密码在生产部署文档中要求修改。
- 上传路径、下载路径继续保持 path traversal 防护。

## 11. 发布策略

建议继续采用分支树方式：

```text
codex/panel-platform-m4-batch-diff-gate
  └── codex/panel-platform-m6-pipeline
        └── codex/panel-platform-m7-rule-engine
              └── codex/panel-platform-m8-template-processors
                    └── codex/panel-platform-m9-web-production
```

每个阶段合并前必须：

1. 通过该阶段测试。
2. 生成至少一份 CRC 358 报告。
3. 运行 `panel validate`。
4. 更新对应文档。
5. 明确剩余风险和下一阶段任务。

不建议在 M6-M9 中途直接合并到 `main`，除非：

- Web 可以在测试服务器跑通。
- CRC 358/301 回归报告已人工确认。
- Draft PR 已完成 review。
- 生产回滚路径明确。

## 12. 风险与应对

### 风险 1：阶段化重构改变现有输出

应对：

- M6 只包裹阶段，不迁移医学规则。
- 每次改动跑 golden case 和 reference diff。
- 输出差异先标记为 WARN，人工确认后再调整 gate。

### 风险 2：规则配置化导致 YAML 复杂不可维护

应对：

- 只迁移稳定、可枚举、可审核规则。
- 规则 schema 必须有类型和必填校验。
- 复杂算法继续保留 Python evaluator，但由 rules 声明调用。

### 风险 3：后处理器顺序依赖导致版式回退

应对：

- Processor registry 明确 order/dependency。
- 每个 processor 增加 idempotency test。
- 关键表格引入 style contract。

### 风险 4：Web 展示过多技术细节，生产人员看不懂

应对：

- Web 层把 issue 聚合为“可继续 / 需复核 / 已阻断”。
- 技术详情折叠展示。
- 下载 QA JSON 给开发/测试人员使用。

### 风险 5：部署环境和开发环境不一致

应对：

- Docker 自包含部署作为标准路径。
- 服务器部署前必须跑 `docker compose config`。
- 对 `RG_WEB_UPSTREAM_ROOT`、`RG_WEB_STORAGE_ROOT` 做启动日志输出。

## 13. 退出条件

如果出现以下情况，应暂停继续大范围重构，转入缺陷修复：

- CRC 358 golden case 连续两个阶段无法恢复 PASS。
- Web 单报主流程不可用超过一个阶段。
- 新架构需要大量临时硬编码才能维持输出。
- 规则配置化导致测试无法解释报告差异。
- 部署无法在干净服务器复现。

## 14. 下一步建议

下一步进入 M6：

1. 新建分支：`codex/panel-platform-m6-pipeline`。
2. 新增 `reportgen/core/pipeline/` 基础对象。
3. 先包裹现有 `ReportGenerator.generate()`，不移动医学规则。
4. 返回结果新增 `stage_results`。
5. Web 暂时只透传，不做复杂 UI。
6. 跑 CRC/Lung golden case 和现有 QA 测试。

M6 的第一批任务应该小而稳定，不追求立即让代码变漂亮，优先让生成阶段可观测、可失败、可测试。
