"""Deterministic LibreOffice profile settings for ReportGen rendering.

The report templates intentionally keep their reviewed Word font names (for
example ``微软雅黑`` and ``宋体``).  Those fonts are normally unavailable on
Linux and macOS LibreOffice hosts.  Leaving fallback selection implicit makes
the same DOCX paginate differently across fresh LibreOffice processes.  This
module pins display/print-only substitutions in an isolated LibreOffice
profile; it never changes the fonts stored in the delivered DOCX.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from xml.sax.saxutils import escape

FONT_SUBSTITUTION_PROFILE = "reportgen-cjk-font-substitution-v2"


def _platform_default_fonts(system_name: str) -> tuple[str, str]:
    if system_name == "Darwin":
        # LibreOffice 25 on macOS can select the Interface/partial face behind
        # ``Hiragino Sans GB`` during Word-font substitution.  The PDF text
        # layer stays correct but common Chinese glyphs render as squares.
        # Arial Unicode MS is installed on the qualified report workstation
        # and was verified with the full legal-notice glyph probe.
        return "Arial Unicode MS", "Songti SC"
    # Production and CI install fonts-noto-cjk.  Fail closed when that
    # prerequisite is absent instead of silently selecting a different font.
    return "Noto Sans CJK SC", "Noto Serif CJK SC"


@lru_cache(maxsize=1)
def _installed_font_families() -> frozenset[str]:
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return frozenset()
    try:
        process = subprocess.run(
            [fc_list, "--format=%{family}\n"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return frozenset()
    families: set[str] = set()
    for line in process.stdout.splitlines():
        for family in line.split(","):
            normalized = family.strip().casefold()
            if normalized:
                families.add(normalized)
    return frozenset(families)


def deterministic_font_substitutions(
    *,
    system_name: str | None = None,
    require_available: bool = True,
) -> dict[str, str]:
    """Return the pinned Word-font substitutions for this renderer host."""
    detected_system = system_name or platform.system()
    default_sans, default_serif = _platform_default_fonts(detected_system)
    sans = str(os.environ.get("REPORTGEN_LO_SANS_CJK_FONT") or default_sans).strip()
    serif = str(os.environ.get("REPORTGEN_LO_SERIF_CJK_FONT") or default_serif).strip()
    if not sans or not serif:
        raise RuntimeError("LibreOffice CJK 字体替换配置不完整")

    if require_available:
        installed = _installed_font_families()
        if not installed:
            raise RuntimeError("无法通过 fc-list 验证 LibreOffice CJK 字体")
        missing = [font for font in (sans, serif) if font.casefold() not in installed]
        if missing:
            raise RuntimeError(
                "LibreOffice 缺少固定 CJK 替换字体: " + ", ".join(missing)
            )

    return {
        "微软雅黑": sans,
        "Microsoft YaHei": sans,
        "Microsoft YaHei UI": sans,
        "宋体": serif,
        "SimSun": serif,
        "NSimSun": serif,
        "华文中宋": serif,
    }


def font_substitution_fingerprint(
    *,
    system_name: str | None = None,
    require_available: bool = True,
) -> dict[str, object]:
    """Return an auditable identity for the effective replacement table."""
    substitutions = deterministic_font_substitutions(
        system_name=system_name,
        require_available=require_available,
    )
    canonical = json.dumps(
        substitutions,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "font_substitution_profile": FONT_SUBSTITUTION_PROFILE,
        "font_substitution_profile_sha256": hashlib.sha256(canonical).hexdigest(),
        "font_substitutions": substitutions,
    }


def _registry_xml(substitutions: Mapping[str, str]) -> str:
    nodes: list[str] = []
    for index, (source, target) in enumerate(sorted(substitutions.items())):
        nodes.append(
            "".join(
                [
                    f'<node oor:name="ReportGen{index}" oor:op="replace">',
                    '<prop oor:name="ReplaceFont" oor:op="fuse"><value>',
                    escape(source),
                    "</value></prop>",
                    '<prop oor:name="SubstituteFont" oor:op="fuse"><value>',
                    escape(target),
                    "</value></prop>",
                    '<prop oor:name="Always" oor:op="fuse"><value>true</value></prop>',
                    '<prop oor:name="OnScreenOnly" oor:op="fuse"><value>false</value></prop>',
                    "</node>",
                ]
            )
        )
    return (
        "".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<oor:items xmlns:oor="http://openoffice.org/2001/registry">',
                '<item oor:path="/org.openoffice.Office.Common/Font/Substitution">',
                '<prop oor:name="Replacement" oor:op="fuse"><value>true</value></prop>',
                "</item>",
                '<item oor:path="/org.openoffice.Office.Common/Font/Substitution/FontPairs">',
                *nodes,
                "</item>",
                '<item oor:path="/org.openoffice.Office.Common/Misc">',
                '<prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop>',
                "</item>",
                "</oor:items>",
            ]
        )
        + "\n"
    )


def initialize_libreoffice_profile(
    profile_dir: Path,
    *,
    system_name: str | None = None,
    require_available: bool = True,
) -> dict[str, object]:
    """Create the pinned font table before LibreOffice opens the profile."""
    profile_dir = Path(profile_dir)
    user_dir = profile_dir / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = font_substitution_fingerprint(
        system_name=system_name,
        require_available=require_available,
    )
    target = user_dir / "registrymodifications.xcu"
    temporary = user_dir / "registrymodifications.xcu.next"
    temporary.write_text(
        _registry_xml(fingerprint["font_substitutions"]),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return fingerprint
