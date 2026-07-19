import hashlib
import json
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.qa_report import _build_provenance, build_docx_qa_report

from app.api.report import _qa_has_full_visual_pass


def test_qa_binds_output_hash_to_explicit_source_revision(tmp_path, monkeypatch):
    revision = "a" * 40
    monkeypatch.setenv("REPORTGEN_SOURCE_REVISION", revision)
    output = tmp_path / "candidate.docx"
    document = Document()
    document.add_paragraph("deterministic candidate")
    document.save(output)

    report = build_docx_qa_report(output_file=str(output))

    assert report["build_provenance"] == {
        "source_revision": revision,
        "source_kind": "environment",
        "source_dirty": False,
    }
    assert report["metrics"]["output_sha256"] == hashlib.sha256(
        output.read_bytes()
    ).hexdigest()


def test_explicit_source_revision_must_be_commit_like(monkeypatch):
    monkeypatch.setenv("REPORTGEN_SOURCE_REVISION", "latest")
    provenance = _build_provenance()

    assert provenance["source_kind"] != "environment"


def test_golden_visual_gate_requires_linux_full_render(tmp_path):
    qa_path = tmp_path / "candidate.qa.json"
    visual = {
        "status": "PASS",
        "requested": "all",
        "required": True,
        "renderer_fingerprint": {"platform": "Darwin"},
    }
    qa_path.write_text(
        json.dumps({"checks": {"visual_render": visual}}),
        encoding="utf-8",
    )
    assert _qa_has_full_visual_pass(str(qa_path)) is False

    visual["renderer_fingerprint"]["platform"] = "Linux"
    qa_path.write_text(
        json.dumps({"checks": {"visual_render": visual}}),
        encoding="utf-8",
    )
    assert _qa_has_full_visual_pass(str(qa_path)) is False

    visual["renderer_fingerprint"] = {
        "platform": "Linux",
        "machine": "x86_64",
        "engine": "soffice",
        "engine_version": "LibreOffice 24.2",
        "profile_mode": "isolated",
        "pdf_renderer": "pdftoppm",
        "pdf_renderer_version": "pdftoppm 24.02.0",
        "font_substitution_profile": "reportgen-cjk-font-substitution-v1",
        "font_substitution_profile_sha256": "a" * 64,
    }
    qa_path.write_text(
        json.dumps({"checks": {"visual_render": visual}}),
        encoding="utf-8",
    )
    assert _qa_has_full_visual_pass(str(qa_path)) is True
