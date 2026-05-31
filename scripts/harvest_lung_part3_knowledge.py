#!/usr/bin/env python3
"""收割语料肺329终版 → lung reviewed_part3_knowledge overlay。
- gene_sections(基因机制intro/解析mutation_analysis): 不加CRC过滤(保留肺analysis)
- drug_sections(药物关联, benefit+caution): 加CRC过滤(排除提结直肠的药物段)
均基因级、去标识。FIRST PASS,需报告组审。用法: python scripts/harvest_lung_part3_knowledge.py
"""
import zipfile, re, glob
GENES=["EGFR","KRAS","ALK","ROS1","BRAF","MET","RET","ERBB2","TP53","PIK3CA","STK11","KEAP1","NRAS","NTRK1","KIT"]
CORPUS="各癌种基因报告近年汇总/肺癌/*329基因+pd-l1*.docx"
def paras_of(f):
    try: xml=zipfile.ZipFile(f).read("word/document.xml").decode("utf-8","ignore")
    except Exception: return []
    return [re.sub(r"<[^>]+>","","".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>",pm.group(0),re.S))).strip()
            for pm in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S)]
def clean(t): return t and "该样本检出" not in t and not re.search(r"丰度|；\s*\d+\.?\d*%", t)
def nocrc(t): return not re.search(r"结直肠|结肠癌|直肠癌", t)
MECH=("编码","原癌","抑癌","属于","是一种","受体","激酶","抑制因子","信号通路")
SIG=("非小细胞肺癌","NSCLC","肺癌","肺腺癌")
BEN=("一线","推荐","获益","敏感","首选","有效","PFS","ORR","缓解")
CAU=("耐药","不敏感","慎用","无效","原发耐药","继发耐药","不推荐")
def harvest():
    H={g:{"intro":None,"analysis":None,"benefit":[],"caution":[]} for g in GENES}
    for f in [x for x in glob.glob(CORPUS) if "/._" not in x]:
        ps=paras_of(f)
        for g in GENES:
            cur=H[g]
            for t in ps:
                if not clean(t) or len(t)<55 or f"{g}" not in t: continue
                if not cur["intro"] and t.startswith(f"{g}基因") and any(m in t for m in MECH):
                    cur["intro"]=t
                if not cur["analysis"] and (f"{g}基因" in t or t.startswith(g)) and any(s in t for s in SIG):
                    cur["analysis"]=t
                if not any(s in t for s in SIG) or not nocrc(t): continue
                if len(cur["benefit"])<2 and any(k in t for k in BEN) and t not in cur["benefit"] and t!=cur["analysis"]:
                    cur["benefit"].append(t)
                elif len(cur["caution"])<2 and any(k in t for k in CAU) and t not in cur["caution"] and t!=cur["analysis"]:
                    cur["caution"].append(t)
    return H
def build(H):
    L=['schema_version: 1','source:','  panel: lung_329_pdl1',
       '  purpose: |-','    First-pass lung-curated Part-3 (gene_sections=机制/解析, drug_sections=药物关联 benefit/caution),',
       '    gene-level(no c_hgvs)→覆盖该基因任意变异。Corpus-harvested(de-identified, drug段已去结直肠)+',
       '    CIViC参考(civic_gene_reference.md)。NEEDS report-team clinical review.',
       '  scope: gene_level_reviewed_knowledge','  source_type: lab_reviewed_final_report_text','gene_sections:']
    ng=0
    for g in GENES:
        h=H[g]
        if not h["intro"] and not h["analysis"]: continue
        ng+=1; L.append(f"- gene: {g}")
        if h["intro"]: L+=["  intro: |-","    "+h["intro"]]
        if h["analysis"]: L+=["  mutation_analysis: |-","    "+h["analysis"]]
    L.append("drug_sections:"); nd=0
    for g in GENES:
        for dt,key in (("benefit","benefit"),("caution","caution")):
            paras=H[g][key]
            if not paras: continue
            nd+=1
            L.append(f"- gene: {g}"); L.append(f"  type: {dt}")
            L.append(f"  drug_name: 见下述肺癌相关用药"); L.append("  clinical: |-")
            for p in paras: L.append("    "+p)
    return "\n".join(L)+"\n", ng, nd
if __name__=="__main__":
    H=harvest(); txt,ng,nd=build(H)
    open("panels/lung_329_pdl1/rules/reviewed_part3_knowledge.yaml","w",encoding="utf-8").write(txt)
    print(f"gene_sections {ng}/15 | drug_sections {nd}")
