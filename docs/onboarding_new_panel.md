# 接入新 Panel 的 9 步走查清单

适用场景:你要给报告自动化系统加一个新的 panel(新癌种 / 新子 panel / 新检测类型),让它走和 CRC358 同样的工程路径——从 Excel 上传到生成 docx 全流程跑通。

> 阅读顺序建议:先把 `docs/prd_multi_panel_template_architecture.md` 扫一遍理解大架构,再走本清单。

## 0 · 前置:你必须先有的两份东西

| | 是什么 | 没有就 stop |
|---|---|---|
| 🅰️ | **一份已被业务/医生确认的"终版报告 docx"** | 整个系统的设计假设是"以终版为模板基底变量化",没有终版无法接入。先去找 / 评审到一份 |
| 🅱️ | **至少 1-2 份真实样本的输入 Excel** | 用来端到端跑通 + 双病例验证(避免硬编码陷阱) |

不要在 🅰️/🅱️ 不齐时就开始;白浪费时间。

---

## 0.5 · 跑 Template-Fit 分析(数据驱动的设计起点)

在动手拷目录、写 panel.yaml 之前,先用脚本扫一遍 family 语料,**量化它和 CRC358 golden template 的兼容度**,据此决定接入策略:

```bash
python -m scripts.template_fit_analyzer \
  --golden panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx \
  --corpus "各癌种基因报告近年汇总/<your_cancer>" \
  --family-hint <your_family_id> \
  --report tmp/template_fit/<your_family>_brief.md
```

读输出的 markdown(`<your_family>_brief.md`),它会告诉你:

| Fit Score | 分类 | 该做什么 |
|---|---|---|
| **≥ 85%** | 兄弟 panel | 直接 `cp panels/crc_358_msi panels/<new>`,改癌种内容即可,~1-2 天 |
| **60-85%** | 表亲 panel | 复用骨架,但有 N 个低契合章节要重新设计,~3-5 天 |
| **< 60%** | 陌生 panel | CRC358 不是合适 base。换 family 内另一份 reviewed final 当 golden,或走无监督模式挖掘 |

输出里还会列:
- ✅ 高契合章节(直接复用)
- 🟡 中契合章节(可复用骨架,改内容)
- 🔴 低契合章节(必须新设计)
- 🆕 该 family 独有章节(CRC358 没有)

**这一步是为后面的 Step 1-3 节省时间**——你拿到这份 brief 后,Step 1 的 `cp` 不用拍脑袋选 base,Step 3 的变量化也知道哪几个章节要重点画。

算法细节、阈值、为什么用 Jaccard 等:见 [`template_fit_methodology.md`](template_fit_methodology.md)。

如果你的脚本还没写好(`scripts/template_fit_analyzer.py` 是后续工作),退而求其次:**用 git diff 或文本对比工具手工对一份 reviewed final 和 CRC358 golden** 的章节标题与段落,得到同样的"高/中/低/新"分类,只是更慢更主观。

---

## 1 · 选 `panel_id` 与目录骨架

```
panels/<panel_id>/
├── panel.yaml                    # 主契约,见步骤 2
├── qa.yaml                       # QA 配置(可选,先复制邻居)
├── templates/
│   ├── <panel_id>_<variant>_v<n>.docx   # 步骤 3 产出
│   ├── golden_template_v0_variables.yaml # 变量字典
│   └── README.md                 # 说明从哪份终版变量化来的
├── rules/                        # 步骤 4 填
│   ├── biomarkers.yaml / drugs.yaml / report_text.yaml / ...
└── context_contracts/            # 步骤 6 填
    └── <reviewed_case_id>.yaml
```

**命名约定**:`panel_id` 必须 `lowercase_snake_case`,直接作为目录名。例:`crc_358_msi`、`lung_methylation`、未来的 `breast_brca_panel` 等。

**最快上手**:`cp -r panels/crc_358_msi panels/<your_panel_id>`,逐项改。

---

## 2 · 写 `panel.yaml`(主契约)

参考 schema:`docs/schemas/panel.schema.json`。每个字段都有说明 + 在哪个 panel 能看到示例。

**最少必填**(被 schema 标 `required` 的):
```yaml
schema_version: "1.0"
panel_id: "your_panel_id"          # 必须等于目录名
display_name: "对外展示名"
version: "0.1.0"
status: "pilot"                    # ⚠️ 先 pilot,通过验收后才改 active
default_template: "your_panel_id_v0"
templates: [ ... ]                  # 至少 1 个
rules: { ... }                      # 至少有 panel_rules
input_contract: { ... }             # required_tables + required_single_fields
template_contract: { ... }          # required_variables + required_lists
```

