#!/usr/bin/env python3
# 步骤: 正式金标准注册
# 上游: 外部报告组终版 DOCX + panels/*/golden_cases 脱敏契约
# 输出: 运行时 reference_reports 记录 + .golden.json 校验凭据
# 种子: 不适用（确定性校验）
"""Register an external reviewed DOCX in the runtime reference-report store."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-id", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--docx", required=True)
    parser.add_argument(
        "--contract",
        required=True,
        help="Committed de-identified panels/<panel>/golden_cases/*.yaml contract",
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--storage-root")
    parser.add_argument("--inactive", action="store_true")
    args = parser.parse_args()

    source = Path(args.docx).resolve()
    if not source.is_file() or source.suffix.lower() != ".docx":
        parser.error("--docx must point to an existing .docx file")
    if args.storage_root:
        storage_root = Path(args.storage_root).resolve()
        (storage_root / "db").mkdir(parents=True, exist_ok=True)
        os.environ["RG_WEB_STORAGE_ROOT"] = str(storage_root)

    for path in (ROOT, BACKEND):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    from app.database import Base, SessionLocal, engine
    from app.services.reference_report_service import (
        create_formal_golden_attestation,
        create_reference_report,
        delete_reference_report,
        validate_formal_golden_registration,
    )

    try:
        validated = validate_formal_golden_registration(
            panel_id=args.panel_id,
            case_id=args.case_id,
            reference_docx=source,
            contract_path=args.contract,
        )
    except ValueError as exc:
        parser.error(str(exc))

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        reference = None
        try:
            with source.open("rb") as handle:
                reference = create_reference_report(
                    db,
                    panel_id=args.panel_id,
                    case_id=args.case_id,
                    name=args.name,
                    notes=args.notes or None,
                    active=not args.inactive,
                    original_filename=source.name,
                    fileobj=handle,
                )
            attestation = create_formal_golden_attestation(
                reference,
                contract_path=validated["contract_path"],
            )
        except Exception:
            if reference is not None:
                delete_reference_report(db, reference)
            raise
        print(
            json.dumps(
                {
                    "id": reference.id,
                    "panel_id": reference.panel_id,
                    "case_id": reference.case_id,
                    "name": reference.name,
                    "active": reference.active,
                    "checksum_sha256": reference.checksum_sha256,
                    "stored_path": reference.stored_path,
                    "formal_golden_verified": True,
                    "contract_alias": attestation["case_alias"],
                    "contract_sha256": attestation["contract_sha256"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
