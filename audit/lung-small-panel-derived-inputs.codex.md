---
module: lung-small-panel-derived-inputs
agent: codex
identity_kind: git_commit
identity_value: 1fbb2948410c75321530f93d6936498e07c9f3fd
audit_date: 2026-09-06
---

# 肺癌小 Panel 派生输入与 draft 建包记录

当前结论：用户已授权仅部署报告组 draft；六肺包已恢复原文 + WARN，临床资格不变。
本节之后的旧停止结论保留为历史记录，不再把医学 WARN、缺失 IHC 或 P2 排版待办
当作 draft 开放前置条件。新版冻结回放与发布进度见 5.15；尚未声称生产已切换。

原两项规格冲突已经用户明确裁决：C 例为四条变异/三条靶向提示；62 和 588 都按
NGS 家族识别、默认无 PD-L1，再由订单/网页同族选择消歧。不存在排除 PIK3CA 或
新增实验室不会输出的 PD-L1 旗标。新增无 PD-L1 的 588 draft 是本轮追加范围。
C13 的 f7aabde 实稿已独立核对四条变异、三条靶向，以及 13 基因/9 指南/73 PGx
明细，指南/逐药表边界已恢复；但人工发现空药物栏目页与变异行跨页/缩进问题。
845aaef 网页实测 13/62 各生成 3/3，但 QA 全部 FAIL，B13 更误用 CRC 默认模板。
37b77f7 实际网页九份均生成，C13 四行/三靶向和 38 项 588 parity 通过，但有缺少来源的
样本类型默认值、A62+PD-L1 两行注释孤页，以及九份各一张被默认 PDF 导出隐藏的自动
空白页。5883452 真实九份均生成，原始 QA 均 WARN，九份完整空白门禁和 12 项定向
泄漏检查通过；人工仍发现 B/C62 标题孤页及符号字体回退。前向修复已提交至
6462cd5，279/33/10 项开发保护通过；最新网页九份生成完成、原始 QA 全为 WARN
且无 FAIL。最终只读矩阵 9/9 空白门禁、12/12 定向泄漏及源表/Word 核对通过，
22 张全书总览已检查；仍有医学 WARN 和 P2 排版待办，不宣称终版放行，详见 5.14。
下述机器测试不等于完整排版或报告组医学复核已通过。

## 1. 需求与冻结身份

- 需求权威：用户 2026-09-06 本轮规格；沿用模板族总规格，增加“真实肺癌超集派生
  输入可用于 draft 工程验证”的明确授权，不把派生输入登记为历史同案真实小 Panel 输入。
- 本轮修复源码冻结：`6462cd5bfc34beafb7d6ec7cd1dffc61451c02c6`，分支为
  `codex/lung-small-panel-derived-drafts-20260906`。正文分别标注开发测试和冻结后验证，
  不将开发回执误报为已完成的冻结全量回放；
  用户原有 13 份未跟踪审计及专用 stash 保留，不属于本次源码 subject。
- 旧 PR #50 已合并 #13，也包含 #14/#15 修改；依新要求在服务切换前停止旧发布。
  本分支前向恢复 #14/#15 历史默认展示，候选严格策略仍有显式单测。
  [报告组待决清单](../docs/analysis-decisions/lung-chemotherapy-pending-review.md) 不代表医学批准。
- 初始建包阶段四产品均未开放；当前 draft 资格以 5.15 及已提交的 readiness 清单为准。
  用户已授权按真实工程回执、源码/模板 SHA 开放报告组草稿；`production_eligible`
  始终为 false，不能凭此提升 `active` 或医学批准。不放宽历史差异指纹。

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
| lung_13_historical_draft_v1 | `31a3f5a87744ed3902251b196cdf40960c4eb76cf3712ccd87d7bcd4b87afe1a` |
| lung_62_historical_draft_v1 | `dcaf902f13abdecca75d4f88cb0f508e8a56bde746f901e554454044706c61f9` |
| lung_62_pdl1_historical_draft_v1 | `94f3983af19e6afe6c9561f8eab8892334e0ef518e9d5be23ee7dc303b49cee8` |
| lung_588_historical_draft_v1 | `9a1485b677b10522e51fe32543141d69d0a39de90ec68d8264f43128ada8ef85` |

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
| lung-small-panel-derived-inputs-03 | P1 | 8c8aeb5 的 62+PD-L1 合成稿遗留母版“2 个变异/0 个靶向”段落，与实际 1/1 矛盾 | CI 34015224627 原 Word/第 6 页；5.4 动态统计及重复统计校验修复 | CONFIRMED |
| lung-small-panel-derived-inputs-04 | P1 | 同版 62+PD-L1/588 空目录未正确刷新，旧正文数字误参与目录检查 | 同 CI 第 5/7 页与 QA；5.4 原生终态刷新/必需域检查修复 | CONFIRMED |
| lung-small-panel-derived-inputs-05 | P2 | 原生排版后基本信息字段继承表头白字，浅底不可读 | 13/62+PD-L1 第 6 页、模板与输出颜色节点比对；5.4 显式黑字 | CONFIRMED |
| lung-small-panel-derived-inputs-06 | P1 | 83b22b0 的 588 同时出现旧浮动目录和新目录；旧页码最高 74，新目录混入病例单元格及空条目 | CI 34015953334、588 原 Word SHA 与第 5/6/8 页；5.5 定位及修复 | CONFIRMED |
| lung-small-panel-derived-inputs-07 | P2 | 同一 588 第 9 页仅余一句末行，第 27 页空白 | 同版本第 8/9/26/27/28 页人工检查与原始 QA LOW_CONTENT；5.5 清理标题前占位空段落 | CONFIRMED |
| lung-small-panel-derived-inputs-08 | P2 | 62+PD-L1 目录收录整段文献及局部文献小标题，页码门禁虽 PASS 仍不专业 | 83b22b0 原 Word SHA `5d3179a38e0fe0247f35de8ed7fc066197e1c447230b181587c26d8e6469bdaa` 第 5/6 页；5.6 修复及补门禁 | CONFIRMED |
| lung-small-panel-derived-inputs-09 | P2 | B 族旧目录装饰线穿过新文字，FAQ 第 7 问跨页后仅余 3 行孤页，附录 FAQ 编号承接为 3 | CI 34016832113 的 588 Word 第 5/23/24 页；1244f3d 定点修复，5.7 | CONFIRMED |
| lung-small-panel-derived-inputs-10 | P2 | 真实多药 PGx 与 C13 指南表被原生引擎合并；数据仍在，但标题/续页表头边界不正确 | 18514ad C13 Word XML 及独立回读；0b85b93 加持久标题分隔，5.8 | CONFIRMED |
| lung-small-panel-derived-inputs-11 | P2 | 验收脚本把 gridSpan 重复格当物理字段，误报 0 行；渲染 None→空文本被误报 588 数据变化 | 旧 C13 9/73 行逐字段均匹配、38 个 parity 键归一化后零差异；合并仍 FAIL，5.8 | CONFIRMED |
| lung-small-panel-derived-inputs-12 | P2 | f7aabde C13 第 8 页只有空药物表头，变异窄列继承正文首行缩进且事件行跨页 | 原 Word 第 6—8 页 PNG、OOXML firstLine=420；845aaef 显式空态/缩进/分页与新 QA，5.10 | CONFIRMED |
| lung-small-panel-derived-inputs-13 | P2 | 6462cd5 仍有页尾小标题/表头与次页正文分离；不是整张孤行页，但不能据机器空白 PASS 宣称终版排版完全合格 | `final_web_exports_6462cd5/lung_13_C_page_10.png`：PIK3CA 标题及“基因简介”在页尾；`page_overviews_6462cd5/lung_62_pdl1_B/overview_21_40.png`：第 26—27 页药物—基因表头与行分离；两者 SHA 见 artifact_checksums_6462cd5.json | CONFIRMED |

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
| C 例四行/三靶向修正规格 | 6462cd5 实际 Word PASS | 四变异/三靶向、13 检测基因/9 指南/73 PGx；38 项 588 parity 零差异 |
| 62 / 588 同族身份 | 开发 PASS；62 与 588 网页默认/自动切换 PASS | 同一族 Excel 默认无 IHC；真实 C 的 TPS 5/CPS 6 触发同族 +PD-L1；只测表单切换、未提交单份 Word，批量不复制 IHC |
| seed → variableize → 三小包及 588 无 PD-L1 | BUILT | 四包均 draft，可加载，源模板样式基线四项通过 |
| scan_hardcoded_literals | PASS，4/4 模板 | 合并四母版 6 个私有身份 token 交叉扫描零命中；硬性文字零命中；不等于病例泄漏/视觉门禁已过 |
| two_case_leak_test | 6462cd5 三包 12 个方向 PASS | 每包 C↔A、C↔B，病例别名/HGVS 专属 token 不泄漏、自身 token 存在；不扩大为全文医学核对 |
| render_blank_page_check / 全页无孤行 | 6462cd5 九份完整空白门禁 PASS；361 页总览已查 | 显式包含自动空白页；B/C62 原整张标题孤页已消除，页尾标题/表头仍有 P2 排版待办，不能宣称完全终版 |
| 新产品 QA gate / 网页批量 3×3 | 6462cd5 三批各 3/3；原始 QA 九份 WARN、零 FAIL | 独立 Word / 源表核对零失败；医学 WARN 未改成 PASS，strict_pass=false |
| 前端 / 发布范围保护 | 开发 PASS | lint、类型检查、build、3 个前端测试；发布范围 48 passed / 2 skipped；跳过项为既有可选环境测试 |
| 冻结完整 CI | 6462cd5 整条 SUCCESS | 34026187551：四 draft golden + 默认 qa-gate 全部成功；旧失败不覆盖 |
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

