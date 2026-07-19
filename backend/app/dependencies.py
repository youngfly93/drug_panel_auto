"""FastAPI dependency injection providers."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.task import Task
from app.models.upload import Upload
from app.models.user import User
from app.services.reportgen_bridge import ReportGenBridge

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)

# Singleton bridge instance
_bridge: Optional[ReportGenBridge] = None

TASK_PRIVILEGED_ROLES = frozenset({"admin", "reviewer"})
KNOWLEDGE_MANAGER_ROLES = frozenset({"admin", "knowledge_manager"})
REFERENCE_READER_ROLES = frozenset({"admin", "reviewer", "knowledge_manager"})


def get_bridge() -> ReportGenBridge:
    """Get the singleton ReportGenBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = ReportGenBridge(
            config_dir=settings.upstream_config_dir,
            template_dir=settings.upstream_template_dir,
        )
    return _bridge


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.access_token_expire_hours
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def authenticate_access_token(token: str, db: Session) -> User:
    """Validate a bearer token and return its active user."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", 0))
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Extract current user from JWT token. Returns None if no token."""
    if credentials is None:
        return None
    return authenticate_access_token(credentials.credentials, db)


def require_user(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Require authenticated user."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    request.state.current_user = user
    return user


def user_can_access_task(user: User, task: Task) -> bool:
    """Return whether an authenticated user may access a task and its artifacts."""
    return user.role in TASK_PRIVILEGED_ROLES or task.user_id == user.id


def user_can_access_upload(user: User, upload: Upload) -> bool:
    """Return whether an authenticated user may consume an uploaded workbook."""
    return user.role in TASK_PRIVILEGED_ROLES or upload.user_id == user.id


def require_task_access(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> User:
    """Protect any route containing ``task_id`` with owner/reviewer scope."""
    task_id = request.path_params.get("task_id")
    if not task_id:
        return user
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is not None and not user_can_access_task(user, task):
        # Use 404 to avoid disclosing another operator's task UUID.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return user


def require_upload_access(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> User:
    """Protect any route containing ``upload_id`` with owner/reviewer scope."""
    upload_id = request.path_params.get("upload_id")
    if not upload_id:
        return user
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if upload is not None and not user_can_access_upload(user, upload):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="上传记录不存在")
    return user


def require_reviewer(user: User = Depends(require_user)) -> User:
    """Require a report reviewer or administrator."""
    if user.role not in TASK_PRIVILEGED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer required",
        )
    return user


def require_knowledge_manager(user: User = Depends(require_user)) -> User:
    """Require a knowledge/reference maintainer or administrator."""
    if user.role not in KNOWLEDGE_MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Knowledge manager required",
        )
    return user


def require_reference_reader(user: User = Depends(require_user)) -> User:
    """Require a role allowed to see historical golden report content."""
    if user.role not in REFERENCE_READER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reference library access required",
        )
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    """Require admin role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin required"
        )
    return user
