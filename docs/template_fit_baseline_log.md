# Template-Fit Baseline Log

为防止 `scripts/template_fit_analyzer.py` 的算法被悄悄改坏,每次重要修改后**跑同一组固定输入**记录指标,逐次比对。**任何数字偏移 >5% 都该 stop & review**,看是算法故意 calibrate 还是误伤。

## 固定输入(self-validation corpus)

```
golden : panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx
corpus : tmp/fit_self_corpus/    (服务器上,3 份从同 golden 生成的 .docx)
  - golden_self.docx       (模板本身)
  - case_reviewed_a.docx   (服务器外置的审核回归件)
  - case_reviewed_b.docx   (服务器外置的审核回归件)
```

复跑命令:
```bash
ssh iyun-server '
cd /media/desk16/iyun6208/apps/reportgen-web
.venv/bin/python -m scripts.template_fit_analyzer \
  --golden panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx \
  --corpus /tmp/fit_self_corpus \
  --family-hint CRC358-self-baseline \
  --output tmp/template_fit/baselines/crc358-self/$(date +%Y-%m-%d)/baseline.json \
  --report tmp/template_fit/baselines/crc358-self/$(date +%Y-%m-%d)/baseline_brief.md
'
```

## 历史记录(新条目追加到表底)

| 日期 | golden git | analyzer git | n | 分类 | fit p25/median/p75 | sections high/med/low | 备注 |
|---|---|---|---:|---|---|---|---|
| 2026-05-28 | `5c278bf` | `a4f4e36` | 3 | sibling | 84.9 / 85.1 / 89.3 % | 7 / 6 / 0 | 初次 baseline,P0 算法 |

## 解读约定

- **fit median 漂移 > 5 个点**:可能算法变了。看 git log 是否有 analyzer 改动 (algorithm change → expected) 还是无关改动 (bug → fix it)。
- **classification 跨档变化**(sibling↔cousin):严重,几乎一定要 review。
- **sections high/med/low 总数变化**:章节定义可能改了(`SECTION_PATTERNS` 加/减)。
- **n_reports 不一致**:语料丢了某份 / 分析逻辑跳过了某份,看 stderr SKIP 信息。

## 何时追加新条目

任意一条满足都该追加:
1. 改了 `scripts/template_fit_analyzer.py` 的算法(权重、阈值、章节模式、Jaccard 实现)
2. 改了 `panels/crc_358_msi/templates/crc_358_msi_golden_template_v0.docx`
3. 周期性体检(可选):每月一次,确认没有意外漂移
