"""Request dependencies: DB session and the stub identity from X-User / X-Role headers."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from db.base import SessionLocal

ROLES = ("requester", "buyer", "procurement")
MAX_USER_LEN = 64


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@dataclass(frozen=True)
class User:
    name: str
    role: str
    department: str = ""


def _role(value: str | None) -> str:
    role = (value or "requester").strip().lower()
    if role not in ROLES:
        raise HTTPException(400, f"X-Role must be one of {', '.join(ROLES)}")
    return role


def current_user(x_user: str | None = Header(default=None), x_role: str | None = Header(default=None),
                 x_department: str | None = Header(default=None)) -> User:
    name = (x_user or "").strip()
    if not name or len(name) > MAX_USER_LEN:
        raise HTTPException(400, "X-User header required")
    return User(name, _role(x_role), (x_department or "").strip()[:128])


def optional_user(x_user: str | None = Header(default=None), x_role: str | None = Header(default=None),
                  x_department: str | None = Header(default=None)) -> User:
    """For the scripted batch API: callers without headers are recorded as 'api'."""
    name = (x_user or "").strip()[:MAX_USER_LEN] or "api"
    return User(name, _role(x_role), (x_department or "").strip()[:128])


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"This action needs role {' or '.join(roles)}")
        return user
    return dep