### 5.4 数字摘要与真实版式的第二轮反馈（8c8aeb5 → fb72cc3）

Actions 34015224627 的 13/62 合成 Word 原始 QA 均 PASS、整本 31/28 页，重复
生成比对 PASS；外层 current-output gate 失败是配置转换遗漏 `section_aliases`。
保留原 Word 重新读取，补传配置后两份 current-output 检查均 PASS；原 CI 的 FAIL
不改写。62+PD-L1 为 29 页、588 为 49 页，原始 QA 均 FAIL。

- 人工查看 62+PD-L1 第 4–8 页确认：第 5 页只有目录标题、第 7 页只有水印；
  第 6 页还残留历史“2/0”病例统计。旧目录检查把正文编号误算为目录页码，
  因而不能仅凭其 PASS 宣称目录正确。13 第 2/6/7/28 页也作了抽样查看，不等于
  真实病例整本人工审核；基本信息白字问题在 Word XML 中复现。
- 本轮将四族目录明确配置为 native，62+PD-L1/588 改用与可工作的 A 族一致的
  普通复杂 TOC 域表示（非数字“待刷新”缓存）；最终版式结束后再用原生引擎刷新。
  不再套用 CRC 四章节重建；缺失可刷新字段直接 FAIL，正文数字不能补足目录。
  该互操作修复仍须下一次 Linux 全页结果确认，不能凭源 XML 单测宣称完成。
- 所有病例摘要改为 total_variants_count / drug_related_count 动态字段，移除旧
  “未筛选到药物”病例结论。新增最终 Word 每一处数字摘要一致性检查，即使文档中
  已存在一处正确数字，也不能掩盖另一处旧数字。指南标题前冗余分页已定点清理；
  基本信息变量明确黑字，不改变检出/药物结果，也不修改 #14/#15 医学待决口径。
- 开发回归 **191 passed / 18.34 秒**；现有 CRC/目录/QA 保护 **33 passed / 7.57 秒**。
  前一次将 pytest 临时根放在 `.work/` 内，导致“拒绝非私有路径”的测试前提不成立
  （190 passed / 1 failed）；未改测试或放宽路径校验，换回无 `.work` 名称的任务
  临时根后全量通过。初始失败回执保留。
- 最新四源模板硬标识/跨母版 token 扫描全过，字面病例数字摘要零残留；样式基线
  仅更新上述四份有意变更。真实输入及派生 SHA 不改。
- 较早 bdd7eaa 全量 CI 34014128765 已 PASS；4387fe8 的默认 qa-gate 也 PASS，
  但其四个新包 gate FAIL。两者都不能作为 fb72cc3 的完整通过凭据。

14:00 前后的 SSH 短连接也超时，分片传输在建远端目录前终止，未组装/导入新源码。
公网 health 返回 `status=ok` 只证明现网存活，不证明版本一致。真实九例、Web UAT、
双病例泄漏与生产部署继续未完成；仍未收到医学 WARN 验收定义的答复，未放行。

### 5.5 588 浮动目录与继承大纲修复（94b478e）

CI **34015953334**（83b22b0，业务源码 fb72cc3）的四包结果已分开核对：

| 包 | 完整合成 golden gate | 原始 QA | 页数 | 原生目录页码 |
|---|---|---|---:|---|
| lung_13 | PASS | PASS | 31 | 11/11 |
| lung_62 | PASS | PASS | 27 | 10/10 |
| lung_62_pdl1 | PASS | PASS | 29 | 38/38 |
| lung_588 | FAIL | FAIL | 53 | 52/60，另有旧浮动目录 |

这三项 PASS 包含最终 Word、重复生成差异和 Linux 整本视觉门禁，但均为公开合成
输入，不替代 A/B/C 九例。该 run 默认 qa-gate 尚未完成时未登记为整条 CI PASS。
原始 588 Word SHA：`cc22bfd7d33ffa754be8c87c2493d7304411e7d00d011f3f8ca319291e53377e`。
逐页看图确认：第 5 页仍是带 74 等历史页码的浮动目录；第 6—8 页另起新目录并
错误收录姓名、样本字段、空标题和图示文献；第 9 页末行孤页、第 27 页空白。
旧 FAIL/PNG 均保留，不能由随后模板变化覆盖。

94b478e 的有界修复：

- 仅重建 588 源模板。识别并移除目录标题中的完整旧文本框目录及其 VML 回退，
  保留无文本装饰；只把真实正文中的对应标题纳入大纲，病例表格、空段落、图示
  文献不再误入目录；全局参考文献只用最后一处标题，不收录局部通路的文献小标题。
- 原目录标题携带的分节边界移至原生目录字段之后，避免新目录和基本信息混页；
  清理对应标题前连续无内容段落，把原显式换页语义留在标题上，标题与下文相连。
  没有补文字、造页码或放宽空白/低内容阈值。其他三个模板 SHA 未变。
- 原生目录 QA 新增浮动旧目录残留失败项；用原 83b22b0 四份 Word 只读重查，
  前三份仍 PASS，588 明确检出两个 OOXML 文本框缓存（显示/兼容两份）。
