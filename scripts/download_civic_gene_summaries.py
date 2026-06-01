#!/usr/bin/env python3
"""下载 CIViC 公共领域基因/变异摘要(英文,权威,带文献),抽肺驱动基因 → 参考文件。
CIViC 是 CC0/public-domain。用法: python scripts/download_civic_gene_summaries.py
"""
import csv, urllib.request, os
GENES=["EGFR","KRAS","ALK","ROS1","BRAF","MET","RET","ERBB2","TP53","PIK3CA","STK11","KEAP1","NRAS","NTRK1","KIT"]
URL="https://civicdb.org/downloads/nightly/nightly-FeatureSummaries.tsv"
os.makedirs("tmp/civic", exist_ok=True)
tsv="tmp/civic/nightly-FeatureSummaries.tsv"
if not os.path.exists(tsv):
    urllib.request.urlretrieve(URL, tsv)
rows={}
with open(tsv,encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r.get("feature_type")=="Gene" and r.get("name") in GENES:
            rows[r["name"]]=r
out="panels/lung_329_pdl1/rules/civic_gene_reference.md"
L=["# CIViC 基因摘要参考(肺 329 驱动基因)",
   "",
   "> 来源:CIViC (civicdb.org, CC0/public-domain),nightly FeatureSummaries。**英文权威底稿**,",
   "> 供报告组策展 lung `reviewed_part3_knowledge.yaml` 的 intro / 药物关联中文叙述时参考。",
   "> 由 scripts/download_civic_gene_summaries.py 生成。需翻译+临床复核后入库。",
   ""]
for g in GENES:
    r=rows.get(g)
    L.append(f"## {g}")
    if r and (r.get("description") or "").strip():
        L.append(f"- CIViC: {r.get('feature_civic_url','')}")
        L.append("")
        L.append((r.get("description") or "").strip())
    else:
        L.append("- (CIViC 无基因级摘要;用语料收割或其它来源)")
    L.append("")
open(out,"w",encoding="utf-8").write("\n".join(L)+"\n")
print(f"写 {out}: {sum(1 for g in GENES if rows.get(g,{}).get('description'))}/{len(GENES)} 基因有 CIViC 摘要")
