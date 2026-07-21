from __future__ import annotations

import bcrypt
from fastapi import HTTPException, Request, status
from sqlalchemy import select

from jobapply.db.models import User
from jobapply.db.session import session_scope

SESSION_USER_KEY = "user_id"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_user(email: str, display_name: str, password: str) -> int:
    with session_scope() as session:
        user = User(email=email, display_name=display_name, password_hash=hash_password(password))
        session.add(user)
        session.flush()
        return user.id


def authenticate(email: str, password: str) -> int | None:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user and verify_password(password, user.password_hash):
            return user.id
    return None


def verify_current_password(user_id: int, password: str) -> bool:
    with session_scope() as session:
        user = session.get(User, user_id)
        return bool(user and verify_password(password, user.password_hash))


def update_password(user_id: int, new_password: str) -> None:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user:
            user.password_hash = hash_password(new_password)


def get_user_display(user_id: int) -> dict | None:
    with session_scope() as session:
        user = session.get(User, user_id)
        return {"email": user.email, "display_name": user.display_name} if user else None


def list_users() -> list[dict]:
    with session_scope() as session:
        users = session.scalars(select(User).order_by(User.id)).all()
        return [
            {"id": u.id, "email": u.email, "display_name": u.display_name, "created_at": u.created_at}
            for u in users
        ]


def get_user_id_by_email(email: str) -> int | None:
    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == email))
        return user.id if user else None


def current_user_id(request: Request) -> int | None:
    return request.session.get(SESSION_USER_KEY)


def require_login(request: Request) -> int:
    user_id = current_user_id(request)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user_id
