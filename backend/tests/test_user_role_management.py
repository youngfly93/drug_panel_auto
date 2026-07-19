import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.manage_reportgen_user_role import update_user_role  # noqa: E402

from app.database import Base  # noqa: E402
from app.models.audit import AuditLog  # noqa: E402
from app.models.user import User  # noqa: E402


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _user(username: str, role: str) -> User:
    return User(
        username=username,
        password_hash="synthetic-hash",
        display_name=username,
        role=role,
        is_active=True,
    )


def test_role_change_is_dry_run_by_default_and_audited_on_apply():
    db = _session()
    db.add_all([_user("admin", "admin"), _user("reporter", "admin")])
    db.commit()

    preview = update_user_role(db, username="reporter", role="operator")
    assert preview["applied"] is False
    assert db.query(User).filter(User.username == "reporter").one().role == "admin"

    applied = update_user_role(
        db,
        username="reporter",
        role="operator",
        apply=True,
    )
    assert applied["applied"] is True
    assert db.query(User).filter(User.username == "reporter").one().role == "operator"
    event = db.query(AuditLog).filter(AuditLog.action == "user.role_changed").one()
    assert json.loads(event.details)["previous_role"] == "admin"
    assert json.loads(event.details)["status"] == "operator"


def test_role_change_refuses_to_demote_last_active_admin():
    db = _session()
    db.add(_user("admin", "admin"))
    db.commit()

    with pytest.raises(ValueError, match="last active admin"):
        update_user_role(db, username="admin", role="reviewer", apply=True)

    assert db.query(User).filter(User.username == "admin").one().role == "admin"
