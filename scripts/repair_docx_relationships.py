#!/usr/bin/env python3
# 步骤: 72 历史 Word 失效关系外科修复
# 上游: .work/lung588_historical_refs/CASE-*.reference.docx
# 输出: .work/lung588_historical_refs/repaired/*.repaired.docx、repair_manifest.json
# 种子: 无（确定性 OOXML 关系校验与节点移除）
"""Repair broken internal relationships in DOCX copies without touching sources.

The tool is deliberately conservative:

* source files are never modified;
* external relationships are ignored;
* only a ``NULL`` target, or an internal target missing from the package, is
  removed;
* XML nodes that reference a removed image relationship are removed with the
  relationship so the repaired copy does not retain an orphan ``r:embed``;
* the manifest contains aliases and hashes, never source paths or document text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote

from lxml import etree


PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_TAG = f"{{{PACKAGE_REL_NS}}}Relationship"
REL_ATTRS = {
    f"{{{OFFICE_REL_NS}}}embed",
    f"{{{OFFICE_REL_NS}}}id",
    f"{{{OFFICE_REL_NS}}}link",
}
REMOVABLE_CONTAINER_TAGS = {
    f"{{{WORD_NS}}}drawing",
    f"{{{WORD_NS}}}object",
    f"{{{WORD_NS}}}pict",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_part_for_relationship_part(name: str) -> str | None:
    """Return the OOXML source part represented by a ``*.rels`` member."""

    if name == "_rels/.rels":
        return None
    marker = "/_rels/"
    if marker not in name or not name.endswith(".rels"):
        return None
    prefix, rel_name = name.split(marker, 1)
    return f"{prefix}/{rel_name[:-5]}"


def _resolve_internal_target(source_part: str | None, target: str) -> str:
    target_without_fragment = unquote(target.split("#", 1)[0]).replace("\\", "/")
    if target_without_fragment.startswith("/"):
        return posixpath.normpath(target_without_fragment.lstrip("/"))
    base = posixpath.dirname(source_part) if source_part else ""
    return posixpath.normpath(posixpath.join(base, target_without_fragment))


def _relationship_type_name(value: str) -> str:
    return value.rstrip("/").rsplit("/", 1)[-1] if value else "unknown"


def _remove_orphan_references(
    xml_bytes: bytes,
    relationship_ids: set[str],
) -> tuple[bytes, int]:
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(xml_bytes, parser=parser)
    removed_nodes: set[int] = set()
    removed_count = 0

    for element in root.iter():
        referenced_ids = {
            value
            for attr, value in element.attrib.items()
            if attr in REL_ATTRS and value in relationship_ids
        }
        if not referenced_ids:
            continue

        container = element
        while (
            container.getparent() is not None
            and container.tag not in REMOVABLE_CONTAINER_TAGS
        ):
            container = container.getparent()

        if container.tag in REMOVABLE_CONTAINER_TAGS:
            identity = id(container)
            if identity not in removed_nodes:
                parent = container.getparent()
                if parent is not None:
                    parent.remove(container)
                    removed_nodes.add(identity)
                    removed_count += 1
            continue

        # Non-drawing references are kept as content, but their orphan
        # relationship attributes must be removed to leave valid XML.
        for attr in list(element.attrib):
            if attr in REL_ATTRS and element.attrib[attr] in relationship_ids:
                del element.attrib[attr]
                removed_count += 1

    return (
        etree.tostring(
            root,
            encoding="UTF-8",
            xml_declaration=True,
            standalone=None,
        ),
        removed_count,
    )


def repair_docx(source: Path, output: Path) -> dict[str, object]:
    source_hash_before = _sha256(source)
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        member_names = {item.filename for item in members}
        replacements: dict[str, bytes] = {}
        removed_by_source: dict[str, set[str]] = {}
        removed_relationships: list[dict[str, str]] = []

        for item in members:
            if not item.filename.endswith(".rels"):
                continue
            xml_bytes = archive.read(item.filename)
            parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
            root = etree.fromstring(xml_bytes, parser=parser)
            source_part = _source_part_for_relationship_part(item.filename)
            removed_ids: set[str] = set()

            for relationship in list(root):
                if relationship.tag != REL_TAG:
                    continue
                if relationship.get("TargetMode") == "External":
                    continue
                target = relationship.get("Target", "")
                resolved = _resolve_internal_target(source_part, target)
                target_is_null = posixpath.basename(resolved).upper() == "NULL"
                target_is_missing = bool(resolved) and resolved not in member_names
                if not (target_is_null or target_is_missing):
                    continue

                relation_id = relationship.get("Id", "")
                root.remove(relationship)
                removed_ids.add(relation_id)
                removed_relationships.append(
                    {
                        "relation_id": relation_id,
                        "relationship_type": _relationship_type_name(
                            relationship.get("Type", "")
                        ),
                        "reason": (
                            "null_target"
                            if target_is_null
                            else "missing_internal_target"
                        ),
                    }
                )

            if removed_ids:
                replacements[item.filename] = etree.tostring(
                    root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=None,
                )
                if source_part:
                    removed_by_source[source_part] = removed_ids

        removed_reference_nodes = 0
        for source_part, relation_ids in removed_by_source.items():
            if source_part not in member_names:
                continue
            repaired_xml, removed_count = _remove_orphan_references(
                archive.read(source_part),
                relation_ids,
            )
            replacements[source_part] = repaired_xml
            removed_reference_nodes += removed_count

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)

        try:
            with zipfile.ZipFile(
                temporary_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as repaired:
                for item in members:
                    repaired.writestr(
                        item,
                        replacements.get(item.filename, archive.read(item.filename)),
                    )
            shutil.move(temporary_path, output)
        finally:
            temporary_path.unlink(missing_ok=True)

    source_hash_after = _sha256(source)
    if source_hash_after != source_hash_before:
        raise RuntimeError("source DOCX changed during repair")

    return {
        "alias": source.stem,
        "source_sha256": source_hash_before,
        "output_sha256": _sha256(output),
        "removed_relationships": sorted(
            removed_relationships,
            key=lambda item: (
                item["relation_id"],
                item["relationship_type"],
                item["reason"],
            ),
        ),
        "removed_reference_nodes": removed_reference_nodes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records: list[dict[str, object]] = []
    for source in args.sources:
        if not source.is_file():
            raise FileNotFoundError(f"input DOCX does not exist: {source.name}")
        output = args.output_dir / f"{source.stem}.repaired.docx"
        records.append(repair_docx(source, output))

    manifest = {
        "schema_version": 1,
        "status": "PASS",
        "documents": records,
    }
    manifest_path = args.output_dir / "repair_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "documents": len(records),
                "removed_relationships": sum(
                    len(record["removed_relationships"]) for record in records
                ),
                "manifest": manifest_path.name,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