- 四个空单元格的 `numId=0` 实为取消编号，旧检查误认为可见空编号；按
  [Microsoft 的 OOXML NumberingId 定义](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.numberingid?view=openxml-3.0.1)
  修正判断，正整数编号和缺失编号 ID 的原阻断仍保留。未改生产排版清理器。
- 开发验证：180 项专项 **PASS / 17.41 秒**，17 项全模板源基线 **PASS / 3.60 秒**；
  33 项现有 CRC/目录/QA 保护 **PASS / 9.90 秒**。46/47 项中间专项回执保留；
  最初文本框回归暴露冒号规范化匹配问题（1 failed），已修正后再跑全套。
  四模板跨母版 6 个私有 token 扫描硬命中/ZIP 命中均 0。仅更新 588 有意变更基线。
- 发布脚本声明的三层禁用范围校验 PASS（0 issues）。不传范围的诊断命令按设计
  FAIL，回执另存；不能将默认空参数误报为实际生产配置变化。

14:30 SSH 只读时间探针恢复；服务器 GitHub fetch 仍在 40 秒限制处超时。通过 SSH
继续传输已提交 bundle，尚未核验完整远端 SHA 前不导入、不生成。新 94b478e 的
Linux 整本渲染仍待执行，不能用前三包旧 PASS 推断 588 已修好。医学 WARN 定义
仍待答复，四 draft 继续禁用，未部署。

### 5.6 C 族目录专业性修复与服务器传输恢复（e7d343a）

随后 CI **34016832113**（fb1e725，业务源码 94b478e）四个新包完整合成 golden
gate 全 PASS；默认全量 qa-gate 尚在进行。该成功只证明机器检查范围，不代表
真实病例验收或所有页面的专业性已人工确认。继续查看 83b22b0 的 C 族原稿
第 5/6 页，发现目录纳入长篇参考文献及多个局部参考文献标题；这是此前有效页码
检查没有覆盖的版式缺陷。旧测量保留，不能改称旧稿已通过人工验收。

e7d343a 将重建目录的大纲归一化同时应用于 C 族，只保留原平面目录与正文能够
对应的标题；文献正文保留，只取消其误继承的目录级别，局部“参考文献：”不再
冒充全局章节。原生目录 QA 增加文献条目/裸 URL 混入检查，即使页码全部有效也
FAIL。只重建 62+PD-L1 模板；13、62、588 模板 SHA 不变。
开发 **200 passed / 19.40 秒**，CRC/目录/QA 保护 **33 passed / 7.35 秒**；
50 项细分目录测试、四模板 6 私有 token 交叉扫描全部通过，整本渲染仍待重放。

SSH 有间歇性长连接掉线，已断点续传并独立核验完整远端文件：

- bdd7eaa-from-6749292.bundle：`b6d1bc28030bd65e5cc0e8a362b58850433778e714286b2f4661561b9da1f264`，已导入 Git 对象；
- fb1e725-from-bdd7eaa.bundle：`7d07712b6aa5ce55177c49f465986111af32b629d7f47fd0816b5ed199e6380a`；
- B/C IHC 图片 SHA 为 `aaec9fc11533160600149067cc045a713d66bf3eeddb4a1e0ff8520d13e06a3c`、
  `9d0846dc0d5022eedf8003efde26d9625ecc10edf456e2b44d8673b9095912d4`；
  YAML 完整 SHA 也与本地一致（`3e21b9af…148c04a2`、`ec1f7310…e499297`）。

传输验证不等于运行/部署成功。A 没有可用 PD-L1 原始来源，继续保留缺失，绝不
使用旧 contract 中不可溯源的 TPS/CPS。准备最新提交的隔离实稿与网页回放；
未启动服务切换，医学 WARN 口径仍待用户确认。

### 5.7 合成目录回验与 B 族余留版式（1244f3d）

CI **34017234879 / 18514ad** 四 draft 合成完整 golden gate 均 PASS，默认全量
qa-gate 仍在执行。C62+PD-L1 新 Word SHA
`cc3d52c81a80e09680dcf11cd1c4fedd265be91bb50b2985d3923ac46df85700`，
28 页、原始 QA PASS、目录 21/21、文献条目 0、旧缓存 0；看图核对第 5/6/7 页，
目录已清洁、基本信息黑字可读、合成 1/1 统计正确。并未人工逐页批准整本医学内容。

继续查看上一版 588 合成 Word（CI 34016832113，SHA
`f5a2530d7c7439626935fc981835accac39482567013d285059f960cebc3ecad`）：
50 页、机器 QA PASS；第 5 页原装饰竖线穿过新目录，第 23/24 页 FAQ 第 7 问断成
3 行孤页，FAQ 标题从历史共享编号继承成 3。1244f3d 只移除已识别旧浮动目录上的
剩余装饰，短问答用 keep/cantSplit 绑定，FAQ 明确为第一附录，后续肺癌知识标题
允许自然衔接；长问答不整体强绑，正文答案未改。201 项开发测试通过；最终 Linux
版式要以 0b85b93 的重建模板回放为准，不能把旧机器 PASS 改写成人工 PASS。

### 5.8 真实表格边界与比对器纠正（0b85b93）

隔离服务器实际运行 **18514ad** 完成了两份实稿，均 generation success、原始 QA WARN：

| 实稿 | 最终 Word SHA256 | 页数 | 原始阻断 |
|---|---|---:|---|
| C13 | `0d6224b6cfdf4861bf01faf511f0d151fc42acd015560ba288aa21d1af141f1a` | 39 | 跨癌种残留/已抑制解释 WARN；指南/PGx 合并与旧比对误报 |
| A62 | `750cb740385bd55a0752b3c8f631f2575f33cb500abd9b90b61e8ed91d0ee50b` | 35 | 同类 WARN，另 CNV 来源待审；PGx 合并与旧比对误报 |

C13 原实稿 SHA 下载后匹配；独立读回 4 变异、3 靶向，13 个检测基因。其第 5 张
物理表把 3 列药物介绍和 4 列指南拼在一起；第 13 张物理表合并 17 个药物表头及
73 行实际 PGx，形成 16 列网格但每行只有 6 个逻辑单元格。按 XML 单元格去重、
按真实表头分段后，9 条指南和 73 行 PGx 与上下文逐字段全符；**合并本身仍 FAIL**。
指南/药物行不是缺失，更不能删除源行或调低数量来使验收通过。

588 parity 的 17 个旧差异集合来自 None 渲染为空文本；对全部 38 个键递归执行
同一空值规则后差异为 0。仅规范空值，不忽略 Result/Level/Genotype/药物内容，
不排序行、不去重源行；篡改医学结论、证据等级或删行的单测仍失败。
旧 generation/receipt/Word 均未覆盖，单独复核文件为 `real_C13_logical_scope_recheck.json`。

0b85b93 给指南补持久标题分隔，30 个受控 PGx 模块各自放入来源药名标题，标题和
表格共同受非空列表条件控制。公开合成输入改为两种独立药物；最终 Word golden
门禁新增“指南首行独立、两个 PGx 表分别以表头开头”检查，防止单药样例掩盖合并。
四包重建，**208 passed / 19.55 秒**；CRC/目录/QA 保护 **33 passed / 7.98 秒**；
专项 83 项、四模板源基线及 6 私有 token 交叉扫描均 PASS，ruff/diff check PASS。
这不是最新原生 Word 排版通过证据，需重跑后登记。

