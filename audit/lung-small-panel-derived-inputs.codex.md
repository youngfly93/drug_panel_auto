---
module: lung-small-panel-derived-inputs
agent: codex
identity_kind: git_commit
identity_value: fdf3c100bda9ee6f7180d3cd3c8bbf3b576efd88
audit_date: 2026-09-06
---

# 肺癌小 Panel 派生输入与 draft 建包记录

结论：**部分完成，NEEDS_HUMAN；未完成三个 draft 包，未部署。**

已完成前置规则恢复、派生脚本、六份真实派生输入及冻结提交回归。实际输入与指定
三行验收有矛盾，62 两产品的默认共同旗标亦不能形成独立结构身份。没有通过删改
PIK3CA、手动 `project_type`、文件名识别或改写测试期望来伪造验收通过。

## 1. 需求与冻结身份

- 需求权威：用户 2026-09-06 本轮规格；沿用模板族总规格，增加“真实肺癌超集派生
  输入可用于 draft 工程验证”的明确授权，不把派生输入登记为历史同案真实小 Panel 输入。
- 被测代码：`fdf3c100bda9ee6f7180d3cd3c8bbf3b576efd88`，分支
  `codex/lung-small-panel-derived-drafts-20260906`。冻结测试前后 tracked tree 不变；
  用户原有 13 份未跟踪审计及专用 stash 保留，不属于本次源码 subject。
- 旧 PR #50 已合并 #13，也包含 #14/#15 修改；依新要求在服务切换前停止旧发布。
  本分支前向恢复 #14/#15 历史默认展示，候选严格策略仍有显式单测。
  [报告组待决清单](../docs/analysis-decisions/lung-chemotherapy-pending-review.md) 不代表医学批准。
- 本轮不修改生产禁用范围、不放宽历史差异指纹、不推断 PD-L1 或临床字段。

## 2. 母版来源（只记 SHA，不提交病例 Word 或文件名）

487 台账 SHA256：`9fb8d9d69f9c9642162518bc96112693ff9592e90db74befc39ebb358b215b3a`。
台账行号以包含表头的文件物理行计。三份原文件已复制到忽略目录，复制前后 SHA 一致。

| 产品 | 母版选择 | 族 | 台账行 | 母版 SHA256 |
|---|---|---|---|---|
| lung_13 | 用户指定终版 | A，无 PD-L1 | 28 | `56330fa8d883136297048ac58b2475da1bf6639fbbe9eedf90c61a5f4030305c` |
| lung_62 | 台账首份 A 族 62 候选 | A，无 PD-L1 | 255 | `a90010acad8e33c0d963b89c055f534b8162c90b5bcff0aa990eef57edf55b3c` |
| lung_62_pdl1 | 台账首份 C 族 62+PD-L1 候选 | C，含 PD-L1 | 426 | `25bccdf88cd8694e4c1c1ecd0a3a1428eed40a945f2f3b08466567a821f975d3` |

62 基因集合从上述非 PD-L1 母版的第 10 张表（零基索引 9）抽取；PD-L1 母版
第 9 张表（索引 8）给出相同顺序的 62 个唯一符号。清单文件
`.work/lung-small-panel-derived-inputs/genes62.json` 的 SHA256 为
`fc24e6bf05d940fc62f420af7e9049aa19be8f6f8a4da079b9a940e41e3a82f0`。
这仅冻结母版候选及集合，不表示模板已清洗、已批准或已通过历史同案对照。

## 3. 派生规则与源表复算

实现：`scripts/derive_panel_input.py`。

1. 只重写 Variations / Hereditary_tumor 两个工作表的成员旗标列；删除旧产品列，
   在首个旧列位置写入新列。无旧列则追加。Gene_Symbol 经去首尾空白、转大写后
   在指定集合中即为数值 1，其他行保持空值；不把分级当作成员资格。
2. 其余工作表以及其他 ZIP 成员原样复制。原始分级、HGVS、数值、公式与 Cnv 的
   ExistIn137 不改。多旧列且含公式/Excel Table 时显式拒绝未经审核的结构移动。
3. 旗标可由 `--flag-column` 指定，默认 `ExistInsmall13` / `ExistInsmall62`；
   脚本支持从未来 `panel.yaml` 的 `derived_input` 读取产品配置。
4. 输出必须在 `.work/` 下，文件名带 `-derived-<panel>`，已有输出/回执拒绝覆盖。
   回执只记录哈希、列名、计数及规则边界，不记录病例身份或原始正文。

当前可执行示例（无配置包时显式传基因集合）：

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

## 4. 两项需用户确认的冲突

