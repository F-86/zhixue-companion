"""数据库操作层 —— 用户认证查询"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, StudentRegisterRequest, TeacherRegisterRequest

_bearer = HTTPBearer()


def register_student(req: StudentRegisterRequest, db: Session) -> User:
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="学号已注册")
    user = User(
        username=req.username, name=req.name, role="student",
        password_hash=hash_password(req.password),
        extra={"class_name": req.class_name},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def register_teacher(req: TeacherRegisterRequest, db: Session) -> User:
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="工号已注册")
    user = User(
        username=req.username, name=req.name, role="teacher",
        password_hash=hash_password(req.password),
        extra={"courses": req.courses},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(req: LoginRequest, db: Session) -> dict:
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token({"sub": user.id, "role": user.role})
    from app.core.config import settings
    return {
        "token": token,
        "expires_in": settings.access_token_expire_minutes * 60,
        "user": {"id": user.id, "username": user.username, "name": user.name, "role": user.role},
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖：解析 JWT，返回当前用户对象"""
    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="仅学生可访问")
    return current_user


def require_teacher(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="仅教师可访问")
    return current_user