**enhancer 字段两种用法**:
- 业务规则像 CRC → `enhancer: "reportgen.core.enhancer_registry:CRC358Enhancer"`(复用)
- 全新业务规则 → 写一个新的 PanelEnhancer 类放进 `reportgen/core/enhancer_registry.py`,然后填它的完整路径
- 暂不需要 → `enhancer: ""`(自动走 NoopEnhancer)

**校验**:写完后立即跑
```bash
python -c "
import json, yaml
from jsonschema import Draft7Validator
schema = json.load(open('docs/schemas/panel.schema.json'))
doc = yaml.safe_load(open('panels/<your_panel_id>/panel.yaml'))
errs = list(Draft7Validator(schema).iter_errors(doc))
print('ok' if not errs else errs)
"
```

字段名打错、缺必填、枚举值不对,都在这一步报出来,不要等渲染时才发现。

---

## 3 · 把终版报告变量化成 `templates/<...>.docx`

这步最费时,也是接入新 panel 最值钱的工作。**核心原则**:不要从头造模板,**就地变量化终版**。

详细方法论参见 [`golden-doc-report-factory` skill](~/.claude/skills/golden-doc-report-factory)(三层分类法 + 四个反模式)。简版:

1. 拿到终版报告 docx 副本
2. 清洗:删评论 / 删修订痕迹 / 删品牌字 / 删真实病人数据
3. 逐节决策(每段问自己):
   - 全报告通用 → **原样保留**
   - 一份报告一个值 → `{{ variable_name }}`
   - 表格行数随病例变 → `{%tr for row in items %}` 行循环
   - 数量不定 + 每段不同格式的富文本 → 插入 `__SECTION_MARKER__`,渲染层用代码动态注入
4. 整理变量字典到 `templates/golden_template_v0_variables.yaml`(谁该是 `{{}}`、谁该是循环、谁是 marker)
5. `templates/README.md` 写"这份模板从 `<某某终版 docx>` 变量化而来,变量化日期 YYYY-MM-DD"

**绝对不要**把任何病人数据(姓名、ID、具体变异、丰度、日期)留在模板里。模板里 0 字面量是验收硬指标(步骤 7 会扫)。

---

## 4 · 填 `rules/*.yaml`(panel-specific 业务规则)

按需创建,**和 panel.yaml 的 `rules` 字段对应**:

| 文件 | 内容 | 何时需要 |
|---|---|---|
| `panel_rules` | 主规则(变异分级、I/II/III 类规则、复合条件等) | 总是 |
| `report_text` | 固定文案、说明段、固定引导句 | 总是 |
| `biomarkers` | TMB / MSI / PD-L1 等生物标志物的口径与文案 | 涉及 IO 治疗时 |
| `guideline_tables` | NCCN / 临床指南表的内容 | 实体瘤报告通常需要 |
| `drugs` | 靶向/免疫药物商品名、证据等级 | 涉及药物推荐时 |
| `style` | 颜色 / 字体 / 边框等 docx 样式细节 | 总是 |
| `reviewed_part3_knowledge` | 变异级知识覆盖(按 gene + cHGVS + pHGVS 键控) | 想做"变异级精准解析"时(强烈推荐) |

**起点**:从最像的现有 panel 复制一份,改值。不要从零写,容易漏字段。

---

## 5 · 写 `context_contracts/<reviewed_case>.yaml`

把你的"reviewed 真实病例"应该输出的每一个关键字段值,以**结构化期望**写下来。例如:
```yaml
patient_name: "张三"
total_variants_count: 11
drug_related_count: 4
tmb_summary: "TMB-L"
msi_summary: "微卫星稳定型，MSS"
variants_2_1:
  - { gene: "KRAS", c_hgvs: "c.34G>A", p_hgvs: "p.G12S", af_pct: 46.29 }
  # ... 其余预期变异行
```

作用:让 context_contract 校验器在渲染前就抓住"数据出错"(早于版式渲染),省下大量 debug 时间。

---

## 6 · 选 / 写 enhancer

