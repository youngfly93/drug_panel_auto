"""Authentication endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import create_access_token, pwd_context, require_user
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserInfo
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[TokenResponse])
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_access_token(user.id)
    return ApiResponse(data=TokenResponse(access_token=token))


@router.get("/me", response_model=ApiResponse[UserInfo])
def get_me(user: User = Depends(require_user)):
    return ApiResponse(
        data=UserInfo(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            is_active=user.is_active,
        )
    )
