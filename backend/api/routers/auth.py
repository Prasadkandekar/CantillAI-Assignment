"""Demo login: seeded users, scrypt password hashing, HMAC-signed bearer token.

Additive only. Other routers still trust the X-User / X-Role headers (see api/deps.py);
this router gives the UI a real sign-in step and a role per session. Demo-grade, not a security boundary.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from api.deps import ROLES

log = logging.getLogger("corvo.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

DEMO_PASSWORD = "corvo-demo"
DEMO_USERS = {
    "requester@corvo.demo": {"name": "R. Requester", "department": "Maintenance", "roles": ["requester"]},
    "buyer@corvo.demo": {"name": "A. Buyer", "department": "Procurement", "roles": ["requester", "buyer"]},
    "procurement@corvo.demo": {"name": "P. Head", "department": "Procurement",
                               "roles": ["requester", "buyer", "procurement"]},
}
TTL_SECONDS = int(float(os.environ.get("AUTH_TTL_HOURS", "8")) * 3600)

_hashes: dict[str, str] = {}
_secret: bytes | None = None


def _hash(password: str, salt: bytes) -> str:
    return salt.hex() + "$" + hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()


def _verify(password: str, stored: str) -> bool:
    salt_hex, _ = stored.split("$", 1)
    return hmac.compare_digest(_hash(password, bytes.fromhex(salt_hex)), stored)


def _stored_hash(email: str) -> str:
    if email not in _hashes:  # lazy: scrypt only when the first login happens
        _hashes[email] = _hash(DEMO_PASSWORD, secrets.token_bytes(16))
    return _hashes[email]


def _key() -> bytes:
    global _secret
    if _secret is None:
        env = os.environ.get("AUTH_SECRET")
        if env:
            _secret = env.encode()
        else:
            log.warning("AUTH_SECRET not set; using a per-process secret (sessions reset on restart)")
            _secret = secrets.token_hex(32).encode()
    return _secret


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> str:
    return _b64(hmac.new(_key(), payload, hashlib.sha256).digest())


def make_token(email: str, role: str) -> str:
    payload = _b64(json.dumps({"sub": email, "role": role, "exp": int(time.time()) + TTL_SECONDS}).encode())
    return f"{payload}.{_sign(payload.encode())}"


def _user_body(email: str, role: str) -> dict:
    u = DEMO_USERS[email]
    return {"email": email, "name": u["name"], "department": u["department"], "role": role,
            "allowed_roles": list(u["roles"])}


def _claims(authorization: str | None) -> dict:
    bad = HTTPException(401, "Invalid or expired session")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise bad
    token = authorization[7:].strip()
    try:
        payload, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(payload.encode())):
            raise bad
        data = json.loads(_unb64(payload))
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - any malformed token is simply unauthorized
        raise bad from None
    if data.get("exp", 0) < time.time() or data.get("sub") not in DEMO_USERS or data.get("role") not in ROLES:
        raise bad
    return data


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=1, max_length=128)
    role: str | None = None


class RoleIn(BaseModel):
    role: str


@router.post("/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    user = DEMO_USERS.get(email)
    stored = _stored_hash(email) if user else _stored_hash("requester@corvo.demo")  # keep timing level
    ok = _verify(body.password, stored)
    if not user or not ok:
        log.info("login failed email=%s", email[:128])
        raise HTTPException(401, "Invalid email or password")
    role = body.role or user["roles"][-1]
    if role not in user["roles"]:
        raise HTTPException(403, "Role not allowed for this user")
    return {"token": make_token(email, role), "user": _user_body(email, role)}


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    c = _claims(authorization)
    return {"user": _user_body(c["sub"], c["role"])}


@router.post("/role")
def switch_role(body: RoleIn, authorization: str | None = Header(default=None)):
    c = _claims(authorization)
    if body.role not in DEMO_USERS[c["sub"]]["roles"]:
        raise HTTPException(403, "Role not allowed for this user")
    return {"token": make_token(c["sub"], body.role), "user": _user_body(c["sub"], body.role)}
