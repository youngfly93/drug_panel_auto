# ruff: noqa: E402,I001
"""Lung588 Phase-C evidence boundary and historical-audit regression tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import yaml
from docx import Document
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.panels.loader import load_panel_package
from scripts.repair_docx_relationships import repair_docx
from scripts import validate_lung588_real_inputs


PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PANEL_DIR = ROOT / "panels" / "lung_588_pdl1"
PRE_UAT_RECORD = PANEL_DIR / "uat" / "lung588_machine_pre_uat_20260723.yaml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inject_broken_image_relationship(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        content = {item.filename: archive.read(item.filename) for item in infos}

    rels_name = "word/_rels/document.xml.rels"
    rels = etree.fromstring(content[rels_name])
    etree.SubElement(
        rels,
        f"{{{PACKAGE_REL_NS}}}Relationship",
        Id="rIdBroken",
        Type=f"{OFFICE_REL_NS}/image",
        Target="../NULL",
    )
    content[rels_name] = etree.tostring(
        rels,
        encoding="UTF-8",
        xml_declaration=True,
    )

    document = etree.fromstring(content["word/document.xml"])
    body = document.find(f"{{{WORD_NS}}}body")
    assert body is not None
    paragraph = etree.SubElement(body, f"{{{WORD_NS}}}p")
    run = etree.SubElement(paragraph, f"{{{WORD_NS}}}r")
    drawing = etree.SubElement(run, f"{{{WORD_NS}}}drawing")
    etree.SubElement(
        drawing,
        f"{{{DRAWING_NS}}}blip",
        {f"{{{OFFICE_REL_NS}}}embed": "rIdBroken"},
    )
    content["word/document.xml"] = etree.tostring(
        document,
        encoding="UTF-8",
        xml_declaration=True,
    )

    replacement = path.with_suffix(".injected.docx")
    with zipfile.ZipFile(
        replacement,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for item in infos:
            archive.writestr(item, content[item.filename])
    replacement.replace(path)


def _add_row(table, values: list[str]) -> None:
    cells = table.add_row().cells
    for cell, value in zip(cells, values):
        cell.text = value


def _synthetic_historical_report(path: Path) -> None:
    document = Document()

    cover = document.add_table(rows=1, cols=2)
    cover.cell(0, 0).text = "受控合成封面"
    cover.cell(0, 1).text = "CASE-LUNG-SYNTHETIC"

    targeted = document.add_table(rows=1, cols=4)
    for cell, value in zip(
        targeted.rows[0].cells,
        ["基因", "突变位点", "潜在获益靶向药物（证据等级）", "慎用药物"],
    ):
        cell.text = value
    _add_row(
        targeted,
        ["BRAF", "c.1799T>A，p.V600E", "达拉非尼+曲美替尼（A）", "--"],
    )

    biomarkers = document.add_table(rows=1, cols=2)
    biomarkers.cell(0, 0).text = "项目"
    biomarkers.cell(0, 1).text = "结果"
    _add_row(biomarkers, ["肿瘤突变负荷（TMB）", "6.3 mutations/Mb"])
    _add_row(biomarkers, ["微卫星不稳定性（MSI）", "MSS"])
    _add_row(biomarkers, ["PD-L1表达", "TPS 5%；CPS 6"])
    _add_row(
        biomarkers,
        ["免疫正相关基因", "检出（1个） BRAF：c.1799T>A，p.V600E"],
    )

    pgx = document.add_table(rows=1, cols=6)
    for cell, value in zip(
        pgx.rows[0].cells,
        ["药物", "基因", "检测位点", "等级", "检测结果", "用药提示"],
    ):
        cell.text = value
    _add_row(pgx, ["铂类", "ERCC1", "rs11615", "C", "CT", "历史候选说明"])

    document.add_paragraph("靶向/免疫药物用药提示解析")
    document.add_paragraph("潜在获益靶向药物解析")
    document.add_paragraph("BRAF：c.1799T>A，p.V600E突变")
    document.add_paragraph("达拉非尼+曲美替尼")
    document.add_paragraph("基因变异与药物关联分析：")
    document.add_paragraph("非小细胞肺癌研究见 PMID 28919011。")
    document.add_paragraph("3. 阅读说明")
    document.save(path)


def test_lung588_medical_candidates_are_registered_but_fail_closed():
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    candidate_path = package.resolve_rule_file("medical_candidates")
    candidates = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    runtime = yaml.safe_load(package.resolve_rule_file("drugs").read_text(encoding="utf-8"))

    assert candidates["status"] == "draft"
    governance = candidates["governance"]
    assert governance["runtime_policy"]["enabled"] is False
    assert governance["runtime_policy"]["runtime_rule_source"] is False
    assert governance["runtime_policy"]["report_text_allowed"] is False
    context_contract = governance["promotion_context_contract"]
    assert context_contract["status"] == "exposed_optional_in_engineering_draft"
    assert context_contract["runtime_enforcement"] == "not_implemented"
    assert context_contract["promotion_blocked"] is True
    assert context_contract["missing_or_uncertain_policy"] == "keep_candidate_hidden"
    assert set(context_contract["fields"]) == {
        "lung_histology",
        "disease_extent",
        "prior_systemic_therapy",
        "companion_diagnostic_status",
    }
    assert governance["historical_inventory"] == {
        "source": "two de-identified repaired historical lung588 final reports",
        "exact_targeted_event_count": 15,
        "targeted_drug_claim_count": 169,
        "historical_level_counts": {"A": 9, "B": 0, "C": 146, "D": 14},
        "selected_candidate_claim_count": 4,
        "not_migrated_claim_count": 165,
        "disposition": (
            "Historical report text is evidence of an old display contract, "
            "not current medical truth. Only the four exact-event candidates "
            "below were retained for secondary review; all other claims remain "
            "outside runtime.\n"
        ),
    }

    rules = candidates["candidate_rules"]
    assert len(rules) == 4
    assert {rule["gene"] for rule in rules} == {"BRAF", "ERBB2"}
    assert all(rule["selector"]["c_hgvs"].startswith("c.") for rule in rules)
    assert all(rule["selector"]["p_hgvs"].startswith("p.") for rule in rules)
    assert all(rule["runtime_eligible"] is False for rule in rules)
    assert all(rule["report_text_allowed"] is False for rule in rules)
    assert all(rule["review_status"] == "needs_review" for rule in rules)
    assert all(rule["secondary_review_status"] == "pending_report_group_review" for rule in rules)
    assert all(rule["source_refs"] for rule in rules)
    for rule in rules:
        required_context = set(rule["required_context_fields"])
        assert {
            "lung_histology",
            "disease_extent",
            "companion_diagnostic_status",
        } <= required_context
        if rule["gene"] == "ERBB2":
            assert "prior_systemic_therapy" in required_context

    candidate_events = {
        (
            rule["gene"],
            rule["selector"]["c_hgvs"],
            rule["selector"]["p_hgvs"],
        )
        for rule in rules
    }
    assert ("BRAF", "c.1781A>G", "p.D594G") not in candidate_events
    candidate_drugs = {rule["therapy"]["generic_name_zh"] for rule in rules}
    assert not {"宗艾替尼", "恩美曲妥珠单抗", "吡咯替尼"} & candidate_drugs

    assert runtime["targeted_drug_rules"]["enabled"] is False
    assert runtime["targeted_drug_rules"]["base_db_enabled"] is False
    assert runtime["targeted_drug_rules"]["allowed_source_dbs"] == []
    assert runtime["approved_drug_rows"] == []
    assert candidates["non_target_domains"]["immune_gene_associations"]["enabled"] is False
    assert candidates["non_target_domains"]["chemotherapy_pharmacogenomics"]["enabled"] is False

    if runtime["targeted_drug_rules"]["enabled"]:
        assert context_contract["runtime_enforcement"] == "implemented"
        assert context_contract["promotion_blocked"] is False


def test_docx_relationship_repair_preserves_source_and_removes_orphan(tmp_path):
    source = tmp_path / "CASE-LUNG-SYNTHETIC.reference.docx"
    output = tmp_path / "CASE-LUNG-SYNTHETIC.repaired.docx"
    document = Document()
    document.add_paragraph("synthetic content")
    document.save(source)
    _inject_broken_image_relationship(source)
    before = _sha256(source)

    result = repair_docx(source, output)

    assert _sha256(source) == before
    assert result["source_sha256"] == before
    assert result["removed_reference_nodes"] == 1
    assert result["removed_relationships"] == [
        {
            "relation_id": "rIdBroken",
            "relationship_type": "image",
            "reason": "null_target",
        }
    ]
    assert Document(output).paragraphs[0].text == "synthetic content"
    with zipfile.ZipFile(output) as archive:
        assert b"rIdBroken" not in archive.read("word/document.xml")
        assert b"rIdBroken" not in archive.read("word/_rels/document.xml.rels")


def test_historical_semantic_audit_emits_deidentified_nonruntime_inventory(tmp_path):
    reference = tmp_path / "CASE-LUNG-SYNTHETIC.reference.docx"
    contract = tmp_path / "case_lung_synthetic.yaml"
    output_dir = tmp_path / "audit"
    _synthetic_historical_report(reference)
    contract.write_text(
        yaml.safe_dump(
            {
                "tables": {
                    "all_variants": {
                        "rows": [
                            {
                                "match": {
                                    "gene": {"equals": "BRAF"},
                                    "cHGVS": {"equals": "c.1799T>A"},
                                },
                                "expect": {"pHGVS": {"equals": "p.V600E"}},
                            }
                        ]
                    }
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_lung588_historical_semantics.py"),
            "--reference",
            f"CASE-LUNG-SYNTHETIC={reference}",
            "--contract",
            f"CASE-LUNG-SYNTHETIC={contract}",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary == {
        "status": "PASS",
        "cases": 1,
        "targeted_candidates": 1,
        "immune_observations": 1,
        "pgx_observations": 1,
        "output": "semantic_inventory.json",
    }
    inventory = json.loads((output_dir / "semantic_inventory.json").read_text(encoding="utf-8"))
    case = inventory["cases"]["CASE-LUNG-SYNTHETIC"]
    assert case["contract_check"]["status"] == "PASS"
    assert case["pgx_observation_count"] == 1
    assert inventory["cross_case"]["targeted_candidate_count"] == 1

    emitted = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output_dir.iterdir()
        if path.suffix in {".json", ".tsv"}
    )
    assert "runtime_eligible\tFalse" not in emitted
    assert "\tFalse\tpending_report_group_review" in emitted
    assert "姓名" not in emitted
    assert "报告编号" not in emitted
    assert "LZ258" not in emitted


def test_real_input_validator_reads_quiet_release_revision(tmp_path, monkeypatch):
    revision = "1" * 40
    (tmp_path / "REVISION").write_text(f"{revision}\n", encoding="utf-8")
    monkeypatch.setattr(validate_lung588_real_inputs, "ROOT", tmp_path)

    assert validate_lung588_real_inputs._source_revision() == revision


def test_real_input_validator_handles_empty_release_revision(tmp_path, monkeypatch):
    (tmp_path / "REVISION").write_text("", encoding="utf-8")
    monkeypatch.setattr(validate_lung588_real_inputs, "ROOT", tmp_path)

    assert validate_lung588_real_inputs._source_revision() == ""


def test_lung588_machine_pre_uat_is_traceable_and_does_not_overclaim():
    record = yaml.safe_load(PRE_UAT_RECORD.read_text(encoding="utf-8"))

    assert record["status"] == "partial_not_release_eligible"
    assert record["source_commit"] == ("c23e9f044c55102c0c0d58217fe3efd2f3ccdc88")
    assert record["environment"]["host_alias"] == "iyun129"
    assert record["environment"]["production_switched"] is False
    assert record["environment"]["production_health_after_test"] == "PASS"
    assert record["release_requirements"] == {
        "required_real_case_count": 10,
        "machine_executed_real_case_count": 3,
        "machine_pass_count": 3,
        "machine_observed_pass_rate": 1.0,
        "report_group_reviewed_case_count": 0,
        "formal_uat_requirement_met": False,
        "p0_count_in_observed_cases": 0,
    }

    cases = record["cases"]
    assert [case["alias"] for case in cases] == [
        "CASE-LUNG-A",
        "CASE-LUNG-B",
        "CASE-LUNG-C",
    ]
    assert [case["report_variant_count"] for case in cases] == [7, 8, 9]
    assert all(case["biomarker_contract_status"] == "PASS" for case in cases)
    assert all(case["targeted_drug_runtime_row_count"] == 0 for case in cases)
    assert all(case["report_qa_status"] == "PASS" for case in cases)
    assert all(case["page_count"] == 27 for case in cases)
    assert all(case["blank_page_count"] == 0 for case in cases)
    assert all(case["unexpected_low_content_page_count"] == 0 for case in cases)
    assert all(case["content_failure_count"] == 0 for case in cases)
    assert len(record["remaining_blockers"]) >= 4
