# M1 Baseline 验收记录

日期：2026-05-17
分支：`codex/panel-platform-m1-baseline`
目标：冻结当前 CRC 358 + MSI 修复成果，作为多 Panel 迁移的稳定参照。

## 当前状态

当前阶段仍处于 M1 baseline，不做多 Panel 抽象，不改 Web 交互，不迁移配置目录。目标只是确认当前 CRC 报告修复链路可运行，并记录后续迁移不能破坏的关键行为。

## 本轮新增基线修复

- 新增空项目符号清理：删除模板残留的空 bullet / numbered 段落。
- 新增回归测试：空 numbered 段落必须被删除，普通空白段落不受影响。

## 测试结果

命令：

```bash
python3 -m py_compile reportgen/core/template_renderer.py reportgen/core/validation.py backend/tests/test_report_regression.py
.venv/bin/python -m pytest backend/tests/test_report_regression.py -q
```

结果：

```text
56 passed, 1 warning
```

warning 为现有 pytest 配置项 `asyncio_mode` 未识别，不影响本轮报告链路验证。

## 基线报告生成

使用本地 CRC 358 + MSI 测试 Excel 和当前主模板生成报告。测试输入和输出均位于本地工作区，不进入 Git。

输出目录：

```text
tmp/m1_baseline_crc358/
```

生成结果：

```text
success
duration: about 39s
project_type: crc_358_msi
template: templates/aligned_template_with_cnv_fusion_hla_FIXED.docx
```

## 机器检查结果

| 检查项 | 结果 |
| --- | --- |
| 未替换模板占位符 | 0 |
| 空项目符号段落 | 0 |
| 2.1 变异明细表 | 25 行 x 9 列 |
| 错误 4 列变异明细表 | 0 |
| MSI 结果解读 bullet | 4 条 |
| MSI 解读引用标号 | 已包含 `[1]`、`[1-3]`、`[4,5]` 等 |
| 体细胞变异计数 | 8 个 |
| 靶向药物相关变异计数 | 4 个 |
| 目录页码写回 | 已写回静态页码 |

## 当前不可回归清单

后续迁移分支不得破坏以下行为：

1. `crc_358` 必须归一化为 `crc_358_msi`，不能走 Noop enhancer。
2. 2.1 变异明细表必须保留 reviewed 9 列结构，不能压缩为错误 4 列。
3. 表格中基因/药物链接样式必须保留蓝色下划线，普通字段不得继承模板下划线。
4. TMB/MSI 教育性文案必须按正确报告口径输出。
5. MSI 结果解读多行内容必须拆为多个真实 bullet，不能出现空 bullet。
6. 报告中不得残留 `{{ ... }}` 或 `__PLACEHOLDER__`。
7. 目录必须有页码，不允许生成空页码目录。
8. 生成链路必须显式使用 CRC enhancer，不能静默降级。

## 工作区风险

当前工作区存在大量历史未提交变更和未跟踪文件，包括前端构建产物、本地样本、临时输出和 Word 文件。后续提交 baseline 时必须分批 staging：

1. 代码修复。
2. 回归测试。
3. PRD / 迁移文档。

不得 stage：

- `tmp/`
- `storage/`
- 真实 Excel / DOCX 样本
- Word 临时锁文件
- 无关 VPN 文档
- 未审查的前端 dist 删除/改动

## 下一步

建议下一步切到：

```bash
git switch codex/panel-platform-m1-qa-report
```

在该分支只做 QA 报告能力，不做字段来源、不做 Processor 拆分。这样可以先把当前人工检查项机器化，降低后续迁移风险。