- 像 CRC 系列?直接复用 `CRC358Enhancer`(已注册服务 crc_358_msi + crc_301_msi)
- 不像?在 `reportgen/core/enhancer_registry.py` 加一个新的类,实现 `PanelEnhancer` Protocol。最小骨架照抄 `NoopEnhancer`,需要时再加业务逻辑
- 真不需要业务增强(纯模板填值)?`enhancer: ""`,系统走 `NoopEnhancer`(肺癌甲基化就这么做)

---

## 7 · 接入后必做的硬验收(任何一条没过都不要 active)

### 7.1 schema 校验
步骤 2 末尾那段 Python 必须 0 错。

### 7.2 模板 0 病例硬编码
```bash
python -m scripts.scan_hardcoded_literals panels/<your_panel_id>/templates/<your>.docx
```
变异记法(`c./p.`)、丰度百分比、日期、ID **必须全部 0 命中**。任何 >0 都是漏挖。

### 7.3 双病例零泄漏(防硬编码 #1 法则)
用 2 个不同病例生成报告,跑:
```bash
python -m scripts.two_case_leak_test \
  --other <case_B>.docx \
  --seed-token "病例A的姓名" --seed-token "病例A的样本号" --seed-token "病例A的变异记法" \
  --expect "病例B的姓名" --expect "病例B的样本号"
```
必须 PASS。如果 FAIL,回步骤 3 找漏挖。

### 7.4 知识库未命中**大声报警**(非静默)
故意送一个含未在 KB 里的基因/变异的病例,确认 QA 输出里有明显警告(不是静默跳过)。

### 7.5 渲染器保真
在**生产用的同款引擎**(LibreOffice headless)下渲染,确认没有空白页 / 半空白页:
```bash
python -m scripts.render_blank_page_check <generated>.docx
```

### 7.6 golden case 注册
在 `panel.yaml` 的 `golden_cases` 写一条,以你 reviewed 病例为基准。这是回归护栏,以后改任何规则它会自动跑。

---

## 8 · 把 `status: pilot` 改成 `status: active` + 切默认模板

只在以上 7.1~7.6 全部通过后做:
```yaml
status: "active"          # 之前是 pilot
default_template: "your_panel_id_v0"   # 确保它的 status 也是 active
```

**绝对不允许**在 active 模板上残留"Not approved for default delivery"这类描述字段——这是审计的红线(参考 [main-protection-policy 记忆](~/.claude/projects/-Volumes-KINGSTON-work-minhao----panel------web/memory/main_protection_policy.md))。

---

## 9 · 走 PR + CI gate 流程,合并到 main

```bash
git checkout -b add-panel-<your_panel_id>
# ... 提交所有 panel 文件 + 在 backend/tests/test_report_regression.py 加该 panel 的回归断言
git push -u origin add-panel-<your_panel_id>
gh pr create --base main --title "feat(panel): add <your_panel_id> package"
```

确保 PR 的 `qa-gate` CI workflow 绿了再合。

---

## 常见坑(从这个项目踩过的雷里提炼,务必读一眼)

1. **PII 不要进 git**。`config/patient_info.yaml` 里别写真实病人记录;`context_contracts/` 用脱敏过的值。
2. **签名图片放 `storage/signatures/` 并 gitignore**。`config/signatures.yaml` 只存 name→相对路径映射。
3. **生成产物(`storage/reports/*/`)不要进 git**。
4. **慎用浮动文本框**。Word 里好看的浮动 text box,在 LibreOffice 下渲染常错位、产生空白页。能用内联就别浮动。
5. **空段落是分页杀手**。终版 docx 里成片的空段落(用来"撑页")在 LO 下不会被任何东西覆盖,会变成大片白纸。变量化时把没用的空段删掉。
6. **`__MARKER__` 占位段必须放在最终输出位置**(渲染时整段替换)。不要放在 `{%tr %}` 循环内部,否则替换逻辑会错位。
7. **接入新 panel 不需要改 `enhancer_registry` 的注册顺序**——loader 会按 panels/ 目录自动注册。但你需要把新 Enhancer 类**定义**在该文件里。
8. **不要给 `status: pilot` 模板设为 `default_template`**——schema 不会阻止,但生产上线时会闹笑话。

---

## 参考(已落地的接入范例)

- `panels/crc_301_msi/`:CRC301(肠癌小 panel,基于 crc_358_msi 复制改造)
- `panels/lung_methylation/`:肺癌甲基化(极简 pilot,enhancer 留空)
- `docs/crc301_panel_pilot.md`:CRC301 接入的实战记录,有具体卡点与解法
- `docs/prd_multi_panel_template_architecture.md`:整套架构的 PRD,设计意图溯源
