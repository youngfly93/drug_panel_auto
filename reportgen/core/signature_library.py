"""Signature library helpers for report signing images."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SignatureEntry:
    role: str
    name: str
    path: str
    title: str = ""


ROLE_ALIASES = {
    "detector": ("detector", "issuer", "检测者", "签发人", "报告人"),
    "reviewer": ("reviewer", "审核者", "审核人"),
}


def load_signature_entries(config_dir: str | Path) -> dict[str, list[SignatureEntry]]:
    """Load configured signatures from ``config/signatures.yaml``.

    Supported YAML forms:

    ``detector: { 张三: path/to/sign.png }``
    ``reviewer: [{ name: 李四, path: /abs/sign.png }]``
    ``signatures: { detector: ... }``
    """
    path = Path(config_dir) / "signatures.yaml"
    if not path.exists():
        return {"detector": [], "reviewer": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data.get("signatures"), dict):
        data = data["signatures"]

    base_dirs = [Path(config_dir), Path(config_dir).parent]
    return {
        role: _parse_role_entries(role, data, base_dirs)
        for role in ("detector", "reviewer")
    }


def signature_options(config_dir: str | Path, role: str) -> list[str]:
    entries = load_signature_entries(config_dir).get(_canonical_role(role), [])
    return [entry.name for entry in entries if entry.name]


def resolve_signature_path(
    config_dir: str | Path,
    role: str,
    name: str | None,
) -> str:
    """Resolve a signer name to a configured image path."""
    needle = _norm(name)
    if not needle:
        return ""
    entries = load_signature_entries(config_dir).get(_canonical_role(role), [])
    for entry in entries:
        if _norm(entry.name) == needle:
            return entry.path
    return ""


def _parse_role_entries(
    role: str,
    data: dict[str, Any],
    base_dirs: list[Path],
) -> list[SignatureEntry]:
    raw = None
    for key in ROLE_ALIASES[role]:
        if key in data:
            raw = data[key]
            break
    if raw is None:
        return []

    entries: list[SignatureEntry] = []
    if isinstance(raw, dict):
        iterable = [
            {"name": name, **(value if isinstance(value, dict) else {"path": value})}
            for name, value in raw.items()
        ]
    elif isinstance(raw, list):
        iterable = raw
    else:
        iterable = []

    for item in iterable:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("display_name") or "").strip()
        path = str(item.get("path") or item.get("image") or "").strip()
        if not name or not path:
            continue
        entries.append(
            SignatureEntry(
                role=role,
                name=name,
                path=_resolve_path(path, base_dirs),
                title=str(item.get("title") or "").strip(),
            )
        )
    return entries


def _resolve_path(path: str, base_dirs: list[Path]) -> str:
    p = Path(path).expanduser()
    if p.is_absolute():
        return str(p)
    for base in base_dirs:
        candidate = (base / p).resolve()
        if candidate.exists():
            return str(candidate)
    return str((base_dirs[-1] / p).resolve())


def _canonical_role(role: str) -> str:
    text = _norm(role)
    for canonical, aliases in ROLE_ALIASES.items():
        if text in {_norm(alias) for alias in aliases}:
            return canonical
    return "reviewer" if "review" in text or "审核" in text else "detector"


def _norm(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "")
