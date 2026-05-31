# 子宫内膜癌29基因 B-track Pilot 记录（2026-05-31）

> 验证"挑代表性真实终版 + 局部修改（金标模板）"这条路对子宫内膜癌成立。
> 配合 `docs/crc301_acceptance_and_panel_acceptance_guide.md`（通用验收清单）、
> 记忆 `panel-migration-status`、`architecture-debt-brakes`。

## 一、为什么走 B-track（半自动·局部修改）

子宫内膜癌报告**结构与 CRC 差异大**（MSI 独立成第二部分、无 TMB、有遗传性肿瘤/
胚系/林奇综合征专章、不同分节），早期评估一度判为"大工程"。但实测一份代表性终版
跨 3 份对比：**~53% 段落逐字相同**（章节骨架/MSI 说明/林奇附录/诊疗知识/基因列表
都是固定样板）。结论：绝大多数"结构差异"是**静态内容**，跟着金标模板走即可，不需
新写逻辑。故采用 lung_329 同款 **B-track**：变量化高置信标量，复杂动态段保留为
可编辑样板，先证明端到端管路 + PII 安全成立。

## 二、做了什么（交付物）

| 物件 | 路径 | 说明 |
|---|---|---|
| 金标模板 | `panels/endometrial_29/templates/endometrial_29_golden_template_v0.docx` | 从真实终版变量化、源病人 PII 全擦 |
| 变量映射 | `panels/endometrial_29/templates/golden_template_v0_variables.yaml` | 定点 cell/段 替换留痕（无 PII） |
| panel 包 | `panels/endometrial_29/{panel.yaml,qa.yaml,rules/*}` | 复用 CRC358Enhancer + CRC 规则（rules 内 panel_id 已改） |
| 冒烟测试 | `backend/tests/test_endometrial29_smoke.py` | 5 项：模板存在/PII-clean/注册/检测命中/渲染 |

代表样本：一份 4 体细胞变异（PTEN×2/CTNNB1/PIK3CA）、MSI=MSS、胚系"未检出"的典型终版。

### 变量化工具链（两步，可复现）
1. **种子（擦 PII + 注入身份标量）**：`scripts/build_golden_template_seed.py --replace`
   全局替换跨页眉页脚/跨拆分 run：`于雪梅→{{patient_name}}`、`MLJY-LZ250091→
   {{report_number}}`、`20250611→{{receive_date}}`、`20250624→{{report_date}}`，
   带残留校验（全 0）。
2. **变量化（定点标量）**：`scripts/variableize_golden_template.py --map` 按
   `golden_template_v0_variables.yaml` 替换通用词（不能全局替换的）：
   表0 `age(r1c1)`/`sample_type(r1c3)`/`clinical_diagnosis(r2c1,合并)` + MSI 结果句。
   最终模板残留源 PII = 0。

### 已变量化的占位（8 个）
`patient_name` · `report_number` · `receive_date` · `report_date` · `age` ·
`sample_type` · `clinical_diagnosis` · `msi_result`

> 性别(女)/抬头(女士)**有意保持静态**——子宫内膜癌患者恒为女性。

## 三、源病人临床发现已"中和留空"（数据安全）

代表报告的**阳性临床发现**（源病人于雪梅的 PTEN/CTNNB1/PIK3CA 变异+药物+QC值+
第三部分逐变异叙述）已从金标模板**全部中和**为占位/留空，避免把一份去标识真实临床
档案嵌进 git，也避免换病人时串出他人内容。中和后全模板复扫：源病人阳性发现残留 **0**、
身份 PII 残留 **0**。保留的 PTEN/PIK3CA 仅出现在**参考文献(公开PMID)+分子分型科普
+29基因列表**——是每份通用的静态 boilerplate，非源病人发现。

> 阴性默认（表5 POLE未检出 / 表6 胚系未检出 / 表9 BRCA未检出）作为常见兜底保留；
> 胚系/POLE 阳性的少数病例由 draft 横幅 + 人工复核兜住。

## 四、端到端诊断：哪些区域自动、哪些要人工（关键）

用合成 Excel（与源病人**完全不同**的 TP53/ARID1A 病例）走完整 `ReportGenerator.
generate(project_type=endometrial_29)`，逐区域核对实际行为：

