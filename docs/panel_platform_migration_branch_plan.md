# Panel Platform 迁移分支计划

日期：2026-05-17
当前基线分支：`codex/panel-platform-m1-baseline`
PRD：`docs/prd_multi_panel_template_architecture.md`
后续重构实施 PRD：`docs/prd_refactor_implementation_m6_m9.md`

## 分支树

```text
codex/report-v15-fixes
  └── codex/panel-platform-m1-baseline
        ├── codex/panel-platform-m1-qa-report
        ├── codex/panel-platform-m1-field-provenance
        ├── codex/panel-platform-m1-processors
        └── codex/panel-platform-m1-golden-case
              └── codex/panel-platform-m2-package-loader
                    ├── codex/panel-platform-m2-panel-registry
                    ├── codex/panel-platform-m2-template-contract
                    └── codex/panel-platform-m2-crc-migration
```

## 迁移原则

1. 先保护现有 CRC 358/301 产出，再做抽象。
2. 新 pipeline 初期必须兼容现有 `ReportGenerator.generate()` 和 Web API 调用方式。
3. 每个阶段都必须保留可运行测试和可生成报告的状态。
4. 不在 M1 阶段强行重写医学规则，只包装、观测和验收现有逻辑。
5. 不把真实患者数据提交到 Git；golden case 必须脱敏或使用合成数据。

## M1 Baseline

分支：`codex/panel-platform-m1-baseline`

目标：冻结当前 CRC 修复成果，作为后续迁移的稳定基线。

范围：

- 保留当前 CRC 修复。
- 确认本地测试通过。
- 生成一份当前可接受的 CRC 样例报告。
- 记录当前已知风险和不可回归清单。

验收：

- `backend/tests/test_report_regression.py` 通过。
- CRC 样例报告无空项目符号、无错误 4 列变异表、关键字段不为空。
- 明确哪些文件属于 baseline 修复，哪些是历史脏改动。

## M1 QA Report

分支：`codex/panel-platform-m1-qa-report`

目标：每次生成报告时同步输出机器可读 QA 报告。

范围：

- 增加 `generation_id`。
- 输出 `qa_report.json`。
- 检查未替换占位符、空项目符号、关键表格列数、目录页码、空白页。
- 检查关键业务结果：项目类型、TMB/MSI、变异计数、药物计数。

验收：

- 正常报告 QA 为 `PASS` 或 `WARN`。
- 人为制造缺字段/缺模板变量时 QA 为 `FAIL`。
- Web/CLI 能拿到 QA 报告路径。

## M1 Field Provenance

分支：`codex/panel-platform-m1-field-provenance`

目标：记录关键字段最终值和来源。

范围：

- 统一字段来源优先级：表单 > Excel > 患者库 > 文件名 > 规则计算 > 默认值。
- 输出 `field_provenance.json`。
- 对姓名、样本号、病理号等隐私字段默认脱敏。
- 在 QA 报告中引用关键字段来源。

验收：

- 能解释 `sample_id`、`patient_name`、`project_type`、`report_date`、`tmb_value`、`msi_status` 来源。
- 表单覆盖 Excel 的行为可见。
- Excel 覆盖默认值的行为可见。

## M1 Processors

分支：`codex/panel-platform-m1-processors`

目标：把当前渲染后处理逻辑包装成可组合 Processor。

范围：

- 新增 Processor 基类和执行器。
- 先包装现有函数，不重写内部逻辑。
- 优先抽出：
  - `BulletListProcessor`
  - `VariantTableProcessor`
  - `BiomarkerTableProcessor`
  - `TocProcessor`
  - `BlankPageCleanupProcessor`

验收：

- Processor 执行顺序可配置。
- Processor 幂等测试通过。
- CRC 样例报告输出与 baseline 关键结构一致。

## M1 Golden Case

分支：`codex/panel-platform-m1-golden-case`

目标：建立 CRC 358 + MSI 的端到端回归样例。

范围：

- 使用脱敏或合成样例。
- 固化 expected text / table / style / QA assertions。
- 增加 CLI：
  - `reportgen qa run --panel crc_358_msi`

验收：

- 一键运行 golden case。
- 任一关键表格结构、关键文案、空项目符号、未替换占位符错误都能失败。

## M2 Package Loader

分支：`codex/panel-platform-m2-package-loader`

目标：引入 `panels/` 目录和 Panel Package 加载能力。

范围：

- 定义 `panel.yaml` schema。
- 支持加载 panel metadata、模板、规则、processors。
- 保持旧配置可用。

验收：

- CRC 仍可从旧配置生成。
- 新 loader 可读取 `panels/crc_358_msi/panel.yaml`。

## M2 Panel Registry

分支：`codex/panel-platform-m2-panel-registry`

目标：替换散落的项目类型/增强器注册逻辑。

范围：

- 新增 Panel registry。
- 管理 panel aliases。
- 未注册 Panel 默认阻断，不静默走 Noop。

验收：

- `crc_358` 正确归一化为 `crc_358_msi`。
- 未注册项目生成时返回可解释错误。

## M2 Template Contract

分支：`codex/panel-platform-m2-template-contract`

目标：把模板变量和表格结构纳入契约校验。

范围：

- 解析模板变量。
- 校验必需变量、必需循环表、表格列数和关键表头。
- 输出 contract validation 结果到 QA。

验收：

- 删除关键模板变量时生成前失败。
- 修改 2.1 变异表列数时生成前或 QA 阶段失败。

## M2 CRC Migration

分支：`codex/panel-platform-m2-crc-migration`

目标：把 CRC 358/301 迁移为第一个正式 Panel Package。

范围：

- `panels/crc_358_msi/`
- `panels/crc_301_msi/`
- 复用现有 CRC enhancer 和 processors。
- 迁移 CRC 相关规则配置。

验收：

- CRC 358 golden case 通过。
- CRC 301 基础生成通过。
- Web 端仍可生成当前报告。

## 合并顺序

建议顺序：

1. `m1-baseline`
2. `m1-qa-report`
3. `m1-field-provenance`
4. `m1-processors`
5. `m1-golden-case`
6. `m2-package-loader`
7. `m2-panel-registry`
8. `m2-template-contract`
9. `m2-crc-migration`

每次合并前必须跑：

```bash
.venv/bin/python -m pytest backend/tests/test_report_regression.py -q
```

进入 M2 后还必须跑：

```bash
reportgen qa run --panel crc_358_msi
```
