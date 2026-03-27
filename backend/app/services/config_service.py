"""
Configuration service: YAML config CRUD with validation and backup.

Operates on upstream config files (mapping.yaml, settings.yaml, etc.)
with automatic backup before writes.
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from app.config import settings

# Allowed config files (whitelist for security)
ALLOWED_CONFIGS = {
    "mapping.yaml",
    "settings.yaml",
    "project_types.yaml",
    "filtering.yaml",
    "variant_table_baseline.yaml",
    "drug_tables_config.yaml",
    "cnv_fusion_hla_mapping.yaml",
}


def _config_dir() -> Path:
    return Path(settings.upstream_config_dir)


def _validate_filename(filename: str) -> Path:
    """Validate and resolve config filename."""
    if filename not in ALLOWED_CONFIGS:
        raise ValueError(f"不允许编辑的配置文件: {filename}")
    path = _config_dir() / filename
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {filename}")
    return path


def list_config_files() -> list[dict[str, Any]]:
    """List all editable config files with metadata."""
    result = []
    for name in sorted(ALLOWED_CONFIGS):
        path = _config_dir() / name
        if path.exists():
            stat = path.stat()
            result.append({
                "filename": name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return result


def get_config(filename: str) -> dict[str, Any]:
    """Load and return a config file as parsed JSON/dict."""
    path = _validate_filename(filename)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def get_config_raw(filename: str) -> str:
    """Get raw YAML text."""
    path = _validate_filename(filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def validate_config(filename: str, content: dict) -> dict[str, Any]:
    """Validate config content without saving. Returns {valid, errors}."""
    errors = []

    if filename == "mapping.yaml":
        if "single_values" not in content:
            errors.append("缺少 single_values 字段")
        sv = content.get("single_values", {})
        if isinstance(sv, dict):
            for key, field_def in sv.items():
                if isinstance(field_def, dict):
                    if "type" not in field_def:
                        errors.append(f"字段 {key} 缺少 type 定义")
                    if "synonyms" not in field_def:
                        errors.append(f"字段 {key} 缺少 synonyms 定义")

    elif filename == "project_types.yaml":
        if "project_types" not in content:
            errors.append("缺少 project_types 列表")
        pts = content.get("project_types", [])
        if isinstance(pts, list):
            for i, pt in enumerate(pts):
                if not isinstance(pt, dict):
                    errors.append(f"project_types[{i}] 不是字典")
                elif "id" not in pt:
                    errors.append(f"project_types[{i}] 缺少 id")

    elif filename == "settings.yaml":
        # Basic structure check
        pass

    return {"valid": len(errors) == 0, "errors": errors}


def _backup_config(path: Path) -> str:
    """Create a timestamped backup of a config file."""
    backup_dir = _config_dir() / ".backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{path.stem}_{ts}{path.suffix}"
    backup_path = backup_dir / backup_name
    shutil.copy2(path, backup_path)
    return str(backup_path)


def update_config(filename: str, content: dict) -> dict[str, Any]:
    """
    Update a config file with validation and backup.
    Returns {success, backup_path, validation}.
    """
    path = _validate_filename(filename)

    # Validate first
    validation = validate_config(filename, content)
    if not validation["valid"]:
        return {"success": False, "validation": validation, "backup_path": None}

    # Backup
    backup_path = _backup_config(path)

    # Write
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(content, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return {"success": True, "validation": validation, "backup_path": backup_path}


def get_config_history(filename: str) -> list[dict[str, Any]]:
    """List backup versions of a config file."""
    _validate_filename(filename)  # ensure filename is valid
    backup_dir = _config_dir() / ".backups"
    if not backup_dir.exists():
        return []

    stem = Path(filename).stem
    backups = sorted(backup_dir.glob(f"{stem}_*"), reverse=True)
    result = []
    for bp in backups[:20]:  # limit to 20 most recent
        stat = bp.stat()
        result.append({
            "filename": bp.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return result