| 区域 | 行为 | 说明 |
|---|---|---|
| 标量（姓名/年龄/样本/诊断/日期） | ✅ Excel 自动填 | 标量链路通 |
| **变异/药物详情表（表3/表7）** | ✅ **Excel+药物KB 自动填** | 有靶向药变异→填；无药变异(如TP53/ARID1A)→空(正确) |
| QC表 / 29基因列表 / 知识·通路·分型科普 | ✅ 静态正确 | 53% boilerplate |
| **MSI 结论句** | ❌ **未接线** | 给 MSI-H 仍显占位 → 人工填 / A-track |
| 表2 小结 Ⅱ类变异列表行 | ❌ 未接线 | 显示「待人工填写」 |
| 第三部分 3.1 体细胞变异解析 / 4.1 药物解析叙述 | ❌ 未接线 | 无 `__PART3_MARKER__` → 显示草稿占位 |
| 变异计数（"共N个体细胞变异"） | ⚠️ 口径存疑 | 给2个变异显示"共4个"，需核 CRC enhancer 口径对 endometrial 是否适用 |
| 遗传性肿瘤/胚系/林奇、签名 | ⚠️ 阴性默认/占位 | 阳性病例 + 签名需人工 |

**端到端不崩溃**：`generate` 跑完（~30s）、success=True、产物 PII-clean、QA sidecar
正常运行并 `qa_status=FAIL`（正确地标记"这还不是完整报告"）。换 TP53/ARID1A 病例时
**0 段**串出源病人(PTEN/CTNNB1)叙述。

> 修正早期判断：变异/药物**表**比想象的更自动（CRC 流水线按 Excel+KB 填）。真正要
> 人工/A-track 的是 **MSI结论 + 第三部分叙述 + 表2列表行 + 计数口径**。这缩小了 A-track
> 的范围，也是"每份人工编辑量"的实测起点（见 docs/endometrial29_editing_cost_log.md）。

## 五、试跑保护（draft）

模板首段（原为残留垃圾"哈哈哈哈哈哈"）已替换为**红色粗体横幅**：
「B-track 内部草稿 · 仅供人工复核编辑 · 变异表/药物/胚系遗传/林奇/逐变异解析等区域
未自动填充 · 不可直接交付客户」。panel `status: draft`、未部署。**B 档产物只能作为可
编辑初稿，禁止直接发客户。**

## 六、验证结果

- `pytest backend/tests/test_endometrial29_smoke.py` → **5 passed**（快：存在/PII-clean/注册/检测/渲染）
- `pytest backend/tests/test_endometrial29_e2e.py` → **1 passed**（端到端崩溃测试，~30s，`slow` 标记）
- 整个 panel registry 构建通过（`validate_panel_registry` 全绿，未影响既有 panel）
- 项目检测：`子宫内膜癌分子分型29基因检测` 文件名 → `endometrial_29`（conf 1.00），
  CRC 文件名仍 → `crc_358_msi`（无误判）
- 回归：lung329 smoke + golden_template_pilot **17 passed**

## 七、升级到 A-track（全自动）还需做什么

1. **MSI-only 生物标志物接线**：bridge 产出 `msi_result`（"微卫星稳定（MSS）型"等
   终版措辞），替代当前哨兵/手填。CRC358Enhancer 算 `msi_status`，需映射到该措辞。
2. **变异表 collection 化**：把检测小结表/变异详情表/药物表改 `{%tr for %}` 循环，
   接 enhancer 产出的变异/药物列表（参考 crc_358 模板循环）。
3. **体细胞/胚系拆分 + 林奇逻辑**：从输入区分体细胞 vs 胚系变异，驱动 3.1/3.2 与
   遗传风险提示 / 林奇附录条件文案——这是 CRC 没有、子宫内膜独有的新逻辑。
4. **29 基因列表 + 子宫内膜规则**：endometrial 专属 gene list / drug-filter / NCCN
   表（当前复用 CRC 规则，仅够注册，未对内容正确性负责）。
5. **合成 golden case + 样式基线**：建 endometrial 合成生成器 + `baselines/
   endometrial_29_style_baseline.json`，纳入 `test_style_baseline.py` 与 qa-gate。
6. **真实样本签收 + 部署**：报告团队用真实 Excel 跑一份逐字核对，再合 main → iyun62。

> 端到端诊断已缩小范围：变异/药物**表**已被 CRC 流水线自动填，A-track 重点是
> **MSI结论接线 + 第三部分叙述(`__PART3_MARKER__`)+ 表2列表行 + 计数口径校正**。

## 八、状态

`status: draft`，**未部署生产**。本 pilot 证明方法成立 + 守住 PII + 端到端不崩，
下一步是报告团队用真实 Excel 试跑、记录人工编辑成本（见
docs/endometrial29_editing_cost_log.md），据此决定 B 档留用还是升 A-track。
