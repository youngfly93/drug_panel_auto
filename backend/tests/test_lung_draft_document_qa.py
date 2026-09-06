"""Native TOC and historical appendix boundaries; synthetic documents only."""

import pytest
from docx import Document
from docx.oxml import parse_xml
from reportgen.core.legacy_reference import (
    _extract_features,
    _section_presence,
    snapshot_docx_report,
)
from reportgen.core.qa_report import _build_business_checks, _inspect_toc, _read_part3_text
from reportgen.core.template_bridge_358 import load_panel_config
from reportgen.core.template_renderer import TemplateRenderer
from reportgen.docx_sections import find_reference_section_bounds
from reportgen.panels.loader import load_panel_package
from scripts.build_lung_draft_packages import install_refreshable_toc
from scripts.validate_lung_small_panel_drafts import inspect_word_scope

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@pytest.mark.parametrize("phrase", ["本次共检出体细胞变异：4个", "本次检出体细胞变异：4 个"])
def test_snapshot_counts_both_reviewed_summary_wordings(phrase):
    assert _extract_features(phrase, tables=[])["total_variants_count"] == 4
    assert _extract_features("本次检出其他基因：13个", tables=[])["total_variants_count"] is None


def test_panel_section_aliases_do_not_weaken_other_panel_or_missing_section(tmp_path):
    document = Document()
    document.add_paragraph("补充检测结果：TMB、MSI 与化疗药物基因组学")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "基因突变信息"
    path = tmp_path / "synthetic-sections.docx"
    document.save(path)
    aliases = {
        "variant_summary": ["基因突变信息"],
        "biomarkers": ["补充检测结果：TMB、MSI 与化疗药物基因组学"],
    }
    plain = snapshot_docx_report(path, panel="crc_358_msi")["section_presence"]
    scoped = snapshot_docx_report(path, panel="lung_62", section_aliases=aliases)[
        "section_presence"
    ]
    assert not plain["variant_summary"] and not plain["biomarkers"]
    assert scoped["variant_summary"] and scoped["biomarkers"]
    assert not scoped["gene_list"]
    assert not _section_presence("实际章节缺失", aliases)["biomarkers"]


@pytest.mark.parametrize("values", [[], [""], "任意字符串", [False]])
def test_empty_or_malformed_section_alias_cannot_match_every_document(values):
    with pytest.raises(ValueError):
        _section_presence("无相应章节", {"biomarkers": values})


@pytest.mark.parametrize(
    "boundary",
    ["第三部分：附录", "5. 附录", "补充检测结果：TMB、MSI 与化疗药物基因组学"],
)
def test_reference_cleanup_never_deletes_following_lung_modules(tmp_path, boundary):
    document = Document()
    for value in (
        "检测结果解析",
        "参考文献",
        "合成旧文献",
        boundary,
        "CNV待复核：合成来源待审",
        "固定附录保留",
    ):
        document.add_paragraph(value)
    document.add_table(rows=1, cols=1).cell(0, 0).text = "合成 PGx 行"
    assert find_reference_section_bounds(document.paragraphs) == (1, 3)
    path = tmp_path / "reference-boundary.docx"
    document.save(path)
    TemplateRenderer(log_level="ERROR")._rebuild_reference_section(str(path), {})
    actual = Document(path)
    text = "\n".join(p.text for p in actual.paragraphs)
    assert boundary in text and "CNV待复核：合成来源待审" in text and "固定附录保留" in text
    assert "合成旧文献" not in text
    assert actual.tables[0].cell(0, 0).text == "合成 PGx 行"


def test_flat_historical_toc_becomes_refreshable_without_old_page_numbers(tmp_path):
    document = Document()
    document.styles.add_style("toc 1", 1)
    document.add_paragraph("目录")
    labels = ["第一部分：检测结果", "第二部分：结果解析", "第三部分：附录"]
    for label, page in zip(labels, [42, 56, 99]):
        document.add_paragraph(label + "\t" + str(page), style="toc 1")
    body = [document.add_paragraph(label) for label in labels]
    install_refreshable_toc(document)
    assert all("\t" not in p.text for p in document.paragraphs)
    assert all('w:outlineLvl w:val="0"' in p._p.xml for p in body)
    assert " TOC " in document.element.xml
    path = tmp_path / "converted-toc.docx"
    document.save(path)
    # Empty cache must still fail the page-number check until real LO refresh.
    assert _inspect_toc([], output_path=path)["status"] == "WARN"


def test_empty_b_family_toc_uses_actual_major_headings():
    document = Document()
    document.add_paragraph("目    录")
    labels = ["第一部分：基本信息", "第二部分：检测结果", "第三部分：结果解析", "第四部分：附录"]
    for label in labels:
        document.add_paragraph(label)
    install_refreshable_toc(document)
    assert " TOC " in document.element.xml
    assert [p.text for p in document.paragraphs[1:]] == labels


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
