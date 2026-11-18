"""API test fixtures: a seeded SQLite database built with Alembic, copied per test module."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
SAMPLE = BACKEND.parent / "pr_batches" / "sample_pr_batch.csv"
HEADERS = {"X-User": "tester", "X-Role": "procurement"}
BUYER = {"X-User": "buyer1", "X-Role": "buyer"}


def _sqlite_url(path: Path) -> str:
    return "sqlite:///" + str(path).replace("\\", "/")


def build_seeded_db(path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    from db import base
    from seed.load import seed

    os.environ["DATABASE_URL"] = _sqlite_url(path)
    base.reset()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "db" / "migrations"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    with base.SessionLocal() as s:
        seed(s)
    base.reset()


@pytest.fixture(scope="session")
def seeded_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "template.db"
    build_seeded_db(path)
    return path


@pytest.fixture()
def client(seeded_template, tmp_path, monkeypatch):
    """A TestClient on a fresh copy of the seeded database."""
    from fastapi.testclient import TestClient

    from db import base
    db_path = tmp_path / "corvo.db"
    shutil.copy(seeded_template, db_path)
    monkeypatch.setenv("DATABASE_URL", _sqlite_url(db_path))
    monkeypatch.setenv("LLM_DISABLED", "1")
    base.reset()
    from api.main import app
    with TestClient(app) as c:
        yield c
    base.reset()


def upload_sample(client, params=None, data=None, path: Path = SAMPLE):
    with open(path, "rb") as fh:
        return client.post("/api/process-batch", params=params or {}, data=data or {},
                           files={"file": (path.name, fh, "text/csv")}, headers=HEADERS)
