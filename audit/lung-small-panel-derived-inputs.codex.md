---
module: lung-small-panel-derived-inputs
agent: codex
identity_kind: git_commit
identity_value: c608430ef6f291eac3857e41907f1767be210858
audit_date: 2026-09-06
---

# 肺癌小 Panel 派生输入与 draft 建包记录

结论：**四个 draft 包已构建并提交；工程验收未完成，未部署。**

原两项规格冲突已经用户明确裁决：C 例为四条变异/三条靶向提示；62 和 588 都按
NGS 家族识别、默认无 PD-L1，再由订单/网页同族选择消歧。不存在排除 PIK3CA 或
新增实验室不会输出的 PD-L1 旗标。新增无 PD-L1 的 588 draft 是本轮追加范围。
下述机器测试不等于真实 Word 表格、完整排版或报告组医学复核已通过。

## 1. 需求与冻结身份

- 需求权威：用户 2026-09-06 本轮规格；沿用模板族总规格，增加“真实肺癌超集派生
  输入可用于 draft 工程验证”的明确授权，不把派生输入登记为历史同案真实小 Panel 输入。
- 源码冻结：`c608430ef6f291eac3857e41907f1767be210858`，已推送分支
  `codex/lung-small-panel-derived-drafts-20260906`。正文分别标注开发测试和冻结后验证，
  不将开发回执误报为已完成的冻结全量回放；
  用户原有 13 份未跟踪审计及专用 stash 保留，不属于本次源码 subject。
- 旧 PR #50 已合并 #13，也包含 #14/#15 修改；依新要求在服务切换前停止旧发布。
  本分支前向恢复 #14/#15 历史默认展示，候选严格策略仍有显式单测。
  [报告组待决清单](../docs/analysis-decisions/lung-chemotherapy-pending-review.md) 不代表医学批准。
- 新四产品维持 `draft_generation_eligible=false`、`production_eligible=false`，三端禁用
  范围也包含新增 `lung_588`。后续仅凭真实工程门禁、源码/模板 SHA 与明确用户授权
  可开放报告组草稿，不能凭此提升 `active` 或医学批准。不放宽历史差异指纹。

## 2. 母版来源（只记 SHA，不提交病例 Word 或文件名）

487 台账 SHA256：`9fb8d9d69f9c9642162518bc96112693ff9592e90db74befc39ebb358b215b3a`。
台账行号以包含表头的文件物理行计。四份原文件复制到忽略目录，原件均未修改。

| 产品 | 母版选择 | 族 | 台账行 | 母版 SHA256 |
|---|---|---|---|---|
| lung_13 | 用户指定终版 | A，无 PD-L1 | 28 | `56330fa8d883136297048ac58b2475da1bf6639fbbe9eedf90c61a5f4030305c` |
| lung_62 | 台账首份 A 族 62 候选 | A，无 PD-L1 | 255 | `a90010acad8e33c0d963b89c055f534b8162c90b5bcff0aa990eef57edf55b3c` |
| lung_62_pdl1 | 台账首份 C 族 62+PD-L1 候选 | C，含 PD-L1 | 426 | `25bccdf88cd8694e4c1c1ecd0a3a1428eed40a945f2f3b08466567a821f975d3` |
| lung_588 | 台账首份 B 族 588 无 PD-L1 候选 | B，无 PD-L1 | 398 | `4f4314259d898dcbc95b5ccf64af6e05ad084ea7219970f4acf2f6cebc55d14d` |

62 基因集合从上述非 PD-L1 母版的第 10 张表（零基索引 9）抽取；PD-L1 母版
第 9 张表（索引 8）给出相同顺序的 62 个唯一符号。清单文件
`.work/lung-small-panel-derived-inputs/genes62.json` 的 SHA256 为
`fc24e6bf05d940fc62f420af7e9049aa19be8f6f8a4da079b9a940e41e3a82f0`。
母版已依次执行副本关系修复（588 一处）、`build_golden_template_seed`、
`variableize_golden_template`，再通过 `build_lung_draft_packages.py` 安装结构化表格和规则。
原封面/样式/固定附录保留，病例段落改为动态块，清除源签名与 PD-L1 病例图片。
尚未通过新产品历史同案对照或报告组批准。

