from __future__ import annotations

import re
from pathlib import Path

from reportgen.utils.libreoffice_profile import (
    FONT_SUBSTITUTION_PROFILE,
    deterministic_font_substitutions,
    font_substitution_fingerprint,
    initialize_libreoffice_profile,
)


def test_platform_font_substitution_targets_are_explicit() -> None:
    darwin = deterministic_font_substitutions(system_name="Darwin", require_available=False)
    linux = deterministic_font_substitutions(system_name="Linux", require_available=False)

    assert darwin["微软雅黑"] == "Arial Unicode MS"
    assert darwin["宋体"] == "Songti SC"
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
    assert "Songti SC" in content
    assert '<prop oor:name="Replacement"' in content
    assert '<prop oor:name="Always"' in content
    assert "<value>true</value>" in content


def test_font_profile_hash_changes_when_mapping_changes(monkeypatch) -> None:
    first = font_substitution_fingerprint(system_name="Linux", require_available=False)
    monkeypatch.setenv("REPORTGEN_LO_SANS_CJK_FONT", "Pinned Sans")
    second = font_substitution_fingerprint(system_name="Linux", require_available=False)

    assert first["font_substitution_profile_sha256"] != second["font_substitution_profile_sha256"]
