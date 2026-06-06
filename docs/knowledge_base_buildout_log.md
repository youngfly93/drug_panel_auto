# 知识库建设记录

## 2026-06-06：M0 历史报告 inventory

目标：按 `docs/prd_historical_report_knowledge_base_buildout.md` 的 M0 要求，对
`各癌种基因报告近年汇总/` 做去标识化 inventory，确认可用语料规模、癌种分布、产品族分布和
可解析状态。

工具：

```bash
python scripts/build_historical_report_inventory.py \
  --corpus 各癌种基因报告近年汇总 \
  --output tmp/knowledge_buildout/report_inventory_20260606.xlsx
```

结果：

| 指标 | 数量 |
|---|---:|
| 总文件 | 3157 |
| 有效 DOCX（排除 `._*`） | 1563 |
| 可解析 DOCX | 1563 |
| `._*` 资源文件 | 1586 |
| 旧 `.doc` 不支持解析 | 7 |
| 癌种目录 | 15 |
| 产品族 | 122 |

主力语料：

| 癌种目录 | 有效 DOCX |
|---|---:|
| 肠癌 | 603 |
| 肺癌 | 487 |
| 妇科肿瘤-子宫内膜癌 | 203 |
| 妇科肿瘤-卵巢癌 | 134 |

主力产品族：

| 产品族 | 有效 DOCX |
|---|---:|
| 结直肠癌301基因+msi | 264 |
| 肺癌13基因 | 240 |
| 子宫内膜癌分子分型29基因检测 | 201 |
| hrd评分及精准治疗检测 | 116 |
| 肺癌329基因+pd-l1 | 67 |
| 结直肠癌35基因+msi | 57 |
| 肺癌62基因+pd-l1 | 55 |

隐私检查：

- inventory 表不写真实患者姓名、样本号、完整文件名或报告原文。
- 逐报告索引仅保留 `source_id`、`content_hash`、癌种目录、产品族和解析状态。
- 针对样本号格式、`MLJY`、已知姓名样例做了扫描，命中 0。

结论：

1. 历史终版报告语料足够支撑知识库建设，报告组“完成度不足 5%”的判断在系统性入库口径下成立。
2. 下一步应优先做 M1：从肠癌 603 份报告中抽取 CRC 候选知识，先闭环当前生产压测剩余通用话术缺口。
3. 肺癌目录必须按产品族拆分，不能把肺13、肺62、肺329混成一个知识库来源。

## 2026-06-06：M1 CRC Part3 候选知识抽取

目标：按 PRD 的 M1 要求，先从肠癌 603 份历史终版报告中抽取 CRC Part3 候选内容，
服务当前 CRC358 压测剩余通用话术缺口。

输入：

- 压测 Excel：`肠癌358变异表.zip`
- 历史语料：`各癌种基因报告近年汇总/肠癌`
- 当前 reviewed overlay：`panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml`

工具：

```bash
python scripts/audit_crc_part3_knowledge_gaps.py \
  --input 肠癌358变异表.zip \
  --output tmp/knowledge_buildout/crc358_part3_gap_audit_20260606.xlsx \
  --project-root .

python scripts/harvest_crc_part3_candidates.py \
  --gap-xlsx tmp/knowledge_buildout/crc358_part3_gap_audit_20260606.xlsx \
  --corpus-dir 各癌种基因报告近年汇总/肠癌 \
  --output tmp/knowledge_buildout/crc_part3_candidates_m1_20260606.xlsx \
  --priorities P1,P2 \
  --max-gene-hits 12 \
  --max-exact-hits 8
```

缺口审计结果：

| 指标 | 数量 |
|---|---:|
| 压测 Excel | 14 |
| 纳入变异 | 133 |
| 位点级 reviewed 覆盖 | 10 |
| 基因级 reviewed 覆盖 | 105 |
| 基础库通用内容 | 18 |
| P1 缺口 | 4 |
| P2 缺口 | 14 |

