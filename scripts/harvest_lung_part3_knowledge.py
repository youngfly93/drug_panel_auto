import zipfile, re, glob, os
GENES=["EGFR","KRAS","ALK","ROS1","BRAF","MET","RET","ERBB2","TP53","PIK3CA","STK11","KEAP1","NRAS","NTRK1","KIT"]
reports=[x for x in glob.glob("各癌种基因报告近年汇总/肺癌/*329基因+pd-l1*.docx") if "/._" not in x]
def paras_of(f):
    try: xml=zipfile.ZipFile(f).read("word/document.xml").decode("utf-8","ignore")
    except: return []
    out=[]
    for pm in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S):
        t="".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", pm.group(0), re.S))
        out.append(re.sub(r"<[^>]+>","",t).strip())
    return out
def ok(t):  # 非病人特定
    return t and "该样本检出" not in t and not re.search(r"丰度|；\s*\d+\.?\d*%", t)
H={}
for f in reports:
    ps=paras_of(f)
    for g in GENES:
        cur=H.setdefault(g,{"intro":None,"analysis":None})
        for t in ps:
            if not t.startswith(f"{g}基因") or not ok(t) or len(t)<55: continue
            mech = ("编码" in t or "原癌" in t or "抑癌" in t or "属于" in t or "是一种" in t)
            lung = ("非小细胞肺癌" in t or "NSCLC" in t or "肺癌" in t)
            if mech and not cur["intro"]: cur["intro"]=t
            if lung and not cur["analysis"]: cur["analysis"]=t
# 生成 overlay yaml
import datetime
lines=['schema_version: 1','source:','  panel: lung_329_pdl1',
       '  purpose: |-','    First-pass lung-curated Part-3 wording, HARVESTED from reviewed lung 329+PD-L1',
       '    final reports (de-identified: gene-level only, no patient variant/freq/identity).',
       '    Gene-level overrides (no c_hgvs) → apply to any variant of the gene. NEEDS report-team review.',
       '  scope: gene_level_reviewed_knowledge','  source_type: lab_reviewed_final_report_text',
       'gene_sections:']
def esc(s): return s.replace("\\","\\\\")
n=0
for g in GENES:
    h=H.get(g,{})
    intro=h.get("intro"); analysis=h.get("analysis")
    if not intro and not analysis: continue
    n+=1
    lines.append(f"- gene: {g}")
    if intro:
        lines.append("  intro: |-"); lines.append("    "+esc(intro))
    if analysis:
        lines.append("  mutation_analysis: |-"); lines.append("    "+esc(analysis))
import io
out="panels/lung_329_pdl1/rules/reviewed_part3_knowledge.yaml"
open(out,"w",encoding="utf-8").write("\n".join(lines)+"\n")
print(f"覆盖 {n}/{len(GENES)} 基因 → {out}")
for g in GENES:
    h=H.get(g,{}); print(f"  {g}: intro={'✅' if h.get('intro') else '—'} analysis={'✅' if h.get('analysis') else '—'}")
