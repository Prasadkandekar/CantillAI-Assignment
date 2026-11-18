"""Database engine and session factory, configured from DATABASE_URL."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Every entry point (uvicorn, alembic, seed.load, tests) reads the gitignored repo-root .env,
# so DATABASE_URL (Neon) is picked up everywhere. Real environment variables still win.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

DEFAULT_URL = "sqlite:///./corvo.db"


class Base(DeclarativeBase):
    pass


def normalise_url(url: str) -> str:
    """Render/Heroku style postgres URLs -> the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def database_url() -> str:
    return normalise_url(os.environ.get("DATABASE_URL") or DEFAULT_URL)


_engine = None
_session_factory = None
_engine_url = None


def get_engine():
    global _engine, _session_factory, _engine_url
    url = database_url()
    if _engine is None or url != _engine_url:
        if _engine is not None:
            _engine.dispose()
        kwargs = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
        _engine_url = url
    return _engine


def SessionLocal():
    get_engine()
    return _session_factory()


def reset() -> None:
    """Drop the cached engine (tests switch DATABASE_URL between modules)."""
    global _engine, _session_factory, _engine_url
    if _engine is not None:
        _engine.dispose()
    _engine = _session_factory = _engine_url = None