候选抽取结果：

| 指标 | 数量 |
|---|---:|
| 待处理缺口 | 18 |
| 扫描肠癌终版 DOCX | 603 |
| 历史精确位点候选 | 0 |
| 去个案化基因级候选 | 69 |

候选覆盖基因：

- ERBB2
- KMT2A
- LRP1B
- ALK
- GNAS
- KMT2B
- CCND1
- FAT3
- PTPRS
- PDGFB

去标识处理：

- 候选表不写历史报告完整文件名、患者姓名、样本号。
- 来源仅保留 `source_id`、`content_hash`、产品族、基因数。
- 基因级候选过滤掉“该样本检出”“突变丰度”“拷贝数为”等个案句。
- M1 候选表隐私扫描命中 0。

产物：

| 文件 | 用途 |
|---|---|
| `tmp/knowledge_buildout/crc358_part3_gap_audit_20260606.xlsx` | 内部缺口审计；含当前压测样本编号，仅用于定位 |
| `tmp/knowledge_buildout/crc_part3_candidates_m1_20260606.xlsx` | 报告组审核候选表；已去标识，可优先给报告组审 |

下一步：

1. 报告组先审 `crc_part3_candidates_m1_20260606.xlsx` 的“需补库位点”和“历史基因级候选”。
2. 对 P1 的 ERBB2、KMT2A 优先标注“通过 / 修改后通过 / 不通过”。
3. 开发侧读取审核通过内容，进入 M2：生成正式 `reviewed_part3_knowledge.yaml` overlay 补丁和回归测试。

## 2026-06-06：M2 CRC 审核结果入库工具准备

目标：在报告组审核候选表之后，把“通过 / 修改后通过”的内容转成
`panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml` 可用的 overlay 草稿；
未审核、审核不通过、含个案信息的内容不得进入知识库。

工具：

```bash
python scripts/build_reviewed_part3_overlay_from_approvals.py \
  --review-xlsx tmp/knowledge_buildout/crc_part3_candidates_m1_20260606.xlsx \
  --existing-overlay panels/crc_358_msi/rules/reviewed_part3_knowledge.yaml \
  --output tmp/knowledge_buildout/crc_part3_overlay_draft_from_m1_20260606.yaml
```

本轮改动：

- 支持读取 M1 候选表的“历史精确位点候选”。
- 支持读取 M1 候选表的“历史基因级候选”。
- 只接受审核结论包含“通过”且不包含“不通过”的行。
- 基因级内容严格拒绝具体位点、丰度、拷贝数、样本号、日期和“该样本检出”等个案句。
- 位点级内容允许 c./p. 位点，但拒绝样本号、日期、突变丰度、拷贝数等个案信息。
- 输出 draft 不保留 `source_id`、`content_hash` 或历史报告文件名。
- 继续支持旧候选表入库，但同样增加安全过滤。

当前 dry run 结果：

| 指标 | 数量 |
|---|---:|
| 审核通过内容 | 0 |
| 通过的位点缺口行 | 0 |
| 通过的历史精确位点行 | 0 |
| 通过的历史基因级行 | 0 |
| 新增 overlay 条目 | 0 |
| 是否写入正式 overlay | 否 |

验证：

```bash
python -m py_compile scripts/build_reviewed_part3_overlay_from_approvals.py
python -m pytest \
  backend/tests/test_reviewed_part3_overlay_approvals.py \
  backend/tests/test_crc_part3_harvest_candidates.py \
  backend/tests/test_historical_report_inventory.py
```

结果：5 passed；仅保留既有 `asyncio_mode` pytest 配置提示。

下一步：

1. 报告组在 `crc_part3_candidates_m1_20260606.xlsx` 中标注审核结论。
2. 开发侧重新运行本脚本，先生成 draft YAML 人工复核。
3. 确认无误后再加 `--apply` 写入正式 overlay，并重跑 CRC 压测覆盖率。