隔离 Web 源码 18514ad，独立存储/认证/LO 端口，仅服务器回环 + 私有 SSH 隧道可达，
不属于生产部署。ego-browser task 27 已用专用合成账号登录，上传真实 C62 派生 Excel：
默认检测为“肺癌62基因”；填写可溯源 C 例 TPS 5 / CPS 6 后自动成为 62+PD-L1，
未构造新旗标、未依赖文件名。尚未提交该网页报告或任何批量任务，不能登记 3/3。

工作分支已推送 0b85b93；供服务器验证的 bundle SHA
`e344894c1599a88e1d415739ed1a04608552f489f31a5619e3722f75ed0c932e`。
传输期间的部分文件 SHA 不匹配不代表完整 bundle 损坏，校验完整后才允许导入。
医学 WARN 的验收定义尚未收到答复，A 的 PD-L1 原始来源仍缺失；没有修改这两项门禁。

### 5.9 最终表格边界回验与 13 双病例（f7aabde）

0b85b93 的 C13 仍因指南表合并失败：参考文献清理没有识别紧邻的指南标题，误把
分隔标题当作参考文献替换；A62 的逻辑表格已通过，原始 QA WARN。其 Word SHA
分别为 `215aaf5785eb65101bca4e738772ad8ffae6741c58e6dd82d431155a18534164`
（C13，40 页）与 `753e6d7b018a1160d42aff61f69aec22eee76867dc8b520d4405e4b79498f3a8`
（A62，36 页，62 基因/10 指南/71 PGx）。旧 CI 34018316918 也失败；两种合成药物
还合法映射出“铂类化合物”第三表，不能为迎合“恰好两表”而删来源组。

f7aabde 补齐语义边界、空参考文献段的插入及幂等测试；合成门禁要求至少两个独立
PGx 表且每表从表头开始，保留第三来源组。开发 **211 passed / 20.73 秒**、CRC
保护 **33 passed / 7.78 秒**；GitHub **34018704771 整体 SUCCESS**，不是仅子任务绿灯。
后续查询也确认 34017234879（18514ad）已整体 SUCCESS，但不替代新版本验证。

| f7aabde 实稿 | 最终 Word SHA256 | 页数 | 最终 Word 范围核对 | 严格验收 |
|---|---|---:|---|---|
| C13 | `7fc6967b0e4beba39d310ca3dd84f4e7d9af2cabd034fd8731314e27dbb0ab94` | 40 | 4 变异/3 靶向；13 基因/9 指南/73 PGx，分表检查零差异 | FAIL：qa_not_pass |
| A13 | `139dcf25ed621138352724eac88d91da32872a8cd07597e091dc0ecb2c31cf05` | 35 | 1 变异；13 基因/9 指南/71 PGx，分表检查零差异 | FAIL：qa_not_pass |

两份空白页门禁 PASS；C13 原生 TOC 11/11、旧缓存/文献条目 0。原始 QA 均为 WARN：
PART3_CROSS_CANCER_RESIDUALS、PART3_CROSS_CANCER_SUPPRESSION、PIPELINE_WARN；
A13 另有 CNV_SOURCE_REVIEW。医学警告没有消除或豁免，不能写成 qa gate PASS。

对原始最终 Word 执行规范 `two_case_leak_test.py` 双向检查：C→A 的 9 个 C 专属
工程别名/c.HGVS/p.HGVS 均不出现，3 个 A 自身 token 均在；反向 3 个 A 专属均不出现，
9 个 C 自身均在。`f7aabde_two_case_isolation.json` 为 PASS；该结果仅覆盖选定 token
与 13 包，不表示整个医学正文或另两个包已通过第二病例测试。

### 5.10 人工版式补门禁与隔离网页入口修正（845aaef）

查看 f7aabde C13 的 40 页缩略总览及第 6—9 页原尺寸 PNG：第 8 页仅空栏目说明/
表头，第 6/7 页同一变异行被拆开，染色体/频率窄列首行逐字折断。OOXML 证明数字
本身正确，但继承 Normal 正文 `firstLine=420`；源表未设置重复表头或 cantSplit。
因此旧机器“视觉 PASS”不等于专业排版通过。原 Word/PNG/原始 WARN 回执未改。

845aaef 的变换只涉及四 draft：主变异表显式首行缩进 0、两行重复表头、单事件行
不跨页，保留列宽/字体/内容；三个小包保留原药物栏目标题和说明，非空列表原样出表，
空列表改成明确的“暂无可列示结构化条目/待报告组复核”，不输出阴性或无药可用结论。
移除该短栏目周围的占位分页，“检测结果说明”可自然连排，新报告大部分仍保留母版分页。

新增仅针对四 draft 的 DOCX QA：空药物表头、缺少重复表头、可拆事件行、继承首行
缩进均阻断；旧 f7aabde Word 用新检查只读复核为 FAIL（45 个结构项、4 种错误代码），
不反向修改旧 QA。最小复现先失败；本轮 **213 passed / 19.89 秒**、CRC/目录/QA
保护 **33 passed / 7.53 秒**，另 69 项文档专项及四模板源基线通过；6 个私有 token
交叉扫描零硬命中，ruff/diff check PASS。最新四模板 SHA 见第 2 节，仍待原生回放。

f7aabde 私有 Web 首轮真实三份 13 Excel：项目类型留空，经网页批量入口提交任务
`fbc4d51f-87c7-4d48-b531-48efa6266de8`，实际 0/3、全部失败，未生成 Word。
原因是本任务的私有测试入口缺少 `__main__` 保护，multiprocessing spawn 再次执行
绑定端口，子进程抛 Address already in use；不是生产业务代码或 Excel 格式失败。
失败网页/JSON/日志均保留，未通过直接 API 提交冒充网页成功。
修正后的私有入口已做 `__mp_main__` 导入无副作用验证，等待新工作树网页重测；
已按 PID/cwd 精确停止两个旧测试 Web/LO 实例，未停止生产服务、未删除测试数据。

源码已提交并推送 `845aaef26eefeb9c659a9738223f4c85d2b69085`。供服务器导入 bundle
SHA256 为 `45eade638169817c03b2c02c8b2c044867fbdab5be11a6bb70beeb47324fd8b6`。
PD-L1 批量合同仍隔离共享 IHC 数据；不能把未提供 IHC 的批量稿视为已完成 B/C
来源转录验收。A 的原始 IHC 缺失、医学 WARN 定义、真实九例、最新版整本渲染和
主线/正式部署均仍待完成；四 draft 的生产资格保持 false。

### 5.11 真实批量识别、原生 QA 等价形式与固定附录（a3ad18d → 37b77f7）

845aaef 网页实际提交两个任务，均自动识别模式、未选历史同案强制门禁：
13 为 `dcecb03a-3197-4b1d-bd2c-e2ca8cc1655b`，62 为
`19f753ff-57d4-4b3e-a87f-b6cfcf0b7326`。每组生成完成 3/3 不代表 QA PASS。

| 输入 | 自动项目 | 原始 QA | 原生页数 | 空白/低内容检查 |
|---|---|---|---:|---|
| A13 | lung_13 | FAIL | 33 | PASS |
| B13 | 未识别，错误回退 CRC | FAIL | 63 | FAIL |
| C13 | lung_13 | FAIL | 39 | PASS |
| A62 | lung_62 | FAIL | 35 | PASS |
| B62 | lung_62 | FAIL | 46 | FAIL，第 42 页 |
| C62 | lung_62 | FAIL | 48 | PASS |