| id | severity | claim | evidence | verdict |
|---|---|---|---|---|
| lung-small-panel-derived-inputs-01 | P1 | 指定的 13 基因集合与 C 例“只保留三个变异”不能同时成立 | C 原始 SHA 如上；Variations 第 39 行，Gene_Symbol=PIK3CA，cHGVS=c.3197C>T，pHGVS_S=p.A1066V，ExistIn552=Ⅱ类；用户集合含 PIK3CA | CONFIRMED |
| lung-small-panel-derived-inputs-02 | P1 | 62 与 62+PD-L1 同旗标、同结构、同集合时不能仅靠 structural_fingerprints 唯一识别 | 用户限定产品身份为旗标；`reportgen/core/project_detector.py:_calculate_structural_fingerprint_score`；两母版检测基因集合一致 | CONFIRMED |

C 输入的有效分级事件位于第 2、15、32、39 行，分别为 BRAF V600E、ERBB2 G660D、
TP53 G245D、PIK3CA A1066V。其余成员旗标行包括未分级或知识注释行，因此“旗标
恰好三行”亦不等同于“最终变异表三行”。已询问是否有正式产品排除规则、另一版本
C 输入，或应修正验收集合。没有收到裁决前不删改该事件。

已建议用可配置 `ExistInsmall62pdl1` 区分含 PD-L1 派生产品，待用户/技术老师确认。
该旗标只表示产品，不能被解释为阳性结果或 PD-L1 有来源；既有
`legacy_unspecified_ihc_transcription_v1` 合同仍须逐病例执行。

## 5. 门禁与方法保真

| 要求 | 当前结果 | 凭据/边界 |
|---|---|---|
| #13 保留、#14/#15 转待决 | 已实现于工作分支 | 默认历史回归 + 显式严格候选策略；不新增医学批准 |
| 派生脚本与保护性单测 | PASS | 冻结 SHA 专项 108 passed，8.85 秒；含新脚本 6 项及既有输入/历史回归 |
| A/B/C × 13/62 派生保真 | PASS，6/6 | 独立原始→派生单元格比较 + 冻结提交完整 SHA 重放 |
| C 例三行指定验收 | NEEDS_HUMAN | 原始集合复算为四事件，未更改输入/基因集合/断言以匹配三行 |
| 62+PD-L1 唯一身份 | NEEDS_HUMAN | 共同旗标不足以区分，未用文件名或手动 project_type 补洞 |
| seed → variableize → 三个 draft 包 | NOT_RUN | 原始母版及 SHA 已冻结；尚未创建可加载的半成品包 |
| scan_hardcoded_literals | NOT_RUN | 无变量化模板，不能记 PASS |
| two_case_leak_test | NOT_RUN | 无新产品 Word，不用已有 588 或 CRC 稿替代 |
| render_blank_page_check / 全页无孤行 | NOT_RUN | 无新产品 Word；未声称 42/44/56 页目标达成 |
| 新产品 QA gate / 网页批量 3×3 | NOT_RUN | 上游两项合同冲突待决；登录后的浏览器验收也没有执行 |
| 历史同案逐字对照 | AUTHORIZED_DEFERRED | 用户明确留待真配对输入，不伪称派生稿为同案验收 |
| 新版本部署后三源一致 | NOT_RUN | 本地实现已提交，未推送新分支或切换服务；GitHub main=295ebd2，生产=da8e62d，不能报同步完成 |

旧失败证据保留：首轮派生脚本的 ZIP 元信息复用缺陷导致 5 failed / 103 passed；
修复后各轮独立回执记录通过，不把旧 FAIL 改成 PASS。后续格式检查与 `git diff --check`
均通过。未运行新的整库 CI/历史金标发布门禁，旧 295ebd2 的通过不能挪用于此提交。

步骤地图：原始 Excel + 受控基因集合 → `derive_panel_input.py` → `.work/derived/`
→ 独立 openpyxl/ZIP 比较 → 冻结提交 SHA 重放。此阶段没有新生信重计算或绘图；
真实 Word、派生 Excel、临时脚本和日志均在 `.work/`，不进入 Git。共享审计核对器
仍报既有身份/覆盖缺口；没有宣称双 agent 同版联合批准。

## 6. 私有回执入口

目录：`.work/lung-small-panel-derived-inputs/`。

- `source_manifest.json`：母版原路径、台账行、原始/复制 SHA。
- `derivation_verification.json`：六份产物完整 SHA、所有非修改单元格检查、源表事件。
  SHA256：`9c668b3c89809a315d32f7e6c7fb24b338ca4f677e8d3892627d16c67f155827`。
- `frozen_replay.json`：冻结提交重放六份，完整产物哈希与上述回执逐份相同。
- `prerequisite_units_frozen.xml` / `.log`：冻结提交 108 passed；JUnit SHA256
  `3ee8ed17c0550f2eed51b03393f67c009d9346fd428e89495e0b2de26f587afe`。
- `initial_unit_failure.json`：首轮真实失败，不覆盖。

下一步仅在两项口径明确后继续：冻结产品旗标与筛选合同，清洗/变量化三个母版并
裁剪肺癌规则，运行指定三件套与网页 3×3；全部完成后再进入新的冻结发布流程。
