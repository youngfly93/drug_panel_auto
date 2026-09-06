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
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

FONT_SUBSTITUTION_PROFILE = "reportgen-cjk-font-substitution-v3"

# Some reviewed Word templates carry old or subset-prefixed CJK family names.
# LibreOffice's macOS font matcher can resolve those names to a different face
# on each cold start, even when its replacement table is enabled.  These aliases
# are therefore normalized only in the disposable DOCX used for PDF rendering;
# the delivered Word document keeps its reviewed font names.
_SERIF_CJK_ALIASES = (
    "宋体",
    "SimSun",
    "NSimSun",
    "SimSun-ExtB",
    "华文中宋",
    "楷体",
    "楷体_GB2312",
    "OSTASS+å\x8d\x8eæ\x96\x87ä¸\xadå®\x8b",
)
_SANS_CJK_ALIASES = (
    "微软雅黑",
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "ArialUnicodeMS",
    "LPJNJT+Arial Unicode MS",
)
_DECORATIVE_CJK_ALIASES = ("黑体", "幼圆")


def _platform_default_fonts(system_name: str) -> tuple[str, str, str]:
    if system_name == "Darwin":
        # LibreOffice 25 on macOS can select the Interface/partial face behind
        # ``Hiragino Sans GB`` during Word-font substitution.  The PDF text
        # layer stays correct but common Chinese glyphs render as squares.
        # Arial Unicode MS is installed on the qualified report workstation
        # and was verified with the full legal-notice glyph probe.
        # ``Songti SC`` is a multi-face TTC family.  LibreOffice 25 can resolve
        # it as STSong, Songti TC or Hiragino Sans GB across identical cold
        # starts, changing long-report pagination.  The Noto SC faces are
        # separate OTF files on the qualified workstation and resolve uniquely.
        return "Arial Unicode MS", "Noto Serif CJK SC", "Noto Sans CJK SC"
    # Production and CI install fonts-noto-cjk.  Fail closed when that
    # prerequisite is absent instead of silently selecting a different font.
    return "Noto Sans CJK SC", "Noto Serif CJK SC", "Noto Sans CJK SC"


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
    default_sans, default_serif, default_decorative = _platform_default_fonts(
        detected_system
    )
    sans = str(os.environ.get("REPORTGEN_LO_SANS_CJK_FONT") or default_sans).strip()
    serif = str(os.environ.get("REPORTGEN_LO_SERIF_CJK_FONT") or default_serif).strip()
    decorative = str(
        os.environ.get("REPORTGEN_LO_DECORATIVE_CJK_FONT") or default_decorative
    ).strip()
    if not sans or not serif or not decorative:
        raise RuntimeError("LibreOffice CJK 字体替换配置不完整")

    if require_available:
        installed = _installed_font_families()
        if not installed:
            raise RuntimeError("无法通过 fc-list 验证 LibreOffice CJK 字体")
        missing = [
            font
            for font in dict.fromkeys((sans, serif, decorative))
            if font.casefold() not in installed
        ]
        if missing:
            raise RuntimeError(
                "LibreOffice 缺少固定 CJK 替换字体: " + ", ".join(missing)
            )

    return {
        **{name: sans for name in _SANS_CJK_ALIASES},
        **{name: serif for name in _SERIF_CJK_ALIASES},
        **{name: decorative for name in _DECORATIVE_CJK_ALIASES},
    }


def stabilize_docx_fonts_for_libreoffice_render(
    docx_path: Path,
    *,
    system_name: str | None = None,
    require_available: bool = False,
) -> dict[str, object]:
    """Pin explicit and theme CJK fonts in a disposable DOCX render copy.

    LibreOffice's replacement table alone is insufficient for Word documents
    whose East Asian theme font is blank or whose runs name an unavailable
    legacy family such as ``幼圆``.  On macOS those names can select different
    fallback faces on identical cold starts and change pagination.  This
    function rewrites only the staged QA/PDF copy, never the delivered DOCX.
    """
    try:
        from lxml import etree
    except Exception as exc:
        raise RuntimeError("LibreOffice PDF 字体固定失败：缺少 lxml") from exc

    source = Path(docx_path)
    if not source.exists() or source.suffix.lower() != ".docx":
        raise ValueError(f"LibreOffice PDF 字体固定需要现有 DOCX: {source}")

    substitutions = deterministic_font_substitutions(
        system_name=system_name,
        require_available=require_available,
    )
    folded_substitutions = {
        name.casefold(): target for name, target in substitutions.items()
    }
    theme_font = substitutions["宋体"]
    explicit_replacements = 0
    theme_replacements = 0

    fd, tmp_name = tempfile.mkstemp(
        suffix=".docx",
        prefix=f"{source.stem}_font_render_",
        dir=str(source.parent),
    )
    os.close(fd)
    temporary = Path(tmp_name)
    original_mode = source.stat().st_mode
    try:
        with (
            ZipFile(source, "r") as zin,
            ZipFile(temporary, "w", compression=ZIP_DEFLATED) as zout,
        ):
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    root = etree.fromstring(data)
                    changed = False
                    for element in root.iter():
                        local_name = etree.QName(element).localname
                        if local_name == "rFonts":
                            for attribute, value in list(element.attrib.items()):
                                target = folded_substitutions.get(value.casefold())
                                if target and target != value:
                                    element.set(attribute, target)
                                    explicit_replacements += 1
                                    changed = True
                        elif (
                            item.filename.startswith("word/theme/")
                            and local_name == "ea"
                            and not str(element.get("typeface") or "").strip()
                        ):
                            element.set("typeface", theme_font)
                            theme_replacements += 1
                            changed = True
                    if changed:
                        data = etree.tostring(
                            root,
                            xml_declaration=True,
                            encoding="UTF-8",
                            standalone="yes",
                        )
                zout.writestr(item, data)
        os.chmod(temporary, original_mode)
        os.replace(temporary, source)
    finally:
        if temporary.exists():
            temporary.unlink()

    return {
        "font_substitution_profile": FONT_SUBSTITUTION_PROFILE,
        "explicit_font_replacement_count": explicit_replacements,
        "theme_font_replacement_count": theme_replacements,
        "theme_east_asia_font": theme_font,
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


def _registry_xml(
    substitutions: Mapping[str, str], *, include_automatic_blank_pages: bool = False
) -> str:
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
                (
                    '<item oor:path="/org.openoffice.Office.Common/Filter/PDF/Export">'
                    '<prop oor:name="IsSkipEmptyPages" oor:op="fuse">'
                    '<value>false</value></prop></item>'
                    if include_automatic_blank_pages else ""
                ),
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
    include_automatic_blank_pages: bool = False,
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
        _registry_xml(
            fingerprint["font_substitutions"],
            include_automatic_blank_pages=include_automatic_blank_pages,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return fingerprint