| draft 模板 | SHA256 |
|---|---|
| lung_13_historical_draft_v1 | `e066eb88e549aace6babdc1f19df206c059ae847336f6b6ba857e8ae85143a09` |
| lung_62_historical_draft_v1 | `e8cbb7ed1c768f2b99c1166befa0323bee3c05a387bb9b95a56d3b098e623d77` |
| lung_62_pdl1_historical_draft_v1 | `ce352a8cf7d444f7efbe57861a027b5b6f6ebbc0557b0714125e40ca672c5e2f` |
| lung_588_historical_draft_v1 | `02d151dbba0410e564beb1be22d2c76be86b28bd29c110f7715dd5b667ae9c3c` |

## 3. 派生规则与源表复算

实现：`scripts/derive_panel_input.py`。

1. 只重写 Variations / Hereditary_tumor 两个工作表的成员旗标列；删除旧产品列，
   在首个旧列位置写入新列。无旧列则追加。Gene_Symbol 经去首尾空白、转大写后
   在指定集合中即为数值 1，其他行保持空值；不把分级当作成员资格。
2. 其余工作表以及其他 ZIP 成员原样复制。原始分级、HGVS、数值、公式与 Cnv 的
   ExistIn137 不改。多旧列且含公式/Excel Table 时显式拒绝未经审核的结构移动。
3. 旗标可由 `--flag-column` 指定，默认 `ExistInsmall13` / `ExistInsmall62`；
   脚本支持从 `panel.yaml` 的 `derived_input` 读取产品配置。62 两包共用相同列，配置
   真源 `lung_draft_template_maps.yaml` 以同一 YAML 锚点维护。
4. 输出必须在 `.work/` 下，文件名带 `-derived-<panel>`，已有输出/回执拒绝覆盖。
   回执只记录哈希、列名、计数及规则边界，不记录病例身份或原始正文。

可执行示例（也可省略 `--genes`，直接读取包内产品集合）：

```bash
python scripts/derive_panel_input.py INPUT.xlsx --panel lung_13 \
  --genes "EGFR AKT1 ALK BRAF ERBB2 KRAS MAP2K1 MET NRAS PIK3CA RET ROS1 TP53" \
  --output-dir .work/derived_panel_inputs
```

三个原始输入 SHA 分别为：

| 脱敏病例 | 原始 SHA256 |
|---|---|
| A | `267a8cbab4d112ea38660dcb1734bb4fb3a7269f50abed6d83a9bf1262ee5646` |
| B | `623c96cee1eb7b16cacb62cababba3b790e82007a00a59d0f159efbe025db000` |
| C | `7b39431044c4a9298f7663c97a47c4df83b5b1e0875d88a64b3e24c05bfa498a` |

| 产品 | 病例 | Variations 标 1 行 | Hereditary_tumor 标 1 行 | 有效 HGVS 且Ⅰ/Ⅱ/Ⅲ类事件 |
|---|---|---:|---:|---:|
| 13 | A | 20 | 4 | 1 |
| 13 | B | 46 | 0 | 2 |
| 13 | C | 40 | 3 | 4 |
| 62 | A | 35 | 8 | 5 |
| 62 | B | 72 | 11 | 7 |
| 62 | C | 57 | 12 | 7 |

这些计数是源工作表复算，**不是已生成 Word 的表格行数**。六份输入的所有非旗标
单元格、原有分级及另十张表均一致，ZIP 仅两个 worksheet XML 改变。冻结提交后
再次派生六份并比较完整 XLSX SHA，全部与前次独立检查的产物一致。

