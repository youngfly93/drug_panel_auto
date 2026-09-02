# 修复流水账

## R1 — 2026-09-02 肺癌报告组生产 UAT

- 冻结基线：`808a289a7cb253745d0247066249fb8982454cbf`
- 范围：肺癌 329/588 报告组自助生成链路。
- P1 / `MATERIAL_SCIENCE`：第三部分仍输出含非肺癌历史语境的知识段；修复边界为隐藏命中字段并显示待肺癌专属审核提示，不新增医学结论。
- P1 / `VERIFIER_PLUMBING`：网页上传的病例图片回执覆盖了人工填写的 PD-L1 原始来源编号、日期和标本身份；修复为图片回执与原始来源分字段保存。
- P2 / `VERIFIER_PLUMBING`：可选年龄的 `null` 被前端数值控件初始化成空字符串后显示为 `0`。
- P2 / `VERIFIER_SEMANTICS`：人工确认 Panel 后仍沿用自动识别失败的阻断提示。
- P2 / `VERIFIER_SEMANTICS`：上传预览没有随人工填写的样本类型刷新 TMB 展示口径。
- 观察项：肺癌 588 的完整历史金标附录篇幅较长；本轮不删除已锁定金标附录，避免把版式忠实度问题误修成内容缺失。

## R2 — 2026-09-02 修复与复验

- `MATERIAL_SCIENCE`：对 329/588 第三部分配置的跨癌种词只做字段级结构化隐藏，保留基因、变异和药物身份；渲染后的第三部分再做残留扫描。7 个合成边界病例/Panel 均为 `7/7 PASS`，全部 `part3_cross_cancer_residuals=PASS`。
- `VERIFIER_PLUMBING`：PD-L1 原始来源编号、来源日期、标本编号和 assay profile 与图片上传回执拆分保存；图片上传只写独立的 receipt/upload/bound-sample 技术字段，不再覆盖人工转录来源。
- `VERIFIER_SEMANTICS`：网页预览与正式生成使用同一 Panel 文本规则和 Panel 限定知识源；人工 Panel 选择成为有效选择，年龄空值保持空白，TMB 预览按当前样本类型刷新，329/588 恢复批量入口。
- `VERIFIER_PLUMBING`：为 `lung_329_pdl1`、`lung_588_pdl1` 接入可重复的合成金标；金标显式携带合成 PD-L1 来源和图片，不包含真实患者数据。当前输出快照补采 TPS/CPS/判定，发布门禁不再因验证器不认识肺癌 Panel 而失败。
- 正式 QA gate：`PASS`。Panel validation、知识发布门禁、Ruff、回归、329/588 金标 reference/candidate、重复性 diff、current-output 契约全部 PASS；历史外部报告目录未在本机配置，`legacy_reference` 如实 `SKIPPED`。
- 视觉代表件：329 为 23 页、588 为 46 页，均无空白/近空白页且视觉 QA PASS。页数由病例变异量和 588 历史固定附录决定，不锁定为 25 页。
- Web smoke：前端 production build PASS；登录、任务统计、Excel 上传/识别、预览、报告生成、QA、下载和 DOCX 文本检查全部 PASS。
- 未替代项：以上为工程与报告组 pilot 验收，不等于医学签署；真实病例 PD-L1 来源、医学规则和 Windows Word/WPS 人工版式确认仍需授权人员负责。
