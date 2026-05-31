# 肺癌329+PD-L1 内容策展 — 报告组 Handoff 清单

> 配合 PR #14 / docs/lung329_cbeta_status.md。**机制已就绪并验证**;此清单是交给报告组
> 的「审 + 补 + 扩」工作单。改的是**内容**(医学文本),不是代码。

## 一、现状(机制 + 已做到哪)

**机制(已验证,有测试守护,勿改):**
- lung 金标模板 v1(变异/药物/免疫表 + Part3 marker)— 端到端跑通。
- **gene-level Part-3 overlay**:`panels/lung_329_pdl1/rules/reviewed_part3_knowledge.yaml`
  的 `gene_sections`(基因机制 intro / 解析 mutation_analysis)+ `drug_sections`(药物关联
  benefit/caution)按**基因级**覆盖基础 KB(任意变异生效)。优先级:变异级 > 基因级 > 基础 KB。
- 守护:`backend/tests/test_gene_level_drug_override.py`(3 passed)+ 金标基线 crc_358/301
  全程 PASS(CRC 零回归)。

**效果(合成肺 Excel 实测):** 报告里"结直肠癌"串 **44 → 9**(初始纯 CRC 知识库 44 → 加
基因 说明/解析 31 → 加药物关联 9)。NSCLC 措辞 60+。

> ⚠️ 现有 overlay 内容是**从真实肺报告自动收割 + CIViC 参考**的 **FIRST PASS**,
> **必须经报告组临床审核后才能用于真实交付**。

## 二、内容覆盖表(15 驱动基因)

| 基因 | intro机制 | analysis解析 | benefit获益 | caution慎用 | 缺什么 |
|---|:-:|:-:|:-:|:-:|---|
| EGFR | – | ✅ | ✅ | ✅ | intro(用 CIViC) |
| KRAS | ✅ | ✅ | ✅ | ✅ | 全 |
| ALK | ✅ | ✅ | ✅ | ✅ | 全 |
| ROS1 | ✅ | ✅ | ✅ | ✅ | 全 |
| BRAF | – | ✅ | ✅ | ✅ | intro(CIViC) |
| MET | ✅ | ✅ | ✅ | ✅ | 全 |
| RET | – | ✅ | ✅ | ✅ | intro(CIViC) |
| ERBB2 | – | ✅ | ✅ | – | intro(CIViC)、caution |
| TP53 | ✅ | ✅ | ✅ | ✅ | 全 |
| PIK3CA | ✅ | ✅ | ✅ | ✅ | 全 |
| STK11 | ✅ | ✅ | ✅ | – | caution |
| KEAP1 | ✅ | ✅ | ✅ | – | caution |
| NRAS | ✅ | – | ✅ | ✅ | analysis |
| NTRK1 | ✅ | ✅ | ✅ | – | caution |
| KIT | – | ✅ | – | – | intro(CIViC)、benefit、caution |

- CIViC 英文权威摘要(`civic_gene_reference.md`)覆盖:ALK/BRAF/EGFR/ERBB2/KIT/KRAS/MET/NRAS/PIK3CA/RET/ROS1/TP53。
- CIViC 缺 STK11/KEAP1/NTRK1(这三个语料已收割到)。

## 三、报告组待办(按优先级)

1. **临床审核已收割的 15 基因文本**(最重要):逐基因核对 intro/analysis/benefit/caution
   的医学准确性、措辞、是否完整(收割是自动抽段,可能不完整或抓错段)。
2. **补缺**(见上表"缺什么"):
   - 5 个缺 intro(EGFR/BRAF/RET/ERBB2/KIT)→ 用 `civic_gene_reference.md` 的英文摘要翻译/改写。
   - NRAS 缺 analysis、ERBB2/STK11/KEAP1/NTRK1/KIT 缺 caution → 从真实肺报告或 CIViC 补。
3. **扩驱动基因列表**:剩余 CRC 串里有 **FBXW7** 等不在当前 15 基因列表的 → 把基因加进
   `scripts/harvest_lung_part3_knowledge.py` 的 `GENES` 列表再跑,或手工加 overlay 条目。
4. **核 MSI 共识指南名**(2 处《结直肠癌及其他相关实体瘤MSI检测中国专家共识》):该指南
   覆盖所有实体瘤,是合规静态文案,确认保留即可。

## 四、怎么操作

- **直接改文本**:编辑 `panels/lung_329_pdl1/rules/reviewed_part3_knowledge.yaml`
  - `gene_sections`:每条 `- gene: X` + `intro:` + `mutation_analysis:`(基因级,**不要**写 c_hgvs)。
  - `drug_sections`:每条 `- gene: X` + `type: benefit|caution` + `drug_name:` + `clinical:`。
  - 改完直接生成报告即生效(机制已接好,无需改代码)。
- **重跑收割**(扩基因/换语料后):`python scripts/harvest_lung_part3_knowledge.py`
  （会**覆盖**该 yaml,先备份已手改的内容)。
- **刷新 CIViC 参考**:`python scripts/download_civic_gene_summaries.py`。
- **验证没串 CRC**:生成一份肺报告,搜"结直肠/结肠癌/直肠癌"应趋近 0(除 MSI 共识名)。

## 五、禁忌(数据安全)

- overlay 只放**基因级**文本,**绝不**放病人变异位点/频率/姓名/样本号(收割已去标识,手改时也守住)。
- 语料 `各癌种基因报告近年汇总/` 是本地 PII,gitignored,**不入库**。

## 六、相关文件

| 文件 | 作用 |
|---|---|
| `panels/lung_329_pdl1/rules/reviewed_part3_knowledge.yaml` | **要审/补的 overlay**(gene+drug sections) |
| `panels/lung_329_pdl1/rules/civic_gene_reference.md` | CIViC 英文权威摘要(补 intro 用) |
| `scripts/harvest_lung_part3_knowledge.py` | 语料收割脚本(可改 GENES 列表重跑) |
| `scripts/download_civic_gene_summaries.py` | CIViC 下载脚本 |
| `panels/lung_329_pdl1/panel.yaml` | 声明了 `reviewed_part3_overlay` |
| `backend/tests/test_gene_level_drug_override.py` | 机制单测(勿删) |
