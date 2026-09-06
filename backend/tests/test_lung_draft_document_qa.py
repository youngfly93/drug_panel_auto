"""Native TOC and historical appendix boundaries; synthetic documents only."""

import pytest
from docx import Document
from docx.oxml import parse_xml
from reportgen.core.qa_report import _build_business_checks, _inspect_toc, _read_part3_text
from reportgen.core.template_bridge_358 import load_panel_config
from reportgen.panels.loader import load_panel_package
from scripts.validate_lung_small_panel_drafts import inspect_word_scope

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def native_toc(tmp_path, pages=(1, 2), target="section", closed=True):
    document = Document()
    entries = "".join(
        '<w:p><w:hyperlink w:anchor="section"><w:r><w:t>检测项目 62</w:t></w:r>'
        + (f"<w:r><w:tab/><w:t>{page}</w:t></w:r>" if page is not None else "")
        + "</w:hyperlink></w:p>"
        for page in pages
    )
    block = parse_xml(
        f'<w:sdt xmlns:w="{W}"><w:sdtContent><w:p><w:r><w:instrText>'
        ' TOC \\o "1-3" \\h </w:instrText></w:r></w:p>' + entries + "</w:sdtContent></w:sdt>"
    )
    document._element.body.insert(0, block)
    anchor = document.add_paragraph("正文")._p
    anchor.append(parse_xml(f'<w:bookmarkStart xmlns:w="{W}" w:id="7" w:name="{target}"/>'))
    if closed:
        anchor.append(parse_xml(f'<w:bookmarkEnd xmlns:w="{W}" w:id="7"/>'))
    path = tmp_path / "native.docx"
    document.save(path)
    return path


def test_native_sdt_toc_reads_all_cached_pages(tmp_path):
    path = native_toc(tmp_path)
    assert all("检测项目" not in p.text for p in Document(path).paragraphs)
    result = _inspect_toc([], output_path=path)
    assert result["mode"] == "native_TOC"
    assert result["status"] == "PASS"
    assert result["page_numbered_line_count"] == result["line_count"] == 2


@pytest.mark.parametrize("pages", [(None,), (1, None), (0,), (-1,)])
def test_native_toc_missing_pages_never_pass_from_heading_numbers(tmp_path, pages):
    result = _inspect_toc([], output_path=native_toc(tmp_path, pages=pages))
    assert result["status"] == "WARN"


@pytest.mark.parametrize("target,closed", [("wrong", True), ("section", False)])
def test_native_toc_broken_or_unclosed_bookmarks_fail(tmp_path, target, closed):
    result = _inspect_toc([], output_path=native_toc(tmp_path, target=target, closed=closed))
    assert result["status"] == "FAIL"
    assert result["missing_bookmarks"] or result["unclosed_bookmarks"]


@pytest.mark.parametrize("unsafe_inside", [False, True])
def test_family_specific_part3_bounds_exclude_only_fixed_appendix(unsafe_inside):
    document = Document()
    document.add_paragraph("结直肠癌：章节外的固定文献")
    document.add_paragraph("第二部分：检测结果解析")
    document.add_paragraph("结直肠癌错误解析" if unsafe_inside else "肺癌安全解析")
    document.add_paragraph("附录：基因介绍")
    document.add_paragraph("结直肠癌：附录固定文献")
    policy = {
        "enabled": True,
        "scan_scope": "part3",
        "terms": ["结直肠癌"],
        "start_heading": "第二部分：检测结果解析",
        "end_heading": "附录：基因介绍",
    }
    section = _read_part3_text(document, policy)
    assert "固定文献" not in section
    check = _build_business_checks(
        "结直肠癌", {"part3_cross_cancer_residual_scan": policy}, "lung_13", section
    )["part3_cross_cancer_residuals"]
    assert check["status"] == ("WARN" if unsafe_inside else "PASS")


def test_missing_configured_part3_heading_keeps_full_document_fallback():
    document = Document()
    document.add_paragraph("结直肠癌未分节的错误解析")
    assert _read_part3_text(document, {"start_heading": "不存在的标题"}) is None


@pytest.mark.parametrize("tamper", [None, "gene", "guideline", "pgx"])
def test_final_word_scope_detects_missing_genes_guidelines_and_changed_pgx(tamper):
    package = load_panel_package("lung_13")
    config = load_panel_config(panel_package=package)
    context = {
        "lung_guideline_drug_results": [
            {
                "gene": row.get("display") or "/".join(row["genes"]),
                "drugs": row["drugs"],
                "clinical_note": row["clinical_note"],
                "result": "未检出",
            }
            for row in config.lung_guideline_drug_rows
        ],
        "drug_shunbo": [
            {
                "DrugDisplay": "合成药物",
                "Gene": "合成基因",
                "Locus": "rsTEST",
                "Level": "1B",
                "Genotype": "AA",
                "Result": "合成来源结果",
            }
        ],
    }
    document = Document()
    genes = document.add_table(rows=1, cols=1)
    genes.cell(0, 0).text = "肺癌13基因检测列表"
    for gene in sorted(config.crc_important_genes):
        genes.add_row().cells[0].text = gene
    guide = document.add_table(rows=1, cols=4)
    for cell, value in zip(
        guide.rows[0].cells, ["检测基因", "本癌种相关治疗药物", "临床提示", "检测结果"]
    ):
        cell.text = value
    for row in context["lung_guideline_drug_results"]:
        for cell, key in zip(guide.add_row().cells, ["gene", "drugs", "clinical_note", "result"]):
            cell.text = row[key]
    pgx = document.add_table(rows=1, cols=6)
    for cell, value in zip(
        pgx.rows[0].cells, ["合成药物", "基因", "检测位点", "等级", "检测结果", "用药提示"]
    ):
        cell.text = value
    for cell, key in zip(
        pgx.add_row().cells, ["DrugDisplay", "Gene", "Locus", "Level", "Genotype", "Result"]
    ):
        cell.text = context["drug_shunbo"][0][key]
    if tamper == "gene":
        genes.cell(1, 0).text = "UNASSAYED"
    elif tamper == "guideline":
        guide._tbl.remove(guide.rows[-1]._tr)
    elif tamper == "pgx":
        pgx.cell(1, 5).text = "与来源不符"
    result = inspect_word_scope(document, context, package)
    assert bool(result["failures"]) is (tamper is not None)
