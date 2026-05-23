import json
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for import_path in (str(ROOT), str(BACKEND)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from reportgen.core.legacy_reference import (  # noqa: E402
    LegacySnapshotOptions,
    build_legacy_reference_snapshots,
)


def test_legacy_reference_snapshot_redacts_patient_identifiers(tmp_path):
    source_dir = tmp_path / "legacy"
    source_dir.mkdir()
    docx_path = source_dir / "张三-直肠癌-结直肠癌301基因+msi-mljy-lz123456-终版.docx"
    doc = Document()
    doc.add_paragraph("结直肠癌301基因+MSI检测报告")
    doc.add_paragraph("姓名：张三")
    doc.add_paragraph("样本编号：LZ123456")
    doc.add_paragraph("报告编号：MLJY-LZ123456")
    doc.add_paragraph("报告日期：2025.12.12")
    doc.add_paragraph("本次共检出体细胞变异：2个")
    doc.add_paragraph("与靶向药物用药相关的变异有：1个")
    doc.add_paragraph("6.5 mutations/Mb，TMB-L")
    doc.add_paragraph("微卫星稳定型，MSS")
    doc.add_paragraph("致您的一封信")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "基因"
    table.rows[0].cells[1].text = "突变位点"
    table.rows[1].cells[0].text = "ERBB2"
    table.rows[1].cells[1].text = "c.1979G>A"
    doc.save(docx_path)

    result = build_legacy_reference_snapshots(
        LegacySnapshotOptions(
            panel="crc_301_msi",
            source_dir=str(source_dir),
            output_dir=str(tmp_path / "snapshots"),
            sample_count=1,
        )
    )

    assert result["status"] == "PASS"
    assert result["selected_count"] == 1
    assert result["readable_docx_count"] == 1
    assert result["read_error_count"] == 0
    manifest = json.loads(Path(result["manifest_file"]).read_text(encoding="utf-8"))
    assert manifest["source_dir"] == "<redacted>"
    assert manifest["selected_samples"][0]["features"]["total_variants_count"] == 2
    sample_path = Path(result["output_dir"]) / "samples" / "crc_301_msi_legacy_ref_001.json"
    payload = sample_path.read_text(encoding="utf-8")
    assert "张三" not in payload
    assert "LZ123456" not in payload
    assert "MLJY-LZ123456" not in payload
    assert "2025.12.12" not in payload
    assert "<PATIENT_NAME>" in payload
    assert "<SAMPLE_ID>" in payload
    assert "<REPORT_ID>" in payload
    assert "<DATE>" in payload
