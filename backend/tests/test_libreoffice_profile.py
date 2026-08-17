from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from lxml import etree
from reportgen.utils.libreoffice_profile import (
    FONT_SUBSTITUTION_PROFILE,
    deterministic_font_substitutions,
    font_substitution_fingerprint,
    initialize_libreoffice_profile,
    stabilize_docx_fonts_for_libreoffice_render,
)


def test_platform_font_substitution_targets_are_explicit() -> None:
    darwin = deterministic_font_substitutions(system_name="Darwin", require_available=False)
    linux = deterministic_font_substitutions(system_name="Linux", require_available=False)

    assert darwin["微软雅黑"] == "Arial Unicode MS"
    assert darwin["宋体"] == "Noto Serif CJK SC"
    assert darwin["幼圆"] == "Noto Sans CJK SC"
    assert linux["微软雅黑"] == "Noto Sans CJK SC"
    assert linux["宋体"] == "Noto Serif CJK SC"


def test_profile_initializer_pins_print_font_substitutions(tmp_path: Path) -> None:
    profile = tmp_path / "lo_profile"
    fingerprint = initialize_libreoffice_profile(
        profile,
        system_name="Darwin",
        require_available=False,
    )
    registry = profile / "user" / "registrymodifications.xcu"
    content = registry.read_text(encoding="utf-8")

    assert fingerprint["font_substitution_profile"] == FONT_SUBSTITUTION_PROFILE
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        str(fingerprint["font_substitution_profile_sha256"]),
    )
    assert "微软雅黑" in content
    assert "Arial Unicode MS" in content
    assert "宋体" in content
    assert "Noto Serif CJK SC" in content
    assert "幼圆" in content
    assert "Noto Sans CJK SC" in content
    assert '<prop oor:name="Replacement"' in content
    assert '<prop oor:name="Always"' in content
    assert "<value>true</value>" in content


def test_font_profile_hash_changes_when_mapping_changes(monkeypatch) -> None:
    first = font_substitution_fingerprint(system_name="Linux", require_available=False)
    monkeypatch.setenv("REPORTGEN_LO_SANS_CJK_FONT", "Pinned Sans")
    second = font_substitution_fingerprint(system_name="Linux", require_available=False)

    assert first["font_substitution_profile_sha256"] != second["font_substitution_profile_sha256"]


def test_disposable_docx_render_copy_pins_explicit_and_theme_fonts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "render-copy.docx"
    document = Document()
    run = document.add_paragraph().add_run("页眉")
    run.font.name = "幼圆"
    run._r.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "幼圆")
    document.save(source)

    result = stabilize_docx_fonts_for_libreoffice_render(
        source,
        system_name="Darwin",
        require_available=False,
    )

    with ZipFile(source) as archive:
        document_xml = etree.fromstring(archive.read("word/document.xml"))
        theme_xml = etree.fromstring(archive.read("word/theme/theme1.xml"))

    namespaces = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    font_nodes = document_xml.xpath(".//w:rFonts", namespaces=namespaces)
    assert font_nodes
    assert {value for node in font_nodes for value in node.attrib.values() if value} == {
        "Noto Sans CJK SC"
    }
    assert all(
        node.get("typeface") == "Noto Serif CJK SC"
        for node in theme_xml.xpath(".//a:fontScheme//a:ea", namespaces=namespaces)
    )
    assert result["explicit_font_replacement_count"] >= 1
    assert result["theme_font_replacement_count"] == 2
