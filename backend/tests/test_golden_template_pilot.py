import importlib.util
import sys
from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.services.reportgen_bridge import ReportGenBridge  # noqa: E402
from reportgen.core.report_generator import ReportGenerator  # noqa: E402
from reportgen.panels.loader import load_panel_package  # noqa: E402
from reportgen.panels.validation import validate_panel_package  # noqa: E402


def _load_seed_builder():
    path = ROOT / "scripts" / "build_golden_template_seed.py"
    spec = importlib.util.spec_from_file_location("build_golden_template_seed", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_variableizer():
    path = ROOT / "scripts" / "variableize_golden_template.py"
    spec = importlib.util.spec_from_file_location("variableize_golden_template", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_crc358_golden_template_declares_template_level_processors():
    package = load_panel_package("crc_358_msi", project_root=ROOT)
    template = package.templates["crc_358_msi_golden_template_v0"]

    assert template.status == "pilot"
    assert template.processors == (
        "blank_page_cleanup",
        "toc_refresh",
        "final_refresh_cleanup",
    )
    assert package.resolve_template_file(template.template_id).exists()

    report = validate_panel_package("crc_358_msi", project_root=ROOT)
    assert report.ok, report.to_dict()


def test_web_bridge_resolves_panel_template_id():
    bridge = ReportGenBridge(
        config_dir=str(ROOT / "config"),
        template_dir=str(ROOT / "templates"),
    )

    resolved = Path(
        bridge._resolve_template_path(
            "crc_358_msi_golden_template_v0",
            "crc_358_msi",
        )
    )

    assert resolved.name == "crc_358_msi_golden_template_v0.docx"
    assert resolved.exists()
    assert "panels/crc_358_msi/templates" in resolved.as_posix()


def test_report_generator_uses_template_level_processors():
    package = load_panel_package("crc_358_msi", project_root=ROOT)
    template_path = package.resolve_template_file("crc_358_msi_golden_template_v0")

    processors = ReportGenerator._get_template_processor_names(
        package,
        str(template_path),
    )

    assert processors == (
        "blank_page_cleanup",
        "toc_refresh",
        "final_refresh_cleanup",
    )


def test_golden_seed_builder_scrubs_patient_tokens(tmp_path):
    builder = _load_seed_builder()
    source = tmp_path / "source.docx"
    output = tmp_path / "seed.docx"
    doc = Document()
    doc.add_paragraph("33333333333333333333333333")
    doc.add_paragraph("姓名：黄金测试患者")
    report_no = doc.add_paragraph("报告编号：")
    report_no.add_run("TEST")
    report_no.add_run("-")
    report_no.add_run("REPORT001")
    sample_no = doc.add_paragraph("样本号：")
    sample_no.add_run("SAMPLE")
    sample_no.add_run("001")
    doc.add_paragraph("临床诊断：测试诊断")
    report_date = doc.add_paragraph("报告日期：")
    report_date.add_run("2099")
    report_date.add_run(".12.")
    report_date.add_run("31")
    doc.save(source)
    replacements = {
        "黄金测试患者": "{{ patient_name }}",
        "TEST-REPORT001": "{{ report_number }}",
        "SAMPLE001": "{{ sample_id }}",
        "测试诊断": "{{ clinical_diagnosis }}",
        "2099.12.31": "{{ report_date }}",
    }

    manifest = builder.build_seed(
        source,
        output,
        replacements=replacements,
        protected_tokens=tuple(replacements),
        allow_commit_output=False,
        allow_residual=False,
        project_root=ROOT,
    )

    assert manifest["success"] is True
    assert output.exists()
    assert all(
        count == 0
        for count in manifest["protected_token_residual_counts"].values()
    )
    text = "\n".join(p.text for p in Document(output).paragraphs)
    assert "{{ patient_name }}" in text
    assert "{{ sample_id }}" in text
    assert "{{ report_number }}" in text
    assert "{{ clinical_diagnosis }}" in text
    assert "{{ report_date }}" in text
    assert "333333333333" not in text
    assert manifest["removed_debug_markers"] == 1


def test_golden_template_variableizer_applies_structural_map(tmp_path):
    variableizer = _load_variableizer()
    source = tmp_path / "seed.docx"
    output = tmp_path / "variableized.docx"

    doc = Document()
    table = doc.add_table(rows=3, cols=2)
    table.rows[0].cells[0].text = "姓名："
    table.rows[0].cells[1].text = "黄金测试患者"
    table.rows[1].cells[0].text = "性别："
    table.rows[1].cells[1].text = "男"
    table.rows[2].cells[0].text = "静态行"
    table.rows[2].cells[1].text = "删除我"
    loop_table = doc.add_table(rows=4, cols=3)
    loop_table.rows[0].cells[0].text = "基因"
    loop_table.rows[0].cells[1].text = "位点"
    loop_table.rows[0].cells[2].text = "说明"
    loop_table.rows[1].cells[0].text = "KRAS"
    loop_table.rows[1].cells[1].text = "c.34G>A"
    loop_table.rows[1].cells[2].text = "保留样式"
    loop_table.rows[2].cells[0].text = "TP53"
    loop_table.rows[2].cells[1].text = "c.844C>T"
    loop_table.rows[2].cells[2].text = "删除我"
    loop_table.rows[3].cells[0].text = "ATM"
    loop_table.rows[3].cells[1].text = "c.6874C>T"
    loop_table.rows[3].cells[2].text = "删除我"
    doc.add_paragraph("本次共检出体细胞变异：8个。")
    doc.add_paragraph("3.1 肿瘤突变负荷（TMB）水平提示")
    doc.add_paragraph("在本次检测范围内，该样本肿瘤突变负荷为6.5 mutations/Mb。")
    doc.add_paragraph("TMB科普说明。")
    doc.save(source)

    manifest = variableizer.variableize_docx(
        source,
        output,
        {
            "template_id": "unit_test",
            "cell_variables": [
                {"table": 0, "row": 0, "col": 1, "variable": "patient_name"},
                {"table": 0, "row": 1, "col": 1, "variable": "gender"},
            ],
            "paragraph_variables": [
                {
                    "after_heading": "3.1 肿瘤突变负荷（TMB）水平提示",
                    "nonempty_offset": 1,
                    "variable": "tmb_detail_sentence",
                }
            ],
            "paragraph_templates": [
                {
                    "contains": "本次共检出体细胞变异",
                    "text": "本次共检出体细胞变异：{{ total_variants_count }}个。",
                }
            ],
            "table_loops": [
                {
                    "id": "variants",
                    "table": 1,
                    "collection": "variants",
                    "alias": "row",
                    "template_row": 1,
                    "insert_at": 1,
                    "remove_from": 1,
                    "remove_to": "end",
                    "columns": ["gene", "locus", "中文键"],
                }
            ],
        },
    )

    out_doc = Document(output)
    assert manifest["success"] is True
    assert manifest["operation_count"] == 5
    assert out_doc.tables[0].rows[0].cells[1].text == "{{ patient_name }}"
    assert out_doc.tables[0].rows[1].cells[1].text == "{{ gender }}"
    assert "total_variants_count" in "\n".join(p.text for p in out_doc.paragraphs)
    loop_rows = out_doc.tables[1].rows
    assert [cell.text for cell in loop_rows[1].cells] == [
        "{%tr for row in variants %}",
        "",
        "",
    ]
    assert [cell.text for cell in loop_rows[2].cells] == [
        "{{ row.gene }}",
        "{{ row.locus }}",
        '{{ row["中文键"] }}',
    ]
    assert [cell.text for cell in loop_rows[3].cells] == [
        "{%tr endfor %}",
        "",
        "",
    ]
    assert "{{ tmb_detail_sentence }}" in [p.text for p in out_doc.paragraphs]

    rendered = tmp_path / "rendered.docx"
    template = DocxTemplate(output)
    template.render(
        {
            "patient_name": "张三",
            "gender": "男",
            "tmb_detail_sentence": "TMB 渲染段落",
            "variants": [
                {"gene": "KRAS", "locus": "c.34G>A", "中文键": "A"},
                {"gene": "TP53", "locus": "c.844C>T", "中文键": "B"},
            ],
        }
    )
    template.save(rendered)
    rendered_doc = Document(rendered)
    assert [cell.text for cell in rendered_doc.tables[1].rows[1].cells] == [
        "KRAS",
        "c.34G>A",
        "A",
    ]
    assert [cell.text for cell in rendered_doc.tables[1].rows[2].cells] == [
        "TP53",
        "c.844C>T",
        "B",
    ]
