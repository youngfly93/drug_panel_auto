#!/usr/bin/env python3
"""Validate production-required signature assets without storing them in Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportgen.core.signature_library import resolve_signature_path  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_signature_registry(
    config_dir: str | Path,
    *,
    storage_root: str | Path | None = None,
) -> dict[str, Any]:
    config_path = Path(config_dir) / "signatures.yaml"
    if storage_root is not None:
        os.environ["RG_WEB_STORAGE_ROOT"] = str(Path(storage_root).resolve())
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    required = data.get("production_required") or {}
    checks: list[dict[str, Any]] = []
    for role in ("detector", "reviewer"):
        names = required.get(role) or []
        if isinstance(names, str):
            names = [names]
        for name in names:
            resolved = Path(resolve_signature_path(config_dir, role, str(name)))
            exists = resolved.is_file()
            checks.append(
                {
                    "role": role,
                    "name": str(name),
                    "exists": exists,
                    "sha256": _sha256(resolved) if exists else None,
                }
            )
    errors = []
    if not checks:
        errors.append("production_required is empty")
    errors.extend(
        f"missing runtime signature: {row['role']}/{row['name']}"
        for row in checks
        if not row["exists"]
    )
    return {
        "schema_version": "1.0",
        "status": "PASS" if not errors else "FAIL",
        "required_count": len(checks),
        "checks": checks,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=str(ROOT / "config"))
    parser.add_argument("--storage-root")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = validate_signature_registry(
        args.config_dir,
        storage_root=args.storage_root,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