B13 的 Hereditary_tumor 成员旗标整列空白。ExcelReader 已保留原始表头，但旧检测器
只取非空行键，因此漏掉真实存在的旗标列。a3ad18d 改为联合原始表头与行键，仍不读
单元格值来推断产品；全空成员和仅表头的 13/62/588 六条合成用例先复现失败，再回归
通过。6 份真实派生输入轻量读取均自动识别正确、置信度 1、跨族冲突为空。未修改输入。

另五稿的缩进 FAIL 是旧新检查过严：LibreOffice 把显式首行 0 输出为 `hanging=0`。
新检查接受首行/悬挂/字符缩进的等价零形式，继续检查样式继承并阻断非零或坏值；
不是忽略 QA。a3ad18d 同时给四 draft 配置默认 `_评审草稿.docx`，CRC 默认命名、
调用者明确指定文件名保持不变。248 项轻量回归及 33 项 CRC 保护通过。

B62 原生第 41/42 页人工查看证实：Wnt 图后第三条固定文献独占一页，且页脚
“第 39 页共 31 页”来自母版静态总数。37b77f7 将固定附录短文献组与有界图/图注
共同分页，文献按原行距、不再吸附正文网格；不删文献或修改文字/字体。62 页脚中的
固定总数变为原生 NUMPAGES 域；未刷新的 0 缓存和静态总数均由新 QA 阻断。
源码模板允许待刷新缓存，不能据此把未渲染模板当成最终 Word 的 PASS。
原始 PNG SHA256：第 41 页 `f807acff00fb7d6a94f8941fd5e16c7fd898c0a76f6b1acd93e294a553912bf2`；
第 42 页 `6075d5a58d39f16f9c40c6f17f8993aa1207a2e83f4e5d0cfae07b246425ea22`。

37b77f7 提交前 **250 passed / 23.01 秒**、CRC/目录/QA **33 passed / 7.51 秒**，
四源模板基线及 6 token × 4 模板交叉扫描通过。该轮 SHA 见私有 build_fixed_reference_footer；第 2 节记录最新候选。
bundle SHA256 `f035f2f36555611e4384c6084dc34e5883388858e38f6254e8182ec88e4b2fb5`。
网页 UI 对 845aaef 的 QA_FAIL 正确展示 BLOCKED；未标记审核、交付或降级门禁。
两个旧批量已终态后才停旧测试服务；生产仍未改动。最新原生页数、九份矩阵、
双病例及医学 WARN/缺失 A IHC 的裁决仍待完成。

### 5.12 原始来源默认值与自动空白页（37b77f7 → 801f3b0 → 5883452）

37b77f7 通过真实网页提交三个批量，均完成 3/3；13、62 自动识别，62+PD-L1
从同一 62 族下拉选择。没有填写虚构 IHC，没有启用历史真同案强制对照。

| 包 | 实际网页任务 | A/B/C 原始 QA | 默认 PDF 页数 | 原生含自动空白页页数 |
|---|---|---|---|---|
| lung_13 | `514f6aa7-69c8-4d75-987a-c73ea2a39da7` | WARN/WARN/WARN | 33/36/39 | 34/37/40 |
| lung_62 | `7f1007a1-8d07-45fa-bfea-8086ab743b84` | WARN/WARN/WARN | 35/46/48 | 36/47/49 |
| lung_62_pdl1 | `89f8a4f0-4ab7-415e-b8ae-9262644b09c7` | FAIL/WARN/WARN | 36/45/47 | 37/46/48 |

1. **来源保真**：三份原始 Excel 都没有样本类型，旧全局默认“组织”被网页映射再当成
   表单来源注入。801f3b0 新增 panel 限定的 `missing_source_defaults`：四 draft 显示
   “未提供”，表单默认留空、映射预览不返回该默认值，显式组织/血液照常保留；共享
   CRC 映射不变。263 项 / 29.06 秒、33 项 CRC / 7.85 秒、相关表单接口测试通过。
2. **真实孤页**：A62+PD-L1 第 14 页仅剩 Level D 和尾注，下一短指南指向小节还保留
   历史强制分页。5883452 复用已有按固定说明前缀移除分页的处理器，只为该包增加
   对应固定尾注；合成测试先复现 2 个分页，再确认仅移除目标、保留无关章节。
3. **默认导出漏检**：B62 页脚共 47 页而默认 PNG 46 张，不是 NUMPAGES 刷新错误。
   同一 Word 在 UNO 中三阶段刷新均 47 页；显式 `IsSkipEmptyPages=false` 导出 47 页，
   第 4 页为空，true 导出 46 页。九份原生成 Word 的只读原生计数均比默认 PNG 多 1。
   自动插页由前置分节重新编号触发。新模板只去掉首节以外的页码重启值，保留节几何、
   页眉/字体/编号格式，改为整本连续编号。原生 TOC QA 启用自动空白页完整导出；
   旧模板的默认渲染路径不变。独立空白门禁增加同一选项，小包验收显式启用。
   原先省略自动空白页的 PASS 不再被视为整本无空白的凭据。
4. **分表独立核对**：37b77f7 的 C13 实际 Word SHA256 为
   `7652a6d75195440ef39fc1528e27bcaf2279868b02c45758b65cf43e014345bb`，
   顺序 BRAF/ERBB2/TP53/PIK3CA，靶向 BRAF/ERBB2/PIK3CA，13 基因/9 指南/73 PGx，
   38 项 588 parity 零差异。A13/B13 为 1/2 个变异、0/1 个靶向、71/73 个 PGx；
   六份 13/62 的基因集合、指南、PGx 及 38 项 parity 一致。剪接事件 pHGVS=`*` 是
   源缺失标记，不当成蛋白终止位点，独立比对使用其真实 cHGVS；不改变异行。

5883452 提交前 **274 passed / 31.87 秒**、CRC **33 passed / 8.45 秒**、
旧渲染行为 **10 passed / 4.82 秒**，四源模板基线、6 token 交叉扫描通过。
模板仅 document.xml 的页码重启属性改变；原媒体/页眉/字体等源基线不变。
本轮 bundle SHA256：`dd3b5bda4b2d761eac5b1972692e06239edefcf198511e7463656003dec2db96`。
启动脚本 SHA256：`eae028488eb2e6c17db761e586a90a8029adeb582e93857e69f6e33efec3990e`。
新的独立验收实例为 `frozen_5883452`（18098/23098），旧九份原始回执保留。
截至本节落档，新版九例尚未完成；医学 WARN 没有消除或豁免，生产资格仍为 false。

### 5.13 完整网页九例与机器漏检的版式问题（5883452 → 6462cd5）

5883452 通过真实网页上传以下三个批量。13 / 62 未指定 project_type，自动识别全部
正确；62+PD-L1 上传同一组 62 文件并按订单下拉选择。第三次选择后立即点击碰到
下拉关闭动画，未产生请求；等待关闭、重选并确认后仅有一次有效提交，没有跨族生成。

| 产品 | 网页任务 | A/B/C 页数 | 生成 | 原始 QA | 完整空白门禁 |
|---|---|---|---|---|---|
| lung_13 | `97a7ca88-78e1-4a89-9d4c-54671664308b` | 33/36/39 | 3/3 | WARN/WARN/WARN | 3/3 PASS |
| lung_62 | `b0b7cf43-353c-4b91-ac76-11b2a0bb422b` | 35/46/48 | 3/3 | WARN/WARN/WARN | 3/3 PASS |
| lung_62_pdl1 | `3ecbd769-5cfb-4194-96a2-4037464976d0` | 35/45/46 | 3/3 | WARN/WARN/WARN | 3/3 PASS |

