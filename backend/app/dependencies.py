"""FastAPI dependency injection providers."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.reportgen_bridge import ReportGenBridge

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)

# Singleton bridge instance
_bridge: Optional[ReportGenBridge] = None


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
    expire = datetime.utcnow() + timedelta(hours=settings.access_token_expire_hours)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Extract current user from JWT token. Returns None if no token."""
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", 0))
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    """Require authenticated user."""
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    """Require admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user
