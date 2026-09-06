---
module: lung-small-panel-derived-inputs
agent: codex
identity_kind: git_commit
identity_value: fa17b1ab2413cb1c65a5c5268176f49961051163
audit_date: 2026-09-06
---

# 肺癌小 Panel 派生输入与 draft 建包记录

结论：**四个 draft 包已构建并提交；工程验收未完成，未部署。**

原两项规格冲突已经用户明确裁决：C 例为四条变异/三条靶向提示；62 和 588 都按
NGS 家族识别、默认无 PD-L1，再由订单/网页同族选择消歧。不存在排除 PIK3CA 或
新增实验室不会输出的 PD-L1 旗标。新增无 PD-L1 的 588 draft 是本轮追加范围。
C13 的旧候选实稿已独立核对四条变异、三条靶向；完整排版仍未通过，详见 5.2。
下述机器测试不等于完整排版或报告组医学复核已通过。

## 1. 需求与冻结身份

- 需求权威：用户 2026-09-06 本轮规格；沿用模板族总规格，增加“真实肺癌超集派生
  输入可用于 draft 工程验证”的明确授权，不把派生输入登记为历史同案真实小 Panel 输入。
- 本轮修复源码冻结：`fa17b1ab2413cb1c65a5c5268176f49961051163`，分支为
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
| lung_13_historical_draft_v1 | `774a81c1d3221e5f4116389dbf703ec1919004d38705c2828fa4453e534b90d4` |
| lung_62_historical_draft_v1 | `891146fb0799d138c054518ac16c7c90f2e077c71e2849d54875467b9c6adffd` |
| lung_62_pdl1_historical_draft_v1 | `a05b1ae51db36b33ccda853a4703fcc1610acb40f8e6f6400d11582f21ed2907` |
| lung_588_historical_draft_v1 | `add46f103919b3a83d31b60eecf9f282bc60d55efb4be81821ebf979213a4c55` |

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
主变异表沿用肺癌Ⅰ/Ⅱ/Ⅲ类口径，Ⅲ类不展示药物提示；没有把数字旗标 1 当Ⅰ类。
早期验收脚本将主表误限于Ⅰ/Ⅱ类，已依据现有 mapper 和 A62 实际五条上下文行纠正；
未通过删除 ESR1/FLT3 Ⅲ类变异迎合错误验收预期。

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
| C 例四行/三靶向修正规格 | 6749292 真实 Word 表格 PASS；当前版待回放 | 独立 python-docx 读取实稿四变异/三靶向，不以内部上下文替代表格 |
| 62 / 588 同族身份 | 开发 PASS | 同族默认/可信订单/跨族阻断；前端 3 项测试包含 0 值 |
| seed → variableize → 三小包及 588 无 PD-L1 | BUILT | 四包均 draft，可加载，源模板样式基线四项通过 |
| scan_hardcoded_literals | PASS，4/4 模板 | 合并四母版 6 个私有身份 token 交叉扫描零命中；硬性文字零命中；不等于病例泄漏/视觉门禁已过 |
| two_case_leak_test | NOT_RUN | 已有两份失败候选实稿；尚未完成各包 A/B/C 跨病例门禁 |
| render_blank_page_check / 全页无孤行 | 6749292 整本 QA FAIL；修复待回放 | C13 30 页，26/27 页空白或低内容；A62 27 页；未声称历史页数量级已达成 |
| 新产品 QA gate / 网页批量 3×3 | 未通过 / 待运行 | 新合成 golden runner 已接入，不能以默认 CRC gate 替代新四包门禁 |
| 前端 / 发布范围保护 | 开发 PASS | lint、类型检查、build、3 个前端测试；发布范围 48 passed / 2 skipped；跳过项为既有可选环境测试 |
| 冻结完整 CI | 6749292 全量 PASS；最新修复待复测 | Actions 34013341880/job 101432818311；4387fe8 四包合成 gate FAIL，见 5.3 |
| 历史同案逐字对照 | AUTHORIZED_DEFERRED | 用户明确留待真配对输入，不伪称派生稿为同案验收 |
| 新版本部署后三源一致 | NOT_RUN | 本任务仍在工作分支；main=295ebd2，生产最后核验=da8e62d，不能报同步完成 |

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

