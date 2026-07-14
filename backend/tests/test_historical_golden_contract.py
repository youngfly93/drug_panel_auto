from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from docx import Document
from reportgen.core.historical_golden_contract import (
    load_historical_golden_contract,
    validate_historical_golden_docx,
)
from scripts.check_historical_golden_release import (
    _candidate_renderer_fingerprint,
    _sha256_files,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    ROOT
    / "panels"
    / "crc_358_msi"
    / "golden_cases"
    / "crc358_reviewed_case_a.yaml"
)


def test_crc358_historical_contract_is_deidentified_and_structured() -> None:
    contract = load_historical_golden_contract(CONTRACT)
    assert contract["case_alias"] == "crc358_reviewed_case_a"
    assert contract["privacy"]["contains_phi"] is False
    assert contract["expectations"]["targeted_summary"]["row_count"] == 7
    assert contract["expectations"]["part3"]["gene_section_count"] == 11
    assert contract["expectations"]["part3"]["drug_section_count"] == 18


def test_historical_contract_loader_rejects_phi_contract(tmp_path) -> None:
    payload = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    payload["privacy"]["contains_phi"] = True
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="contains_phi=false"):
        load_historical_golden_contract(path)


def _minimal_historical_docx(path: Path, *, include_tp53: bool = True) -> None:
    doc = Document()
    summary = doc.add_table(rows=2 if include_tp53 else 1, cols=4)
    summary.rows[0].cells[0].text = "基因"
    summary.rows[0].cells[1].text = "突变位点"
    summary.rows[0].cells[2].text = "潜在获益靶向药物"
    summary.rows[0].cells[3].text = "可能耐药"
    if include_tp53:
        summary.rows[1].cells[0].text = "TP53"
        summary.rows[1].cells[1].text = "c.499C>T, p.Q167*"
        summary.rows[1].cells[2].text = "AZD1775（C）"
        summary.rows[1].cells[3].text = "--"

    detail = doc.add_table(rows=3 if include_tp53 else 2, cols=9)
    detail.rows[0].cells[0].text = "基因名称"
    detail.rows[0].cells[7].text = "潜在获益靶向药物"
    detail.rows[1].cells[1].text = "转录本号"
    if include_tp53:
        row = detail.rows[2].cells
        row[0].text = "TP53"
        row[4].text = "c.499C>T, p.Q167*"
        row[6].text = "1.16"
        row[7].text = "AZD1775（C）"
        row[8].text = "--"
    doc.add_paragraph("非业务差异标记")
    doc.save(path)


def test_reference_sha_verifies_reference_not_candidate(tmp_path) -> None:
    reference = tmp_path / "reference.docx"
    candidate = tmp_path / "candidate.docx"
    _minimal_historical_docx(reference)
    _minimal_historical_docx(candidate)
    # Change only a non-contract paragraph so the candidate binary hash differs.
    doc = Document(candidate)
    doc.add_paragraph("候选版本标记")
    doc.save(candidate)
    reference_sha = hashlib.sha256(reference.read_bytes()).hexdigest()
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() != reference_sha
    contract = {
        "schema_version": "1.0",
        "case_alias": "synthetic_case",
        "panel_id": "crc_358_msi",
        "privacy": {"contains_phi": False},
        "source": {"reference_docx_sha256": reference_sha},
        "expectations": {
            "table_count": 2,
            "targeted_summary": {"row_count": 1, "gene_order": ["TP53"]},
            "part3": {"gene_section_count": 0, "drug_section_count": 0},
            "reviewed_variant_rows": [
                {
                    "gene": "TP53",
                    "c_hgvs": "c.499C>T",
                    "p_hgvs": "p.Q167*",
                    "vaf": 1.16,
                    "benefit_count": 1,
                    "caution_count": 0,
                }
            ],
        },
    }

    result = validate_historical_golden_docx(
        contract=contract,
        docx_path=candidate,
        require_reference_sha=True,
        reference_docx_path=reference,
    )

    assert result["status"] == "PASS", result["errors"]


def test_historical_contract_blocks_missing_reviewed_variant(tmp_path) -> None:
    reference = tmp_path / "reference.docx"
    candidate = tmp_path / "candidate.docx"
    _minimal_historical_docx(reference)
    _minimal_historical_docx(candidate, include_tp53=False)
    contract = {
        "schema_version": "1.0",
        "case_alias": "synthetic_case",
        "panel_id": "crc_358_msi",
        "privacy": {"contains_phi": False},
        "source": {"reference_docx_sha256": hashlib.sha256(reference.read_bytes()).hexdigest()},
        "expectations": {
            "table_count": 2,
            "targeted_summary": {"row_count": 1, "gene_order": ["TP53"]},
            "part3": {"gene_section_count": 0, "drug_section_count": 0},
            "reviewed_variant_rows": [
                {
                    "gene": "TP53",
                    "c_hgvs": "c.499C>T",
                    "p_hgvs": "p.Q167*",
                    "vaf": 1.16,
                    "benefit_count": 1,
                    "caution_count": 0,
                }
            ],
        },
    }

    result = validate_historical_golden_docx(contract=contract, docx_path=candidate)

    assert result["status"] == "FAIL"
    assert {error["code"] for error in result["errors"]} >= {
        "REVIEWED_VARIANT_ROW_PRESENT",
        "TARGETED_SUMMARY_REVIEWED_ROW_PRESENT",
    }


def test_committed_historical_contract_registry_passes() -> None:
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_historical_golden_release.py"),
            "--contracts-only",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr


def test_candidate_renderer_fingerprint_is_explicit_and_complete() -> None:
    assert _candidate_renderer_fingerprint(
        {
            "candidate_renderer": {
                "platform": "Linux",
                "engine": "LibreOffice",
                "version": "7.3.7.2",
                "evidence": "production-equivalent visual QA",
            }
        }
    ) == {
        "platform": "Linux",
        "engine": "LibreOffice",
        "version": "7.3.7.2",
        "evidence": "production-equivalent visual QA",
    }
    with pytest.raises(ValueError, match="missing required fields"):
        _candidate_renderer_fingerprint(
            {"candidate_renderer": {"platform": "Linux", "engine": "LibreOffice"}}
        )


def test_release_hash_ignores_macos_filesystem_metadata(tmp_path) -> None:
    controlled = tmp_path / "rules.yaml"
    controlled.write_text("rules: controlled\n", encoding="utf-8")
    expected = _sha256_files([controlled])

    appledouble = tmp_path / "._rules.yaml"
    appledouble.write_bytes(b"macOS AppleDouble metadata")
    finder_marker = tmp_path / ".DS_Store"
    finder_marker.write_bytes(b"Finder metadata")

    assert _sha256_files([controlled, appledouble, finder_marker]) == expected
