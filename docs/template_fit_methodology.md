# Template-Fit 分析方法论

为新 panel 提供**数据驱动的设计起点**——量化候选 panel 的语料与已有 golden template 的兼容度,据此判断"该复用、该扩展、还是该重新设计"。

> 这份文档说明**为什么**和**怎么做**。具体接入操作请走 [`onboarding_new_panel.md`](onboarding_new_panel.md) 第 0.5 步。

---

## 1. 出发点

直接"挑一份终版报告变量化"是单点经验做法。问题:
- 不知道这份终版是不是 family 内的代表案例
- 不知道 family 之间结构上像不像、能不能复用现有 golden
- 设计模板时凭"看起来差不多"判断,容易漏挖变量或硬编码

我们已经有 CRC358 golden template,它经历过完整变量化 + 双病例验证 + 量产。**与其每个新 family 从零摸索,不如先量化它和 CRC358 的差距,告诉接入者该走哪条路。**

## 2. 算法

对每份候选语料报告(`.docx`),计算它对 CRC358 golden 模板的"契合度":

### 2.1 章节命中率
- 已知 CRC358 章节标题集合(报告导读 / 致患者信 / 检测结果小结 / 基因变异解析 / 阅读说明 / 基因检测列表 / 参考文献 ...)
- 在候选报告里按标题模糊匹配(去标点、去序号),命中数 / 目标数 = 章节命中率

### 2.2 章节级 Jaccard 相似度
对每个命中的章节:
- 提取章节内**段落集合**(规范化:去空白、去 footnote 标记、去 zwsp)
- 计算与 CRC358 同章节的固定段落集合的 Jaccard 相似度 `|A∩B| / |A∪B|`
- Jaccard ≥ 0.85 = "段落基本一致";0.5–0.85 = "结构同但内容不同";< 0.5 = "需重新设计"

### 2.3 表格列签名匹配
对每个已知表格(主变异表 / NCCN / 化疗 / 免疫四表):
- 列数(报告中 vs 模板中)
- 列名 first row 的字符串集合的 Jaccard
- 评分:列数相同 + Jaccard ≥ 0.8 → "可复用结构";否则 → "需重新设计"

### 2.4 汇总:per-report fit score
```
fit = 0.4 × 章节命中率 + 0.4 × 段落级Jaccard均值 + 0.2 × 表格签名匹配率
```
权重可调,默认按"章节存在最重要 → 段落次之 → 表格细节最次"。

### 2.5 聚合到 family
- 取 family 内所有报告的中位数 fit score
- 也算 25/75 分位数,看分布

## 3. 分类与决策

按 family 中位数 fit score 分三档,对应不同接入策略:

| fit score | 分类 | 接入策略 | 工作量估计 |
|---|---|---|---|
| **≥ 85%** | 兄弟 panel | 直接 `cp panels/crc_358_msi panels/<new>`,只改癌种内容 + panel.yaml | 1-2 天 |
| **60-85%** | 表亲 panel | 复用骨架,但 fit < 0.6 的章节需要单独设计;变量化重点放在差异部分 | 3-5 天 |
| **< 60%** | 陌生 panel | CRC358 不是合适的 base。两条路:(a) 找另一份 family 内的 reviewed 报告作为新 golden;(b) 走完整 corpus 段落频率挖掘(无监督) | 5-10 天或更长 |

## 4. 输出格式

### 4.1 Per-report JSON(机器可读)
```json
{
  "report_path": "肠癌/CRC301/2025-09-21-脱敏.docx",
  "family_hint": "CRC301",
  "fit_score": 0.91,
  "section_hit_rate": 1.0,
  "paragraph_jaccard_mean": 0.88,
  "table_signature_match_rate": 1.0,
  "high_fit_sections": ["报告导读", "致患者信", "阅读说明", ...],
  "low_fit_sections": [],
  "novel_sections": [],
  "missing_sections": []
}
```

### 4.2 Per-family markdown(人读)
就是 `onboarding_new_panel.md` Step 0.5 期望的那份 design brief。例:

```markdown
## Template-fit analysis: CRC358 golden ↔ Lung13 (n=130)

Median fit: 72/100  →  "表亲 panel"

### ✅ 高契合章节(直接复用) ...
### 🟡 中契合章节(可复用骨架,改内容) ...
### 🔴 低契合章节(必须新设计) ...
### 🆕 该 family 独有(CRC358 不存在) ...
### 接入预估: 5-7 天
### 推荐起步:
- base: panels/crc_358_msi
- 重点设计 4 个新章节
- 知识库扩展项 ...
```

## 5. 已知局限

1. **结构差异极大的 family,该方法准确性低**——比如 family 内根本没有 CRC 那套章节结构(纯非癌种、纯检验报告),fit 都会算成 0-30%,没有信息量。这时退到 Layer 2-4 无监督挖掘。
2. **fit score 是**"参考度量",不是"通过线"——0.85 阈值是经验值,实际应结合 medical 顾问 review 决定。
3. **对单份 reviewed final docx 的依赖**——分析只能告诉你"这个 family 和 CRC358 像不像",不能告诉你"这个 family 的 reviewed final docx 哪份最有代表性"。后者仍需医学/产品人工挑选。
4. **段落规范化是脆弱的**——空白处理、不可见字符、字体变化都可能让两段看上去一样的段被 Jaccard 算成不同。代码里需要稳健的 normalizer,且接入新 family 时要 spot-check 一批 false negative。

## 6. 工具实现

参考脚本(待写):`scripts/template_fit_analyzer.py`

CLI 草案:
```bash
python -m scripts.template_fit_analyzer \
  --golden panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx \
  --corpus "各癌种基因报告近年汇总/肺癌" \
  --family-hint Lung13 \
  --output tmp/template_fit/lung13_fit_analysis.json \
  --report tmp/template_fit/lung13_fit_brief.md
```

约束:
- 输入语料里**不得**包含真实病人信息(脱敏后用),或者所有产出文件留在 `tmp/`(.gitignore 覆盖)
- 第一版**先在 CRC358 自己的语料(603 份肠癌报告)跑 self-validate**——应该所有报告都高契合,如果不是说明算法有 bug

## 7. 和其他文档的关系

| 文档 | 角色 |
|---|---|
| 本文档 | 方法论:为什么用 fit 分析、怎么算、怎么解读 |
| [`onboarding_new_panel.md`](onboarding_new_panel.md) Step 0.5 | 接入流程里的具体一步 |
| [`panel_migration_roadmap.md`](panel_migration_roadmap.md) | 哪些 panel 要接入、按什么顺序 |
| [`panel_report_inventory_audit.md`](panel_report_inventory_audit.md) | 语料的 aggregate 统计(为本方法提供输入候选) |
| [`prd_multi_panel_template_architecture.md`](prd_multi_panel_template_architecture.md) | 高层产品决策(包括"用数据驱动迁移"这一选择本身) |