3961ce0 的 C13/A62 进入严格模板契约后再次失败，尚未渲染：可选质控签核/病史等
字段未接入，且模板未引用声明要求的 total_variants_count。C13 的实际上下文已为
四变异/三靶向；A62 为五变异（含两条Ⅲ类）。TMB/MSI/PGx 对照均无差异。
后续开发增加包内可选源字段映射：有值按来源展示、缺失明确“未提供”，不得由 Q30/
深度推断质控合格；新增总数位置、修正 collection_date 字段名，模板契约仍为 fail。
该轮轻量专项 96 passed（10.88 秒），包括缺失/有来源质控与Ⅲ类回归。

c608430 全量 CI 实际为 **2 failed / 943 passed / 2 skipped**（1189.71 秒）；两项
失败均为产品清单断言尚未列入新增四 draft，不是通过。后续补齐显式清单并断言新包
仍为 draft/NOT_PRODUCTION_ACTIVE；必须由新提交全量 CI 重新证明通过。

### 5.2 首轮实稿及后续版式修复（6749292 → 411faf1）

6749292 的 C13、A62 均在 iyun129 完成 Word 和全页渲染。C13 最终变异表四行、
靶向表三行；A62 五条主表事件包含 ESR1/FLT3 两条Ⅲ类，不删行。两例 TMB/MSI/
化疗汇总/方案/剂量上下文与同例 588 比较无差异，但**原始 QA 均 FAIL**。

- C13 Word SHA：`de60bded05e19ef916e7e37b152dbc92382b5ab814f56889107a3e072693d9d5`。
  30 页；第 26 页正文空白，第 27 页仅短基因表，已查看真实 PNG。简易空白检测的
  PASS 不能覆盖更强全页 QA 的 LOW_CONTENT 错误。源基因列表/QC 周边的重复分页
  已定点清理，未放宽低内容阈值，也未以填充文字凑历史页数。
- A62 Word SHA：`2c4a3ca778762099216bf24fe564c42587e1bad01d7d461ae6cb3b38d51356bd`。
  27 页；新模板漏展示 CNV 待复核提示，现已补条件显示，保持 #13 医学边界。
- C13 原生 TOC 位于 SDT 内容控件，实际已有缓存页码，旧 QA 漏读。新增 XML 检查
  要求每条目录均有独立页码且目标书签闭合；数字标题、单条缺页码、坏书签均不能 PASS。
- 四包曾只接化疗汇总，现补入 588 维护的 30 组逐药来源表和剂量表，空药物集合
  不生成标题空表。新增最终 Word 指南逐行、完整检测基因集合和每条 PGx 六字段校验；
  588 对照也扩大到全部逐药集合。变异/靶向四行三行仍不变。
- 跨癌种扫描按各历史族的真实动态章节边界读取，不再误扫描固定附录；动态章节内
  命中仍报警，起始标题缺失仍回退全文检查。医学待审 WARN 没有被改成 PASS，已向
  用户澄清工程 PASS 与原始 QA 全零警示的验收区别，未获得答复前保持严格判定。
- 开发验证：原生目录/章节测试 13 passed；小包/输入保真/章节合计 113 passed；
  最终 Word 范围断言及完整源样式矩阵 31 passed。四包源基线仅更新有意模板改动，
  其余基线保持；六个私有源身份 token 对四包交叉扫描均零硬命中。新增四产品合成
  golden runner 可执行，但尚未跑完服务器全页 gate；合成 fixture 不算真实临床记录。

本节修复已形成新源码身份；6749292 的旧 FAIL 不被回溯改为通过。

### 5.3 合成全页反馈与章节保留修复（4387fe8 → fa17b1a）

4387fe8 新增四包独立 Linux golden CI（Actions 34014423779，最多并行两包）；
四包均生成 Word/PNG，但四个 QA gate 均 FAIL。下载的是公开合成 fixture 产物，
不上传真实 Excel、母版或 IHC。13/62/62+PD-L1 实稿缺少 CNV 提示；588 提示已在，
但原始 QA WARN。62+PD-L1 保留历史固定目录页码，588 只有空目录标题。

