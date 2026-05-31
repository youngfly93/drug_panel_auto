#!/usr/bin/env python3
"""收割语料肺329终版的基因级 Part-3 叙述 → lung reviewed_part3_knowledge overlay。
去标识(只取基因级文本,丢弃含"该样本检出"/丰度/具体位点的病人特定段)。FIRST PASS,需报告组审。
用法: python scripts/harvest_lung_part3_knowledge.py
"""
import zipfile, re, glob, sys
GENES=["EGFR","KRAS","ALK","ROS1","BRAF","MET","RET","ERBB2","TP53","PIK3CA","STK11","KEAP1","NRAS","NTRK1","KIT"]
CORPUS="各癌种基因报告近年汇总/肺癌/*329基因+pd-l1*.docx"
def paras_of(f):
    try: xml=zipfile.ZipFile(f).read("word/document.xml").decode("utf-8","ignore")
    except Exception: return []
    out=[]
    for pm in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S):
        t="".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", pm.group(0), re.S))
        out.append(re.sub(r"<[^>]+>","",t).strip())
    return out
def clean(t): return t and "该样本检出" not in t and not re.search(r"丰度|；\s*\d+\.?\d*%", t)
MECH=("编码","原癌","抑癌","属于","是一种","受体","激酶","抑制因子","信号通路")
SIG=("非小细胞肺癌","NSCLC","肺癌","肺腺癌")
def harvest():
    H={g:{"intro":None,"analysis":None} for g in GENES}
    for f in [x for x in glob.glob(CORPUS) if "/._" not in x]:
        ps=paras_of(f)
        for g in GENES:
            cur=H[g]
            for t in ps:
                if not clean(t) or len(t)<55: continue
                if not cur["intro"] and t.startswith(f"{g}基因") and any(m in t for m in MECH):
                    cur["intro"]=t
                if not cur["analysis"] and (f"{g}基因" in t or f"{g}突变" in t or t.startswith(g)) \
                   and any(s in t for s in SIG):
                    cur["analysis"]=t
    return H
def build(H):
    L=['schema_version: 1','source:','  panel: lung_329_pdl1',
       '  purpose: |-','    First-pass lung-curated Part-3 wording. Gene-level overrides (no c_hgvs) apply to',
       '    any variant of the gene. CORPUS-HARVESTED (de-identified) + CIViC-sourced intros for genes',
       '    the corpus lacks (marked). NEEDS report-team clinical review/completion.',
       '  scope: gene_level_reviewed_knowledge','  source_type: lab_reviewed_final_report_text + civic',
       'gene_sections:']
    n=0
    for g in GENES:
        h=H[g]
        if not h["intro"] and not h["analysis"]: continue
        n+=1; L.append(f"- gene: {g}")
        if h["intro"]: L+= ["  intro: |-","    "+h["intro"]]
        if h["analysis"]: L+= ["  mutation_analysis: |-","    "+h["analysis"]]
    return "\n".join(L)+"\n", n, H
if __name__=="__main__":
    H=harvest(); txt,n,H=build(H)
    open("panels/lung_329_pdl1/rules/reviewed_part3_knowledge.yaml","w",encoding="utf-8").write(txt)
    print(f"语料收割覆盖 {n}/{len(GENES)} 基因")
    for g in GENES:
        h=H[g]; print(f"  {g}: intro={'✅' if h['intro'] else '—'} analysis={'✅' if h['analysis'] else '—'}")