## 4. 已裁决的历史发现与实现

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-small-panel-derived-inputs-01 | P1 | 原“三行”验收漏计产品内 PIK3CA；用户已修正为四行，业务未删该行 | 原始 Variations 第 39 行；`backend/tests/test_lung_small_panel_contract.py:test_thirteen_gene_context_keeps_four_variants_and_three_targeted_rows` | CONFIRMED |
| lung-small-panel-derived-inputs-02 | P1 | NGS 共同旗标不能确定 IHC 订单；用户已授权同族下拉/订单消歧 | `reportgen/core/project_detector.py:_resolve_structural_family`；`frontend/tests/projectIdentity.test.mjs` | CONFIRMED |

C 输入的有效分级事件位于第 2、15、32、39 行，分别为 BRAF V600E、ERBB2 G660D、
TP53 G245D、PIK3CA A1066V。其余成员旗标行包括未分级或知识注释行，因此“旗标
恰好四行”亦不等同于“最终变异表四行”。成员资格、有效 HGVS 和显式分级必须分别核对。
主变异表沿用肺癌Ⅰ/Ⅱ类口径，Ⅲ类保留于完整事件/解释上下文；没有把数字旗标 1 当Ⅰ类。

此前提出额外 PD-L1 旗标的方案已撤回。62 族共用 `ExistInsmall62`，588 族共用
`ExistInsmall588`；文件名不作为 IHC 证据。填写 PD-L1 结果或来源可自动切换同族
产品（0 为有效输入）；未填写则保持无 PD-L1。跨 NGS 家族覆盖继续阻断。
`legacy_unspecified_ihc_transcription_v1` 逐病例执行，批量不复制共享 PD-L1 字段。

小包按非突变注释、有效变异及产品集合做独立处理，Cnv/Fusion/Hotspot 只建立
产品内只读视图，原工作簿与 Cnv 数值/旗标不改；Fusion 覆盖真实小写 gene1/gene2 列。
修复了小包误继承旧 CRC “未见突变”基因表的问题，指南、免疫、未检出集合按产品裁剪。
588 知识候选的审核状态保持不变，不因复制到小包就启用未审核内容。

## 5. 门禁与方法保真

| 要求 | 当前结果 | 凭据/边界 |
|---|---|---|
| #13 保留、#14/#15 转待决 | 已实现于工作分支 | 默认历史回归 + 显式严格候选策略；不新增医学批准 |
| 派生脚本与保护性单测 | 开发 PASS | 旧 fdf3c10 冻结 108 passed；本次提交前 122 passed / 11.33 秒，见 development_units_final.xml |
| A/B/C × 13/62 派生保真 | PASS，6/6 | 独立原始→派生单元格比较 + 冻结提交完整 SHA 重放 |
| C 例四行/三靶向修正规格 | 源表及合成上下文 PASS，真实 Word 待验 | 不排除 PIK3CA；尚未以内部数据代替 Word 表格验收 |
| 62 / 588 同族身份 | 开发 PASS | 同族默认/可信订单/跨族阻断；前端 3 项测试包含 0 值 |
| seed → variableize → 三小包及 588 无 PD-L1 | BUILT | 四包均 draft，可加载，源模板样式基线四项通过 |
| scan_hardcoded_literals | PASS，4/4 模板 | 合并四母版 6 个私有身份 token 交叉扫描零命中；硬性文字零命中；不等于病例泄漏/视觉门禁已过 |
| two_case_leak_test | NOT_RUN | 无新产品 Word，不用已有 588 或 CRC 稿替代 |
| render_blank_page_check / 全页无孤行 | NOT_RUN | 无新产品 Word；未声称 42/44/56 页目标达成 |
| 新产品 QA gate / 网页批量 3×3 | 待运行 | SSH 大文件传输中断；未用旧 588/CRC 或静态表格代替网页验收 |
| 前端 / 发布范围保护 | 开发 PASS | lint、类型检查、build、3 个前端测试；发布范围 48 passed / 2 skipped；跳过项为既有可选环境测试 |
| 冻结完整 CI | RUNNING | GitHub Actions 34012314013，源码 c608430；不提前写 PASS |
| 历史同案逐字对照 | AUTHORIZED_DEFERRED | 用户明确留待真配对输入，不伪称派生稿为同案验收 |
| 新版本部署后三源一致 | NOT_RUN | 分支已推送 c608430；main=295ebd2，生产最后核验=da8e62d，不能报同步完成 |

