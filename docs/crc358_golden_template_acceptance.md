# CRC358 Golden Template 试点验收清单

## 输入

- Panel: `crc_358_msi`
- Legacy template: `crc_358_msi_standard_v1`
- Golden pilot template id: `crc_358_msi_golden_template_v0`
- Golden source: 本地报告组正确报告，不提交仓库
- Test Excel: 本地 reviewed CRC358+MSI Excel，不提交仓库

## 迁移前置门槛

1. `scripts/build_golden_template_seed.py` 生成 scrubbed seed。
2. manifest 中 `success=true`。
3. `protected_token_residual_counts` 全部为 0。
4. 输出 DOCX 不包含 `word/comments*.xml`。
5. 输出 DOCX 不包含 `w:commentRangeStart`、`w:del`。
6. `scripts/variableize_golden_template.py` 能按结构化变量清单生成本地模板候选。
7. `2.1 variants_2_1`、`2.2 chemotherapy` 等大表必须通过 docxtpl 行循环渲染，
   不再保留正确报告中的静态患者样本行。
8. `2.3 nccn_results` 和 `3.3 immune_*_results` 必须来自列表型
   context，不再依赖静态表行或散字段逐格填充。

## 内容验收

渲染 Word 前必须先通过 context contract。该门槛只检查结构化数据，不检查
排版，避免把错误数据带进模板层。

| 项目 | 期望 |
|---|---|
| 患者信息 | 姓名、性别、年龄、样本号、报告编号、诊断、日期均来自 clinical_info 或 patient_info |
| 计数 | 体细胞变异 8 个，药物相关变异 4 个 |
| 靶向表 | FBXW7 不进入药物相关变异表 |
| 2.1 表 | 与 reference 逐行比对核心字段 |
| 2.2 表 | 7 个药物行完整 |
| TMB | 汇总表和 3.1 正文一致，6.5/TMB-L/水平较低 |
| MSI | MSS 文案与 reference 一致 |
| NCCN | FGFR1/2/3 不误报 |
| 免疫表 | POLE/ALK 不误报，DDR 规则一致 |

## 视觉验收

1. 渲染 PDF 成功。
2. 不出现近空白异常页。
3. 前 6 页结构与正确报告一致或差异有明确说明。
4. 表格字体、字号、颜色、下划线、边框与 reference 接近。
5. 页眉页脚、水印、目录、末页信息完整。

## M4.2 表格循环验收

1. `targeted_drug_tips`、`variants_2_1`、`chemotherapy` 在模板中使用
   `{%tr for row in ... %}` 行循环。
2. 渲染后 DOCX 中不残留 `{%`、`%}`、`{{`、`}}`。
3. 2.1 表格行数来自 `context["variants_2_1"]`，2.2 表格行数来自
   `context["chemotherapy"]`。
4. 渲染为 PDF 后不出现像素级近空白页。

## M4.3 指南/免疫表循环验收

1. `nccn_results`、`immune_positive_results`、`immune_negative_results`、
   `immune_hyperprogression_results` 在模板中使用 `{%tr for row in ... %}`
   行循环。
2. context contract 检查 `nccn_results=32`、`immune_positive_results=15`、
   `immune_negative_results=12`、`immune_hyperprogression_results=8`。
3. contract 必须命中 KRAS 外显子 2、FGFR1/2/3 阴性、KRAS 免疫正相关、
   DDR/ATM、ALK 阴性等关键行。
4. 渲染后 DOCX 中不残留 `{%`、`%}`、`{{`、`}}`。
5. PDF 渲染后不出现像素级近空白页。

## M4.4 入包验收

1. `panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx`
   指向完整 scrubbed golden-template pilot，不再是 smoke shell。
2. 入包 DOCX 不包含真实姓名、样本号、报告编号、报告日期、批注或修订痕迹。
3. 计数字段必须保留为 `{{ total_variants_count }}` 和
   `{{ drug_related_count }}`，不得把 reviewed case 的 8/4 静态写死。
4. `docx_render.py` 在 macOS 上默认使用系统 LibreOffice profile，避免
   LibreOffice 25.x 初始化隔离 profile 时弹出崩溃报告；显式使用隔离 profile
   时仍需失败后 fallback 到系统 profile，并发出 warning。
5. 使用入包模板和 reviewed Excel 重新生成报告时，context contract 和视觉基础检查均通过。

## M4.5 Reference Diff Gate 验收

1. `scripts/diff_golden_report.py` 必须能用 reviewed Excel、正确报告和入包
   golden template 生成一份候选报告。
2. reviewed case 的患者/日期等表单字段必须通过 `--override KEY=VALUE`
   注入，不能写死在模板、规则或脚本源码中。
3. 脚本必须输出：
   - `diff.json`：机器可读差异。
   - `diff.md`：人工审阅清单。
   - `context.json`：本次渲染上下文。
   - reference/candidate 的 PDF 和 PNG 页图。
4. 以下差异必须被明确标出：页数、近空白页、关键标题页码、关键表格形状、
   关键文案片段、QA 状态。
5. 切换默认 golden template 前，`diff.json` 的最终状态必须达到 `PASS`；
   迁移过程中允许 `WARN`，但每条 warning 都必须有后续处理结论。

## 回归命令

```bash
python scripts/build_golden_template_seed.py /path/to/正确报告.docx \
  --replace "原姓名={{ patient_name }}" \
  --replace "原报告编号={{ report_number }}" \
  --replace "原样本号={{ sample_id }}" \
  --replace "原诊断={{ clinical_diagnosis }}" \
  --replace "原送检日期={{ receive_date }}" \
  --replace "原报告日期={{ report_date }}"
python scripts/variableize_golden_template.py tmp/golden_template_seed/crc_358_msi_golden_seed.docx --map panels/crc_358_msi/templates/golden_template_v0_variables.yaml --output tmp/golden_template_m4/crc_358_msi_golden_template_m4_3.docx
python scripts/check_report_context.py tmp/m4_3_context_probe/context.json panels/crc_358_msi/context_contracts/reviewed_low_tmb_mss.yaml --output tmp/m4_3_context_probe/context_contract_report.json
python scripts/diff_golden_report.py \
  --excel /path/to/reviewed.xlsx \
  --reference-docx /path/to/reference.docx \
  --override patient_name=... \
  --override sample_id=... \
  --override report_date=... \
  --allow-warn
python -m reportgen.cli validate --template panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx --show-vars
cd backend && pytest tests/ -v
```

## 切换门槛

Golden template 不得成为默认模板，直到：

1. reviewed CRC358+MSI 样本强 diff 通过。
2. 至少 2 个额外 CRC358+MSI 样本通过。
3. Web 端可选择 legacy/golden 并都能下载。
4. QA 报告和 reference diff gate 均无 FAIL。