- C13 最终 Word SHA256：`499686b29eeb55eeec09026c9859b2cc750a52e45e6fef72f2a8f4f1644c44ac`；
  四变异 BRAF/ERBB2/TP53/PIK3CA、三靶向 BRAF/ERBB2/PIK3CA；13 检测基因、9 指南
  行、73 PGx 明细。38 项 588 parity 零差异，独立读取最终 Word 而非只读内部上下文。
- 九份产品集合、指南、逐药六字段、38 项 parity、缺失样本类型“未提供”、draft 标记、
  页脚总数与实际页数均通过只读检查。12 项 C↔A / C↔B 定向泄漏测试通过。
  旧独立比较器对 A62 / A62+PD-L1 误报 TSC1：源为 `c.474delT`，报告按既有
  `normalize_c_hgvs_display_text` 合同显示 `c.474del`，蛋白 `p.F158Lfs*9` 完整。
  已让比较器按既有显示合同规范期望值；原矩阵中的两条失败保留，新版须重跑。
- 全部 raw QA WARN 保留：跨癌种历史叙述及结构化隐藏后的替代文案待审；A 例另有
  产品内 CNV 原始记录待复核。原有 #13 边界不变，#14/#15 仍按历史口径留待报告组。
  批量中的 PD-L1 全部“未提供”，不使用 B/C 结果填 A；A 没有 IHC 原始记录。
- 人工看到 B/C62 第 5 页仅标题/统计、变异表整块移至第 6 页。OOXML 定位是母版
  `w:tblpPr` 浮动锚点，不是数据删行或行的 keepNext 链。6462cd5 只将新 draft 主表
  改内联、统计说明随首行；表格网格、宽度、边框、字体、行值和不拆事件行规则不变。
- 动态解读标题还将 Wingdings 字体编码 `u` 显示为字母。6462cd5 四 draft 通过包内
  样式配置使用 Unicode `❖`；服务器确有覆盖该字符的 DejaVu Sans。默认 CRC/旧
  588+PD-L1 分支不改。QA 新增浮动主表、旧字体符号两项 FAIL，不放宽原有规则。
- 新回归 5 项先失败、修复后通过；首次两条颜色断言错误检查了历史黑色前缀，纠正为
  检查标题正文红/蓝色，不改变既有配色。完整 **279 passed / 31.34 秒**、CRC
  **33 passed / 8.44 秒**、旧渲染 **10 passed / 4.28 秒**。四源基线仅 document.xml
  哈希变化，原媒体/页眉/字体等基线不变；四模板硬字面量 0、6 token 交叉命中 0。

新 bundle SHA256：`af6f2a5e6c648517047498fc29b5555ab83199896726c65d6b82a7e55ee57e78`。
新私有启动脚本 SHA256：`3a54a2c313e665e9be11294140d8f8011ddf2cf0c79b1addbddda2637dfbcbec`。
6462cd5 已推送并核对 origin 同分支完整 SHA；main 仍为 295ebd2。5883452 的完整
CI 34024639069 为 SUCCESS，新 CI 34026187551 已启动。bundle/启动脚本/比较器
远端 SHA 均匹配，正在启动 `frozen_6462cd5`（18099/23099）；不宣称新版本原生或
正式部署已完成。5883452 九份导出 Word 的本地 SHA 均与原始网页产物相同；22 张
全书总览已人工查看，版式缺陷按上述结论保留，不能由机器空白 PASS 覆盖。

### 5.14 最新冻结源码真实网页回放（6462cd5）

`frozen_6462cd5` 启动后已复核 Git/cwd/完整源码身份、四模板 SHA，以及六份派生输入
逐字节一致。入口为隔离回环 18099 / 23099；最多两个报告工位，生产未改。
三次上传均通过 ego-browser 的实际文件选择和提交按钮，不直接调用后端代替网页。

| 产品 | 网页任务 | A/B/C 页数 | 生成终态 | 原始 QA / FAIL |
|---|---|---|---|---|
| lung_13 | `7130ba04-9831-456a-b15a-c1adb4e5fff6` | 33/36/39 | 3/3 | 三份 WARN / 0 FAIL |
| lung_62 | `a300a682-c215-4394-b46f-0446c7244885` | 35/45/47 | 3/3 | 三份 WARN / 0 FAIL |
| lung_62_pdl1 | `8aa4b816-a1f6-4162-b40f-59d0e15edce1` | 35/45/46 | 3/3 | 三份 WARN / 0 FAIL |

13 / 62 默认自动识别；+PD-L1 用同一组 62 文件从下拉选择。三次上传均 HTTP 200，
用时约 16.40 / 6.86 / 8.81 秒。金标准同案门禁未勾选，原因是用户明确授权延期真实
配对；不是命中了历史基准。三组 PD-L1 未随共享表单填入，缺失内容保持未提供。
`web_submission_6462cd5.json` 留存提交事实及任务 ID。

最新版 C13 Word SHA256：
`727fe08302bae3ec93ec08ae588553c94c478c1f624089893d2fad2e3cbd9398`；
原始 QA SHA256：`4c514f6b02eb99783d7bf94336fc8b6bb7421a7101c3875500b9537d58a0412c`。
九份导出清单 SHA256：`da5bfdb90c916bff9f2a7949c84aa34d67c4753e9f4fa899ca6fb42add467b5c`。
新比较器 SHA256：`a241f4faacce273c79c4420cf5639fbbacb7d2c7a0f3e2806101a7adba486a43`；
只读导出工具 SHA256：`17032633b6cef2b2cb22ce97259d1d359faa5822fe619c140dce75386a4fcb5d`。
全书 361 页、22 张总览均由本版本实际 Word 的原生渲染产生，已全部下载并人工查看。
59 项原件/总览/导出清单逐一 SHA 核验相同；校验清单 SHA256：
`ceaec00f071d60f9dbacfe8cf6fe20c914b4fd3df6d7ec12050fbc4732a84eca`。
六张关键页面另看全尺寸；范围与未解决问题记录于 `visual_review_6462cd5.json`，
并非逐字医学审核，不能扩大为所有叙述或临床证据已获得批准。

最新版完整只读矩阵 SHA256：`52b49b263980535f080da28de4c03d35d3101049f1659ff1994ccbb0a6ca4731`，
九份最终 Word 成员集合/HGVS/顺序/检测基因/指南/逐药六字段/样本类型/draft 标记/页脚
均无失败，38 项 588 parity 全部零差异；包括 A62 / A62+PD-L1 的 TSC1 既有显示合同。
九份 `render_blank_page_check` 均 PASS，显式包含自动空白页且 strict trailing；
12 项定向 two_case_leak_test 均退出 0。比较器整体退出 1、`strict_pass=false`，唯一
机器严格未通过项是九份原始 QA WARN，未更改原始 QA 或将退出 1 当作通过。

已查看的全尺寸页确认 B62 第 5 页标题/统计与变异表同页，原先整张标题孤页已消除；
C13 第 7 页 PIK3CA 完整事件及三条靶向提示保留，第 10 页 Unicode 符号正常。
人工另记录 P2 页尾小标题/表头与正文分离（finding 13），保留为排版待办，未把它
说成不存在或自动门禁已经覆盖。因此本稿只能作为带明示限制的评审候选，不能宣称
终版专业排版或临床质量已经全部放行。