旧失败证据保留：首轮派生脚本的 ZIP 元信息复用缺陷导致 5 failed / 103 passed；
修复后各轮独立回执记录通过，不把旧 FAIL 改成 PASS。后续格式检查与 `git diff --check`
均通过。本次首次小包上下文测试发现 CRC 未见突变基线继承缺陷（13 passed / 1 failed），
修复后新 14 项通过。一次误含生成的本地旧 588 完整合同测试进入重计算后被终止，
不计为完整成功；完整生成应在 iyun129 / CI 执行。旧 295ebd2 的通过不能挪用于此提交。

步骤地图：原始 Excel + 受控基因集合 → `derive_panel_input.py` → `.work/derived/`
→ 独立 openpyxl/ZIP 比较 → SHA 重放；历史 Word → 75 建包脚本 → 四个 panels draft
→ 76 逐例验收脚本 → `.work/` 的 Word/上下文/视觉/门禁回执。当前未重跑原始测序分析；
真实 Word、派生 Excel、临时脚本和日志均在 `.work/`，不进入 Git。共享审计核对器
仍报既有身份/覆盖缺口；没有宣称双 agent 同版联合批准。

### 5.1 首例服务器反馈（c608430）

服务器通过 Git HTTPS 拉取了干净的 c608430 工作树。A/B/C 原始输入已从本项目
既有私有 QA 目录恢复，三个完整 SHA 均与第 3 节匹配，未使用损坏的部分传输文件。
首例 A13 在 FieldResolutionStage 失败：新范围校验把每行字典中的空旗标键省略误认
为工作表缺列，未进入 Word 渲染。原始 FAIL 留存，不计为视觉或表格通过。

后续修复改用 ExcelReader 保留的表头判断列存在；没有表头元数据的调用用行键并集，
空单元格仍为非成员，真实缺列继续阻断。新增稀疏行和全空旗标回归，专项 18 passed
（3.42 秒，`sparse_flag_units.xml`）。验收脚本页数取值同时对齐 QA 的真实 metrics 字段。
上述是开发修复，须以新提交重跑服务器实稿，不能追溯改变 c608430 的失败结论。

## 6. 私有回执入口

目录：`.work/lung-small-panel-derived-inputs/`。

- `source_manifest.json`：母版原路径、台账行、原始/复制 SHA。
- `derivation_verification.json`：六份产物完整 SHA、所有非修改单元格检查、源表事件。
  SHA256：`9c668b3c89809a315d32f7e6c7fb24b338ca4f677e8d3892627d16c67f155827`。
- `frozen_replay.json`：冻结提交重放六份，完整产物哈希与上述回执逐份相同。
- `prerequisite_units_frozen.xml` / `.log`：冻结提交 108 passed；JUnit SHA256
  `3ee8ed17c0550f2eed51b03393f67c009d9346fd428e89495e0b2de26f587afe`。
- `initial_unit_failure.json`：首轮真实失败，不覆盖。
- `build/<panel>/build_receipt.json`：四母版、模板和来源规则 SHA；私有 token/中间种子也
  留在该目录，不能入库。
- `development_units_final.xml`、`release_scope_units.xml`：本次开发回归，不替代冻结服务器门禁。
- 服务器隔离目录为本轮 `reportgen-lung-small-drafts-20260906.HySk3P`，不是生产目录。
  `frozen_c608430` 为干净 Git 工作树；`verified_inputs` 内 A/B/C 三份完整 SHA 已匹配。
  `frozen_c608430/.work/validation_A13_initial` 保留首例失败；损坏传输文件不得使用。

下一步：由服务器拉取修复后的已提交源码并核 SHA，先完成 C13 的真实 Word
四行/三行快速反馈，再运行 A/B/C 全矩阵、三件套和网页批量。所有工程门禁通过后
才写入草稿开放回执、完成主线/历史发布门禁和精确部署；医学晋级仍为 false。