- 实际内容丢失原因：参考文献清理边界只认旧 CRC 的第四部分附录，没有认出
  小包的第三部分/编号附录和新增补充检测章节，误将其正文作为旧参考文献删除。
  修复终止边界；三个独立合成 DOCX 回归确认后续 CNV 文案、固定附录和 PGx 表
  不被删，旧参考文献仍按规则清理。不是把必需提示检查改成可选。
- 62+PD-L1 静态 TOC 和 588 空目录改为原生可刷新目录，按存活正文标题建立级别，
  保留前置分节；页码由真实 LibreOffice 更新，不伪造缓存。13/62 已有原生目录不改。
- 当前输出检查允许包内显式声明真实章节标题别名；无别名的 CRC 保持原默认，
  空/畸形别名不能绕过检查。统计文字同时识别“本次检出”和“本次共检出”。
- 四个新合成 fixture 增加标记明确的完整中性 Cnv 观测及一条合成 PGx 明细，
  检查明细结果真正进入 Word；已有 CRC/329/588+PD-L1 fixture 默认不变。
  该正向合成样本不能证明真实 CNV 阴性；真实输入、#13 缺失/不确定性单测和
  原始 QA 严格要求均未更改，绝不向真实派生 Excel 填入这些合成值。
- 新四包 CI 显式开启生成器整本视觉 QA，而不仅是另行生成 PNG 文件；保持空白/
  低内容失败门槛。没有将医学 WARN 清零，也没有提升 draft 开放状态。
- fa17b1a 提交前轻量回归 **176 passed / 17.36 秒**，源模板两项有意目录基线
  更新；新 PGx/目录/清理子集 51 passed，既有参考文献保护 5 passed。
  六个私有源身份 token × 四包交叉扫描：硬命中 0、ZIP 身份命中 0。
  bdd7eaa 冻结轻量回归另为 134 passed；两组回执不得混称同一源码验证。

服务器最后已验证的源码仍为 frozen_6749292；GitHub HTTPS 拉取超时，Tailscale
中继在线但 SSH 大文件传输多次超时。已准备可校验 Git bundle 作为私有链路备选；
部分传输件在完整 SHA 匹配前不导入。B/C IHC 记录及图片传输结束，但服务器端
图片 SHA 尚未重新核验，不能据此宣称 PD-L1 端到端完成。未改服务器网络/生产服务。

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
- `build_optional_fields/<panel>/build_receipt.json`：补可选字段和总数位置后的开发模板；
  初始冻结模板 SHA 仍在旧 build 回执中。
- `build_layout_complete/<panel>/build_receipt.json`：411faf1 四模板 SHA；补全 PGx、
  CNV 提示及短附录分页。旧 `build_pgx_complete` 是中间候选，不作最终通过凭据。
- `layout_contract_units.xml`、`layout_word_scope_units.xml`：113 / 31 项开发验证回执。
- `build_reference_boundaries/lung_62_pdl1/build_receipt.json` 与
  `build_reference_boundaries_b_final/lung_588/build_receipt.json`：当前两个原生目录模板；
  中间建包失败回执不覆盖、不算通过。
- `reference_toc_full_lightweight.xml`、`reference_toc_pgx_units.xml`、
  `reference_legacy_guard.xml`：176 / 51 / 5 项回归；`cross_scan_reference_toc.json`
  仅记录 token 数、模板 SHA 与命中数，不记录病例身份。
- `ci_4387fe8/`：四包失败的公开合成 Word、PNG 与 QA，不能替代真实 A/B/C 门禁。
- `development_units_final.xml`、`release_scope_units.xml`：本次开发回归，不替代冻结服务器门禁。
- 服务器隔离目录为本轮 `reportgen-lung-small-drafts-20260906.HySk3P`，不是生产目录。
  `frozen_c608430` 为干净 Git 工作树；`verified_inputs` 内 A/B/C 三份完整 SHA 已匹配。
  `frozen_c608430/.work/validation_A13_initial` 保留首例失败；损坏传输文件不得使用。

下一步：由服务器拉取修复后的已提交源码并核 SHA，重跑 C13/A62 整本 QA，
再运行 A/B/C 全矩阵、三件套和网页批量。所有工程门禁通过后
才写入草稿开放回执、完成主线/历史发布门禁和精确部署；医学晋级仍为 false。
