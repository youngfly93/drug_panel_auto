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

from reportgen.core.field_mapper import FieldMapper
from reportgen.core.template_bridge_358 import _variant_override_matches
from reportgen.knowledge.quality import profile_panel_runtime_content
from reportgen.knowledge.release_gate import run_knowledge_release_gate
from reportgen.panels.loader import load_panel_package
from reportgen.rules.targeted_drugs import (
    evaluate_required_clinical_context,
    load_targeted_drug_rule_context,
    reviewed_variant_selector_specificity,
)
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
    assert context_contract["contract_rule"] == "clinical_context"
    assert context_contract["runtime_enforcement"] == "implemented_fail_closed"
    assert context_contract["promotion_blocked"] is True
    assert context_contract["missing_or_uncertain_policy"] == "keep_candidate_hidden"
    runtime_context = yaml.safe_load(
        package.resolve_rule_file("clinical_context").read_text(encoding="utf-8")
    )["clinical_context_contract"]
    assert set(runtime_context["fields"]) == {
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
    assert all(
        rule["selector"]["transcript"].startswith("NM_") for rule in rules
    )
    assert all(rule["runtime_eligible"] is False for rule in rules)
    assert all(rule["report_text_allowed"] is False for rule in rules)
    assert all(rule["review_status"] == "needs_review" for rule in rules)
    assert all(rule["secondary_review_status"] == "pending_report_group_review" for rule in rules)
    assert all(rule["source_refs"] for rule in rules)
    for rule in rules:
        required_context = set(rule["required_context_fields"])
        assert set(rule["context_requirements"]) == required_context
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
    assert runtime["targeted_drug_rules"]["clinical_context_rule"] == "clinical_context"
    assert runtime["approved_drug_rows"] == []
    assert runtime["governance"]["schema_version"] == "1.0"
    assert (
        runtime["governance"]["defaults"]["targeted_drug"]["runtime_eligible"]
        is False
    )
    assert candidates["non_target_domains"]["immune_gene_associations"]["enabled"] is False
    assert candidates["non_target_domains"]["chemotherapy_pharmacogenomics"]["enabled"] is False

    if runtime["targeted_drug_rules"]["enabled"]:
        assert context_contract["runtime_enforcement"] == "implemented_fail_closed"
        assert context_contract["promotion_blocked"] is False


def test_lung588_candidate_context_evaluator_rejects_missing_uncertain_and_out_of_scope():
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    candidates = yaml.safe_load(
        package.resolve_rule_file("medical_candidates").read_text(encoding="utf-8")
    )
    contract = yaml.safe_load(
        package.resolve_rule_file("clinical_context").read_text(encoding="utf-8")
    )["clinical_context_contract"]
    rules = {rule["candidate_id"]: rule for rule in candidates["candidate_rules"]}
    braf = rules["lung588_braf_v600e_dabrafenib_trametinib"]
    erbb2 = rules["lung588_erbb2_g660d_trastuzumab_deruxtecan"]

    braf_context = {
        "lung_histology": "非小细胞肺癌",
        "disease_extent": "转移性",
        "companion_diagnostic_status": "已确认符合",
    }
    assert evaluate_required_clinical_context(
        braf,
        clinical_context=braf_context,
        contract=contract,
    ).eligible

    missing = dict(braf_context)
    missing.pop("companion_diagnostic_status")
    assert evaluate_required_clinical_context(
        braf,
        clinical_context=missing,
        contract=contract,
    ).reasons == ("CONTEXT_VALUE_MISSING:companion_diagnostic_status",)

    uncertain = {**braf_context, "lung_histology": "未明确"}
    assert evaluate_required_clinical_context(
        braf,
        clinical_context=uncertain,
        contract=contract,
    ).reasons == ("CONTEXT_VALUE_UNCERTAIN:lung_histology",)

    wrong_stage = {**braf_context, "disease_extent": "可切除早期"}
    assert evaluate_required_clinical_context(
        braf,
        clinical_context=wrong_stage,
        contract=contract,
    ).reasons == ("CONTEXT_OUT_OF_SCOPE:disease_extent",)

    erbb2_context = {
        **braf_context,
        "disease_extent": "不可切除局部晚期",
        "prior_systemic_therapy": "已接受",
    }
    assert evaluate_required_clinical_context(
        erbb2,
        clinical_context=erbb2_context,
        contract=contract,
    ).eligible
    not_previously_treated = {
        **erbb2_context,
        "prior_systemic_therapy": "未接受",
    }
    assert evaluate_required_clinical_context(
        erbb2,
        clinical_context=not_previously_treated,
        contract=contract,
    ).reasons == ("CONTEXT_OUT_OF_SCOPE:prior_systemic_therapy",)


def test_runtime_loader_moves_context_ineligible_exact_rule_to_blocked_set(tmp_path):
    panel_root = tmp_path / "panels" / "synthetic_lung"
    rules_root = panel_root / "rules"
    rules_root.mkdir(parents=True)
    (rules_root / "clinical_context.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "panel_id": "synthetic_lung",
                "rule_id": "clinical_context",
                "clinical_context_contract": {
                    "fields": {
                        "lung_histology": {
                            "allowed_values": ["非小细胞肺癌", "未明确"],
                            "uncertain_values": ["未明确"],
                        }
                    }
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (rules_root / "drugs.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "panel_id": "synthetic_lung",
                "rule_id": "drugs",
                "targeted_drug_rules": {
                    "enabled": True,
                    "clinical_context_rule": "clinical_context",
                    "reviewed_variant_overrides": [
                        {
                            "gene": "BRAF",
                            "c_hgvs": "c.1799T>A",
                            "p_hgvs": "p.V600E",
                            "required_context_fields": ["lung_histology"],
                            "context_requirements": {"lung_histology": ["非小细胞肺癌"]},
                            "benefit_drugs": ["受控合成药物（A）"],
                        }
                    ],
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    class SyntheticPackage:
        panel_id = "synthetic_lung"
        root_dir = panel_root

        @staticmethod
        def resolve_rule_file(name: str) -> Path:
            return rules_root / f"{name}.yaml"

    active = load_targeted_drug_rule_context(
        SyntheticPackage(),
        clinical_context={"lung_histology": "非小细胞肺癌"},
    )
    assert active is not None
    assert active["clinical_context_enforced"] is True
    assert len(active["reviewed_variant_overrides"]) == 1
    assert active["blocked_reviewed_variant_overrides"] == []
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    assert mapper._lookup_reviewed_variant_override_drugs(
        "BRAF",
        "c.1799T>A",
        "p.V600E",
        targeted_drug_rules=active,
    ) == ("受控合成药物（A）", "--")

    blocked = load_targeted_drug_rule_context(
        SyntheticPackage(),
        clinical_context={"lung_histology": "未明确"},
    )
    assert blocked is not None
    assert blocked["reviewed_variant_overrides"] == []
    assert len(blocked["blocked_reviewed_variant_overrides"]) == 1
    assert blocked["blocked_reviewed_variant_overrides"][0]["_clinical_context_block_reasons"] == [
        "CONTEXT_VALUE_UNCERTAIN:lung_histology"
    ]
    assert mapper._lookup_reviewed_variant_override_drugs(
        "BRAF",
        "c.1799T>A",
        "p.V600E",
        targeted_drug_rules=blocked,
    ) == ("--", "--")


def test_reviewed_variant_transcript_selector_is_exact_and_fail_closed():
    mapper = FieldMapper(config_dir=str(ROOT / "config"), log_level="ERROR")
    generic = {
        "gene": "BRAF",
        "c_hgvs": "c.1799T>A",
        "p_hgvs": "p.V600E",
        "benefit_drugs": ["通用合成药物（A）"],
    }
    transcript_bound = {
        **generic,
        "transcript": "NM_004333.6",
        "benefit_drugs": ["转录本限定合成药物（A）"],
    }
    rules = {
        "enabled": True,
        "reviewed_variant_overrides": [generic],
        "blocked_reviewed_variant_overrides": [transcript_bound],
    }

    # A transcript-bound pending selector outranks the otherwise identical
    # generic selector and keeps the reviewed event closed.
    assert mapper._lookup_reviewed_variant_override_drugs(
        "BRAF",
        "c.1799T>A",
        "p.V600E",
        transcript="NM_004333.6",
        targeted_drug_rules=rules,
    ) == ("--", "--")
    # Missing or version-mismatched transcript must not match that selector;
    # the older rule without a transcript declaration remains compatible.
    assert mapper._lookup_reviewed_variant_override_drugs(
        "BRAF",
        "c.1799T>A",
        "p.V600E",
        targeted_drug_rules=rules,
    ) == ("通用合成药物（A）", "--")
    assert mapper._lookup_reviewed_variant_override_drugs(
        "BRAF",
        "c.1799T>A",
        "p.V600E",
        transcript="NM_004333.5",
        targeted_drug_rules=rules,
    ) == ("通用合成药物（A）", "--")

    assert _variant_override_matches(
        transcript_bound,
        "BRAF",
        "c.1799T>A",
        "p.V600E",
        transcript="NM_004333.6",
    )
    assert not _variant_override_matches(
        transcript_bound,
        "BRAF",
        "c.1799T>A",
        "p.V600E",
    )
    assert not _variant_override_matches(
        transcript_bound,
        "BRAF",
        "c.1799T>A",
        "p.V600E",
        transcript="NM_004333.5",
    )
    assert reviewed_variant_selector_specificity(
        transcript_bound
    ) > reviewed_variant_selector_specificity(generic)
    assert reviewed_variant_selector_specificity(
        {"gene": "BRAF", "transcript": "NM_004333.6"}
    ) < reviewed_variant_selector_specificity(generic)


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


def test_lung588_case_a_contract_is_registered_and_deidentified():
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    contract_path = package.resolve_context_contract_file("case_lung_a")
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))

    assert contract["contract_id"] == "case_lung_a"
    assert contract["panel_id"] == "lung_588_pdl1"
    assert contract["privacy"]["contains_phi"] is False
    assert len(contract["privacy"]["source_excel_sha256"]) == 64
    assert contract["fields"]["total_variants_count"]["equals"] == 7
    assert contract["tables"]["all_variants"]["row_count"] == 7
    assert {
        row["match"]["gene"]["equals"]
        for row in contract["tables"]["all_variants"]["rows"]
    } == {"TP53", "ESR1", "FLT3", "GNAS", "APC", "IFNGR1", "TSC1"}
    assert all(
        row["expect"]["transcript"]["equals"].startswith("NM_")
        and row["expect"]["chromosome"]["equals"]
        and row["expect"]["exon"]["equals"]
        and row["expect"]["gene_class"]["equals"] in {"Ⅱ类", "Ⅲ类"}
        and row["expect"]["frequency"]["equals"]
        for row in contract["tables"]["all_variants"]["rows"]
    )
    emitted = contract_path.read_text(encoding="utf-8")
    assert "LZ258" not in emitted
    assert "patient_name" not in emitted


def test_lung588_semantic_citation_mismatch_remains_release_blocking():
    package = load_panel_package("lung_588_pdl1", project_root=ROOT)
    genes = yaml.safe_load(
        package.resolve_rule_file("knowledge_coverage").read_text(
            encoding="utf-8"
        )
    )["reportable_genes"]
    profile = profile_panel_runtime_content(ROOT, package, genes)

    integrity = profile["citation_integrity"]
    assert integrity["unresolved_pmids"] == []
    assert integrity["source_mismatches"] == [
        {
            "review_id": "lung588_stk11_pmid_25980754_mismatch",
            "gene": "STK11",
            "identifier": "PMID:25980754",
            "status": "source_mismatch_confirmed",
            "claim_contains": "KRAS/STK11共突变可能预测免疫治疗的不良反应",
            "disposition": (
                "block_until_claim_replaced_and_secondarily_reviewed"
            ),
            "secondary_review_status": "pending_report_group_review",
            "suggested_replacement_identifier": "PMID:29773717",
            "present_in_runtime_text": True,
            "claim_fragment_present": True,
        }
    ]

    gate = run_knowledge_release_gate(
        ROOT,
        panel_ids=["lung_588_pdl1"],
    )
    assert gate["status"] == "FAIL"
    codes = {issue["code"] for issue in gate["panels"][0]["issues"]}
    assert "UNRESOLVED_RUNTIME_PMID" not in codes
    assert "RUNTIME_CITATION_SOURCE_MISMATCH" in codes


def test_lung588_medical_knowledge_queue_is_complete_and_deidentified(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "analysis"
                / "23_profile_lung588_medical_knowledge.py"
            ),
            "--project-root",
            str(ROOT),
            "--as-of",
            "2026-07-23",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert completed.returncode == 0, completed.stderr
    inventory = json.loads(
        (tmp_path / "knowledge_depth_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert inventory["denominator"]["total_genes"] == 588
    assert sum(inventory["summary"]["priority_counts"].values()) == 588
    assert inventory["summary"]["citation_source_mismatch_count"] == 1
    stk11 = next(row for row in inventory["rows"] if row["gene"] == "STK11")
    assert stk11["priority"] == "P0"
    assert stk11["citation_source_mismatches"][0]["identifier"] == (
        "PMID:25980754"
    )
    emitted = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in tmp_path.iterdir()
        if path.suffix in {".json", ".tsv"}
    )
    assert "LZ258" not in emitted
    assert "patient_name" not in emitted


def test_lung588_p0_event_review_packet_is_event_scoped_and_fail_closed(
    tmp_path,
):
    completed = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts"
                / "analysis"
                / "24_build_lung588_p0_event_review.py"
            ),
            "--project-root",
            str(ROOT),
            "--reviewed-at",
            "2026-07-23",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert completed.returncode == 0, completed.stderr
    packet = json.loads(
        (tmp_path / "p0_event_review.json").read_text(encoding="utf-8")
    )
    assert packet["status"] == (
        "primary_review_complete_secondary_review_pending"
    )
    assert packet["summary"]["review_unit_count"] == 28
    assert packet["summary"]["unit_type_counts"] == {
        "citation_source_mismatch": 1,
        "targeted_drug_candidate": 4,
        "variant_narrative": 23,
    }
    assert packet["summary"]["secondary_review_completed_count"] == 0
    assert packet["summary"]["patient_visible_part3_allowed_count"] == 0
    assert packet["summary"]["patient_visible_drug_allowed_count"] == 0
    assert packet["scope"]["case_aliases"] == [
        "CASE-LUNG-A",
        "CASE-LUNG-B",
        "CASE-LUNG-C",
    ]
    assert all(unit["runtime_eligible"] is False for unit in packet["units"])
    assert all(
        unit["primary_review"]["status"]
        == "completed_ai_assisted_triage"
        for unit in packet["units"]
    )
    assert all(
        unit["secondary_review"]["status"]
        == "pending_report_group_review"
        for unit in packet["units"]
    )

    variants = [
        unit
        for unit in packet["units"]
        if unit["unit_type"] == "variant_narrative"
    ]
    atm = next(
        unit
        for unit in variants
        if unit["gene"] == "ATM"
        and unit["c_hgvs"] == "c.1236-2A>T"
    )
    assert [row["case_alias"] for row in atm["case_observations"]] == [
        "CASE-LUNG-B",
        "CASE-LUNG-C",
    ]
    assert [row["frequency"] for row in atm["case_observations"]] == [
        "1.67",
        "0.92",
    ]
    assert atm["transcript"] == "NM_000051.4"
    assert atm["chromosome"] == "11"
    assert atm["exon"] == "10"
    braf_d594g = next(
        unit
        for unit in variants
        if unit["gene"] == "BRAF" and unit["p_hgvs"] == "p.D594G"
    )
    assert braf_d594g["explicit_non_promotion"] is True
    assert braf_d594g["patient_visible_drug_conclusion_allowed"] is False

    mismatch = next(
        unit
        for unit in packet["units"]
        if unit["unit_type"] == "citation_source_mismatch"
    )
    assert mismatch["identifier"] == "PMID:25980754"
    assert mismatch["suggested_replacement_identifier"] == "PMID:29773717"

    emitted = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in tmp_path.iterdir()
        if path.suffix in {".json", ".tsv"}
    )
    assert "LZ258" not in emitted
    assert "patient_name" not in emitted