同一隔离实例补测原始 C588 Excel：网页显示肺癌588基因、结构识别置信度 100%，
默认无 PD-L1；填入 C 来源中的 TPS=5 后，下拉自动切换 588+PD-L1 的报告组评审模板。
表单重新加载后确认 TPS=5 保留，再填 CPS=6，两值均正确显示，未触发单份生成请求。
该步骤只检验前端识别/同族切换，不提交缺少患者姓名等信息的单份报告，不把它算作
已完成 588 的新真实 Word 验收或完整 IHC 结果录入验收。

网页批量页会显示“生产门禁 PASS / 待审核 / 0 阻断、9 警告”，但每例 QA 实际为 WARN，
且 Diff 命中 0/3。聚合页顶部“QA 未生成”不代表逐例没有 QA，原始文件和行级结果为准。
没有点击“标记已审核”或“已交付”；上述宽松工作流门禁不能替代用户要求的 raw QA PASS。

完整 [CI 34026187551](https://github.com/youngfly93/drug_panel_auto/actions/runs/34026187551)
已为 completed / success，headSha 精确匹配 6462cd5；四 draft golden 和默认 qa-gate
均 SUCCESS，后者包括全后端回归、历史合同、前端及原生全页报告门禁。
`ci_6462cd5_observed.json` 记录已观察到的状态，不挪用旧版本的 CI。
GitHub 连接间歇性 EOF，未将请求失败记为 CI 失败。18:27（北京时间）实测生产
`current_release` / `REVISION` / 主进程 cwd 仍为 da8e62d，主进程 PID 2596421，
公网 `/api/v1/healthz` 返回 `{"status":"ok"}`；origin/main 仍 295ebd2，工作分支与
本地源码一致为 6462cd5。没有执行正式发布，不满足“部署后三源一致”。

本次再次运行共享审计核对器，退出 1。当前小 Panel 模块仅有 Codex 审计，仍缺
Claude 同版审核；其余历史模块的既有身份差异也未擅自修写。日志 SHA256：
`eab60fcf177e42f29886a840130ec9f74ab1f16309eb3e07aa0a0755ed136e12`。
本轮主线程自检不冒充独立双 agent 同版联合批准。

### 5.15 用户授权的 warn-only draft 发布

2026-09-06 用户复核明确要求：六个肺癌包默认 `runtime_action: warn_only`，
保留扫描/WARN 和历史原文；压制仅保留为可选项。允许仅部署 draft，不开放临床交付。
这替代了 5.14 及旧结尾中“待用户裁决医学 WARN”的停止点，未改写旧 strict=false 回执。

业务源码 `1fbb2948410c75321530f93d6936498e07c9f3fd` 已提交并推送。六包配置、
建包默认、无配置时的默认均为 warn-only。新增六产品原文保留 + 扫描 WARN 单测和
缺省值单测，原有 opt-in 压制单测仍保留。`7922072` 仅修正旧生成单测对 suppression
检查项的预期，不改业务。66 + 211 项轻量测试通过；四个模板与六个私有标识交叉扫描
hard=0、ZIP 命中=0，模板 SHA 与第 2 节相同。

| 产品 | 新实际网页任务 | A/B/C 页数（含封面/封底） | 原始 QA |
|---|---|---|---|
| lung_13 | `0f2b051c-8ab4-4d30-af94-96d6f6eece3a` | 33/36/44 | WARN/WARN/WARN |
| lung_62 | `58972edf-8ca7-45a3-b051-9a233722201a` | 36/49/53 | WARN/WARN/WARN |
| lung_62_pdl1 | `e06109e5-7387-445c-b31c-dfd3b6fc441e` | 36/49/55 | WARN/WARN/WARN |
| lung_588 | `3fc131f2-f396-40c3-8883-51522516cdc7` | 60/73/82 | WARN/WARN/WARN |

原始 WARN 仅保留跨癌种扫描/PIPELINE，A 另有 CNV_SOURCE_REVIEW；suppression
检查项不再出现。早期只读 C13 矩阵确认：BRAF/ERBB2/TP53/PIK3CA 四变异、
BRAF/ERBB2/PIK3CA 三靶向；13 检测基因、9 指南行、73 PGx；38 项 588 parity
无差异，C↔A、C↔B 四向限定 token 检查通过。C13 Word SHA256：
`dc4d8a2c21cdeeac0480e89c9d95eb1ec76d8d9da518ebb795cdb75617ca22f9`；QA SHA256：
`ee8ae983b233fdc7c3c8fd0362fbf5a2ffe8249a549bb2d0522d8983484b4cbb`。
原文恢复使 C13 从压制版 39 页增加到 44 页；没有删行压页。

B/C588 使用同一原始 Excel/同一表单，对比旧生产 da8e62d 与候选的渲染前上下文：
241 个旧键中只有 `immune_hyperprogression_results` 改变，新加 `cnv_review_genes` /
`cnv_review_required`，与 #13 修复边界一致；gene/drug 历史解析表完全相同。
这是渲染前数据对照，不冒充 B/C588 最终 Word 的全页对照或医学二审。

十二份已完成原生空白检查（require-render、strict-trailing、含自动空白页、120 dpi），
均 PASS；每包 C↔A / C↔B 四向泄漏共 16 项全部退出 0。小包九份源表成员/HGVS、
检测基因、指南、逐药六字段、样本类型、draft 标记、页脚和 38 项 588 parity 零差异。
小包原矩阵 SHA：`ce6d5babff0efdec4f05965cfb89f603f5c6f53f699bcf8e6ea5bab41e546daa`。

588 原矩阵 SHA：`73c9f1d0983c29339502e0bb68fecd5c32b61d0a903418d236fba637f73351ab`，
保留其三种检查器适配误报及 strict=false。新独立回执
`588_legacy_adapter_1fbb294.json`（SHA
`e87486952879054fe27a01f25f952684c3eee14f2f23ad8cc1d3d9e424c65b01`）逐份绑定相同
Word/Excel/QA 哈希后复核：完整 588 基因逐项匹配母版，规则仅 `C8orf34/C8ORF34`
大小写有别；A 的 TP53 small588 单元格是注释，而旧/新 588 均按 `ExistIn552` 的明确
I/II/III 类纳入；“样本类型：”的冒号不影响实际“未提供”值。A/B/C 变异为 7/8/9，
所有事件 HGVS 均匹配源表，并有删事件/换基因负对照。未改业务、Word 或旧回执。

CI 34034116775 的四个合成 draft gate 均 PASS（各 8 PASS、0 WARN、0 FAIL；
pytest/历史真配对是独立步骤）；完整后端为 1087 passed、2 skipped、1 failed：
329 旧断言仍要求残留扫描 PASS。该测试前向改为原文可见 + WARN + 无 suppression，
不得据此将整条旧 CI 改判 SUCCESS。最终提交必须重新通过必需 CI 后才能合并部署。
报告组待决清单同时记录 #14/#15、跨癌种原文、页尾表头/断词及派生标识导致的姓名
缺失；原始 QA WARN 不改写为临床 PASS。真实文件均留在本地 .work/ 与 iyun129 私有目录。

全书 606 页的 35 张总览全部下载、逐一核验服务器 SHA 并查看；C13 第 6/7 页另看原尺寸。
视觉回执 `visual_review_warn_only.json` SHA 为
`4d60bb5f80d9a2ff07b6e1e8fb47fc77cfa0bdf6675a68f50dc4eef4982a9710`。没有整张中段
空白页；588 的稀疏 PGx 续页及既有页尾表头/断词仍记为 P2 排版待办，不宣称终版精修。
该检查不等于逐字医学审核或真实同案比较。

新 draft 验收回执引用旧矩阵的不可变 Word/QA/输入哈希、588 适配复核、全书视觉、
模板扫描和合成 gate；明确原始 strict=false、raw QA=WARN、clinical_approval=false：

| 产品 | `.work/lung-small-panel-derived-inputs/draft_acceptance_warn_only/` 回执 SHA256 |
|---|---|
| lung_13 | `45e82c374e795676c2831b1ccb99a0aae1700203e522ac42996f2e0ced829624` |
| lung_62 | `3380387cb28a97142ec9c23416fef36c418812a732ee48006e202adc3bdb017f` |
| lung_62_pdl1 | `ff66f0e4ca50f7a948f85616fc21f1c835c50729c37d173f5937ec063ba8bef0` |
| lung_588 | `5d0a4553b603371ef097c53765e04e0cb4e204c850dffc09b81e1abd6b33374a` |

四份 readiness 因而设为 `DRAFT_REVIEW_ONLY` / draft=true / production=false；三端仅
禁用 CRC301 和甲基化。48 项发布/范围测试通过，2 项按平台条件跳过，三端 scope gate
PASS。再次执行共享审计核对器仍退出 1（既有 identity 短/长 SHA 差异及单边覆盖）；
未编辑对方审计，未冒充同版双 agent 审批。当前仍需新提交必需 CI、主线合并、精确
历史候选/备份/官方部署及在线验证；此处记录 draft 资格，不声称生产已更新。

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
  `build_reference_boundaries_b_final/lung_588/build_receipt.json`：fa17b1a 两个目录候选模板；
  中间建包失败回执不覆盖、不算通过。
- `reference_toc_full_lightweight.xml`、`reference_toc_pgx_units.xml`、
  `reference_legacy_guard.xml`：176 / 51 / 5 项回归；`cross_scan_reference_toc.json`
  仅记录 token 数、模板 SHA 与命中数，不记录病例身份。
- `ci_4387fe8/`：四包失败的公开合成 Word、PNG 与 QA，不能替代真实 A/B/C 门禁。
- `ci_8c8aeb5/`、`profile_alias_recheck/`：第二轮公开合成 Word/QA 及原 Word 重检查。
- `build_native_flat_case_fields/<panel>/build_receipt.json`：fb72cc3 四份历史候选模板；
  `native_flat_full_lightweight_retest.xml`、`native_flat_crc_toc_guard.xml`、
  `cross_scan_native_flat.json` 为 191 / 33 项测试和最新模板扫描。
- `ci_83b22b0/`：前三包合成完整 gate PASS、588 FAIL 的不可覆盖原始产物。
- `build_b_floating_toc_final/lung_588/build_receipt.json`：94b478e 的 588 模板 SHA；
  `b_toc_lightweight_full.xml`、`b_toc_template_matrix.xml`、`b_toc_crc_qa_guard.xml`
  和 `cross_scan_b_floating_toc.json` 是本次 180/17/33 项及四模板扫描回执。
  `build_b_floating_toc/` 为中间模板，不作终态渲染凭据。
- `build_c_toc_heading_scope/lung_62_pdl1/build_receipt.json`：e7d343a 的 C 族模板 SHA；
  `bc_toc_full.xml`、`bc_toc_crc_qa_guard.xml`、`bc_toc_qa_full.xml` 与
  `cross_scan_bc_toc.json` 为 200/33/50 项及四模板扫描回执。
- `build_b_faq_flow/`、`b_faq_full.xml`：1244f3d 的 B 族模板/201 项开发测试。
- `build_table_boundaries/<panel>/build_receipt.json`：旧 0b85b93/f7aabde 四模板 SHA；
  `table_boundary_full.xml`、`table_boundary_crc_guard.xml`、`table_boundary_targeted.xml`
  和 `cross_scan_table_boundaries.json`：208/33/83 项与四模板交叉扫描。
- `real_18514ad_C13/` 与 `real_C13_logical_scope_recheck.json`：旧实稿/上下文/原始门禁，
  以及新比对器的只读复查，不能代替新模板生成后的验收。
- `real_f7aabde_C13/`、`real_f7aabde_A13/`：最终 Word、原始回执与上下文；C13 含
  40 张源 PNG 和两张缩略总览。`f7aabde_two_case_isolation.json` 是限定 token 的双向检查。
- `build_empty_drug_flow/`、`empty_drug_full.xml`、`empty_drug_crc_guard.xml`、
  `cross_scan_empty_drug_flow.json`：845aaef 新四模板与 213/33 项回归及扫描；
  `empty_drug_red.xml` 保留新检查缺失的原始失败。
- `f7aabde_web_batch13_snapshot.json`：首轮真实网页 0/3 失败，不能覆盖为成功；
  `staging_entry.py`、`launch_remote_845aaef.sh` 为只作用于任务隔离目录的测试入口。
- `development_units_final.xml`、`release_scope_units.xml`：本次开发回归，不替代冻结服务器门禁。
- 服务器隔离目录为本轮 `reportgen-lung-small-drafts-20260906.HySk3P`，不是生产目录。
  `frozen_c608430` 为干净 Git 工作树；`verified_inputs` 内 A/B/C 三份完整 SHA 已匹配。
  `frozen_c608430/.work/validation_A13_initial` 保留首例失败；损坏传输文件不得使用。

- `sparse_header_red.xml`、`sparse_header_naming_full.xml`：稀疏表头六项原始失败与 248 项通过；
  `fixed_footer_flow_full_final.xml`、`fixed_footer_flow_crc.xml`：250/33 项验证；
  `build_fixed_reference_footer/`、`cross_scan_fixed_footer.json`：最新模板与扫描。

- `build_continuous_pages/`、`continuous_pages_final.xml`、`continuous_crc_guard.xml`、
  `render_defaults_guard.xml`、`cross_scan_continuous_pages.json`：5883452 的构建与开发保护。
- `web_matrix_5883452_raw.json`、`page_overviews_5883452/`、`final_web_exports_5883452/`：
  实际网页九例原始回执、全书总览及评审稿；完整原生空白检查仍在服务器
  `frozen_5883452/.work/web_matrix_final/`，旧失败不覆盖。
- `receipt_checker_0480c5e.zip` 保留原比较器；新比较器按既有 HGVS 显示合同处理 del/dup，
  不修改源 Excel / Word。全矩阵原始严格验收仍为 false。
- `build_inline_marker/`、`inline_marker_red.xml`、`inline_marker_green.xml`、
  `inline_marker_full.xml`、`inline_crc_guard.xml`、`inline_render_defaults_guard.xml`、
  `cross_scan_inline_marker.json`：6462cd5 构建、原始失败、279/33/10 项保护与扫描。
- `web_submission_6462cd5.json`、`web_matrix_6462cd5.json`、`ci_6462cd5_observed.json`：
  最新三批实际网页提交、最终只读九例矩阵和完整 CI 状态。
- `final_web_exports_6462cd5/`、`page_overviews_6462cd5/`、`artifact_checksums_6462cd5.json`、
  `visual_review_6462cd5.json`：九份评审 Word/原始 QA、全部 22 张总览及哈希/人工检查记录。
  真实来源及产物留在本地 `.work/` 与 iyun129 私有目录，不进入公共仓库。

当前下一步：按 5.15 已获准的 draft 边界，完成新版受影响工程门禁及精确主线 CI、
历史发布合同/清单、备份和发布 wrapper，再验证三源身份与公网入口。医学晋级仍为
false，原始 WARN 不改写，不能把隔离验证实例当作正式服务已更新。
