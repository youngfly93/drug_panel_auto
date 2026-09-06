# 肺癌报告展示：报告组待决清单

日期：2026-09-06。范围：肺癌报告组评审稿；不构成医学批准或正式产品放行。

本轮明确要求先保留 #13 的 CNV 解析修复，#14/#15 与历史终版一致，暂不改变
业务展示。已发布到 Git 主线的 `295ebd26ad03d1f213c0fbfc7e6b1b982cb2ae50`
包含三项变更，因此在服务切换前停止该次部署，通过前向修订恢复以下历史合同；
不重写 Git 历史、不抹去原审计或旧验证记录。

| 事项 | 当前决定 | 待报告组裁决的问题 | 状态 |
|---|---|---|---|
| lung-report-accuracy-review-13 | 保留修复：解析 Cnv 多区块、保留原始 CopyNumber/AvgCP；数值或 gain 不自动等同于扩增 | 原始 CNV 观察是否形成医学结论，仍由报告组复核 | 工程修复保留 |
| lung-report-accuracy-review-14 | 暂保留历史 UGT1A1 展示规则，未覆盖组合不外推 | 是否修订仅在既有 *28/*6 组合上形成的历史剂量展示；需要怎样的基因型、临床上下文和审核依据 | PENDING_REPORT_GROUP |
| lung-report-accuracy-review-15 | 暂保留历史长春新碱/长春碱到长春瑞滨的展示映射 | 这些是不同药物名称；报告组需确认是否撤销历史跨药物映射及其联合方案小结 | PENDING_REPORT_GROUP |
| lung-small-panel-derived-inputs-14 | 六个肺癌 panel 默认 `warn_only`：保留历史解析原文和残留扫描 WARN；压制仅为显式可选项 | 逐段指出不适用的跨癌种原文，并给出经审阅的替换依据；未确认前不代写医学内容 | PENDING_REPORT_GROUP；不阻断 draft |
| lung-small-panel-derived-inputs-13 | 页尾小标题/表头与次页正文分离、个别断词及历史 588 稀疏续页保留为排版待办 | 在 Word/WPS 标注具体页码和希望的换页/断词方式；例如 1fbb294 C13 第 23/28 页、A588 第 28 页；后续按模板族统一修订 | P2；不阻断 draft |

2026-09-06 用户确认：允许部署报告组 draft，不开放临床交付。派生 Excel 文件名
中的 `-derived-` 导致病例富集无法匹配时，姓名保持“未提供”，不得据此补造患者信息。
同案真实小 panel Excel/终版逐字对照及病例级 IHC/医学审核仍分别待补；它们不作为
本轮报告组获取原文草稿的前置条件。原 QA WARN 保留，不改写为临床 PASS。

工程“与历史一致”仅是可复算的显示结论，不能证明药理等价或剂量建议有效。
严格同药物匹配、双位点原始分型展示的候选引擎能力与单测保留为显式选择的候选
策略，不作为本轮包的默认业务规则。所有肺癌包继续受 draft/pilot 及医学审核边界约束。

报告组答复须记录：事项 ID、decision、规则/来源、reviewer、date、适用产品和
边界病例。收到书面决定后再修订规则、冻结验证器身份并重跑受影响病例。

证据入口：`audit/lung-report-accuracy-review.codex.md` 的 #13–#15，
`panels/lung_588_pdl1/rules/guideline_tables.yaml` 的
`irinotecan_safety` 与 `base_drugs`，以及
`backend/tests/test_lung_history_alignment.py` 的历史显示回归。
