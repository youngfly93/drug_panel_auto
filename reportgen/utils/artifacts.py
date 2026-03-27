"""
Build/write reproducibility artifacts (context/meta).

Artifacts are intended for local debugging and auditability; they should be
written under gitignored directories (e.g. data/output/...).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def _sha256_file(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, set):
        return sorted([_to_jsonable(v) for v in obj])
    # Basic scalar types are fine; fallback to string for others (numpy, pandas, etc.)
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _to_jsonable(obj)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_meta(
    *,
    excel_path: Path,
    template_path: Path,
    output_docx: Optional[Path],
    config_dir: Path,
    args: Mapping[str, Any],
    template_contract: Optional[Dict[str, Any]] = None,
    include_paths: bool = False,
) -> Dict[str, Any]:
    """Build a minimal reproducibility metadata object."""
    config_files = {
        "mapping.yaml": config_dir / "mapping.yaml",
        "project_types.yaml": config_dir / "project_types.yaml",
        "settings.yaml": config_dir / "settings.yaml",
    }

    excel_sha256 = _sha256_file(excel_path)
    template_sha256 = _sha256_file(template_path)
    output_sha256 = _sha256_file(output_docx) if output_docx else None

    def safe_ref(path: Path, sha256: Optional[str]) -> str:
        if include_paths:
            return str(path)
        if sha256:
            return f"sha256:{sha256[:12]}{path.suffix}"
        return f"<redacted>{path.suffix}"

    def sanitize_args(obj: Mapping[str, Any]) -> Dict[str, Any]:
        if include_paths:
            return dict(obj)

        out: Dict[str, Any] = dict(obj)

        if "inputs" in out:
            v = out.get("inputs")
            if isinstance(v, (list, tuple)):
                out["inputs_count"] = len(v)
            elif v:
                out["inputs_count"] = 1
            else:
                out["inputs_count"] = 0
            out["inputs"] = "<redacted>"

        if out.get("name_contains"):
            out["name_contains"] = "<redacted>"

        # Keep only basenames for path-like args (still useful, but avoids
        # absolute paths).
        for key in (
            "template",
            "config_dir",
            "output_root",
            "highlight_output_root",
            "report_file",
        ):
            if key not in out or out.get(key) in (None, ""):
                continue
            try:
                out[key] = Path(str(out[key])).name
            except Exception:
                out[key] = "<redacted>"

        return out

    return {
        "generated_at": datetime.now().isoformat(),
        "paths_included": bool(include_paths),
        "excel_file": safe_ref(excel_path, excel_sha256),
        "excel_sha256": excel_sha256,
        "template_file": str(template_path) if include_paths else template_path.name,
        "template_sha256": template_sha256,
        "output_docx": safe_ref(output_docx, output_sha256) if output_docx else None,
        "output_docx_sha256": output_sha256,
        "config_dir": str(config_dir) if include_paths else config_dir.name,
        "config_sha256": {
            k: _sha256_file(p) for k, p in config_files.items() if p.exists()
        },
        "python": sys.version,
        "argv": sanitize_args(args),
        "template_contract": template_contract,
    }
