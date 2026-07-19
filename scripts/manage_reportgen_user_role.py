#!/usr/bin/env python3
# 步骤: 管理 ReportGen Web 用户的最小权限角色
# 上游: storage/db/reportgen_web.sqlite 或 --database-url 指定的数据库
# 输出: 默认仅预览 JSON；传入 --apply 后更新 users.role 并写入审计日志
# 种子: 不适用
"""Safely assign least-privilege ReportGen Web user roles."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal  # noqa: E402
from app.models.audit import AuditLog  # noqa: E402
from app.models.user import User  # noqa: E402

ALLOWED_ROLES = frozenset({"operator", "reviewer", "knowledge_manager", "admin"})


def update_user_role(
    db: Session,
    *,
    username: str,
    role: str,
    apply: bool = False,
) -> dict:
    """Validate and optionally persist one role transition."""
    normalized_username = username.strip()
    normalized_role = role.strip().lower()
    if normalized_role not in ALLOWED_ROLES:
        raise ValueError(f"unsupported role: {normalized_role}")
    user = db.query(User).filter(User.username == normalized_username).first()
    if user is None:
        raise ValueError("user not found")

    previous_role = user.role
    changed = previous_role != normalized_role
    if changed and previous_role == "admin" and normalized_role != "admin":
        active_admins = (
            db.query(User)
            .filter(User.role == "admin", User.is_active.is_(True))
            .count()
        )
        if user.is_active and active_admins <= 1:
            raise ValueError("refusing to demote the last active admin")

    result = {
        "username": normalized_username,
        "previous_role": previous_role,
        "role": normalized_role,
        "changed": changed,
        "applied": bool(apply and changed),
    }
    if not apply or not changed:
        return result

    user.role = normalized_role
    db.add(
        AuditLog(
            user_id=None,
            action="user.role_changed",
            resource_type="user",
            resource_id=str(user.id),
            details=json.dumps(
                {
                    "operator": "role-management-cli",
                    "source": "role-management-cli",
                    "previous_role": previous_role,
                    "status": normalized_role,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    db.commit()
    return result


def _session_factory(database_url: str | None):
    if not database_url:
        return SessionLocal
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    return sessionmaker(bind=engine, expire_on_commit=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, choices=sorted(ALLOWED_ROLES))
    parser.add_argument("--database-url")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="persist the validated role transition; without this flag it is a dry run",
    )
    args = parser.parse_args()

    db = _session_factory(args.database_url)()
    try:
        result = update_user_role(
            db,
            username=args.username,
            role=args.role,
            apply=args.apply,
        )
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 2
    finally:
        db.close()

    print(json.dumps({"status": "PASS", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
