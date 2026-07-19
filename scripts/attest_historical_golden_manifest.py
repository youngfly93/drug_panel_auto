#!/usr/bin/env python3
# 步骤: 历史金标准候选凭据固化
# 上游: 当前冻结 Git commit + Linux 全页 QA + candidate DOCX
# 输出: 外部 historical_golden_release_manifest.yaml（原子更新）
# 种子: 不适用（SHA-256 确定性校验）
"""Bind an external historical-golden manifest to pipeline QA provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_historical_golden_release import (  # noqa: E402
    _resolve_external,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _current_clean_revision() -> str:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise ValueError("工作树未冻结；禁止给候选报告签发当前 commit 凭据")
    return revision


def _candidate_renderer_from_qa(qa: dict[str, Any]) -> dict[str, str]:
    visual = (qa.get("checks") or {}).get("visual_render") or {}
    if not (
        visual.get("status") == "PASS"
        and visual.get("requested") == "all"
        and visual.get("required") is True
    ):
        raise ValueError("候选 QA 未通过 Linux 全页阻断式视觉检查")
    raw = visual.get("renderer_fingerprint") or {}
    result = {
        "platform": str(raw.get("platform") or "").strip(),
        "machine": str(raw.get("machine") or "").strip(),
        "engine": str(raw.get("engine") or "").strip(),
        "version": str(raw.get("engine_version") or "").strip(),
        "profile_mode": str(raw.get("profile_mode") or "").strip(),
        "pdf_renderer": str(raw.get("pdf_renderer") or "").strip(),
        "pdf_renderer_version": str(
            raw.get("pdf_renderer_version") or ""
        ).strip(),
        "font_substitution_profile": str(
            raw.get("font_substitution_profile") or ""
        ).strip(),
        "font_substitution_profile_sha256": str(
            raw.get("font_substitution_profile_sha256") or ""
        ).strip(),
    }
    if result["platform"] != "Linux" or not all(result.values()):
        raise ValueError("候选 QA 缺少完整 Linux 渲染器指纹")
    if not re.fullmatch(
        r"[0-9a-f]{64}", result["font_substitution_profile_sha256"].lower()
    ):
        raise ValueError("候选 QA 字体替换配置哈希无效")
    return result


def attest_manifest(manifest_path: Path, revision: str) -> dict[str, Any]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    cases = manifest.get("cases") or []
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest cases 必须是非空列表")
    for case in cases:
        alias = str(case.get("case_alias") or "unnamed")
        candidate = _resolve_external(
            str(case.get("candidate_docx") or ""),
            manifest_path.parent,
        )
        qa_path = _resolve_external(
            str(case.get("candidate_qa") or ""),
            manifest_path.parent,
        )
        if not candidate.is_file() or not qa_path.is_file():
            raise ValueError(f"{alias}: candidate DOCX/QA 不存在")
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        build = qa.get("build_provenance") or {}
        if build.get("source_revision") != revision:
            raise ValueError(f"{alias}: QA source_revision 与当前 commit 不一致")
        if build.get("source_dirty") is not False:
            raise ValueError(f"{alias}: QA 来自未冻结源码")
        candidate_sha = _sha256(candidate)
        if (qa.get("metrics") or {}).get("output_sha256") != candidate_sha:
            raise ValueError(f"{alias}: QA output_sha256 与候选 DOCX 不一致")
        case["candidate_source_revision"] = revision
        case["candidate_sha256"] = candidate_sha
        case["candidate_qa_sha256"] = _sha256(qa_path)
        case["candidate_renderer"] = _candidate_renderer_from_qa(qa)
    manifest["source_revision"] = revision
    temporary = manifest_path.with_suffix(manifest_path.suffix + ".part")
    temporary.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.manifest).resolve()
    try:
        revision = _current_clean_revision()
        result = attest_manifest(manifest_path, revision)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "source_revision": result["source_revision"],
                "case_count": len(result.get("cases") or []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
