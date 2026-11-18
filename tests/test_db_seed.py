"""Seeded database: counts, the DB adapter reproduces the CSV path, approved policies are immutable."""
import os

import pytest
from sqlalchemy import func, select

from db import base
from db import models as m
from services.engine_adapter import master_from_db, policy_set
from engine import run_batch
from tests.helpers import load_doc, master_data, run, sample_lines


@pytest.fixture()
def session(client):
    s = base.SessionLocal()
    yield s
    s.close()


def test_seed_counts(session):
    md = master_data()
    def count(model):
        return session.scalar(select(func.count()).select_from(model))
    assert count(m.Plant) == len(md.plants)
    assert count(m.Item) == len(md.items)
    assert count(m.Supplier) == len(md.suppliers)
    assert count(m.POHistory) == sum(len(v) for v in md.po_by_item.values())
    assert count(m.Contract) == len(md.contracts)
    pdf = session.scalars(select(m.Contract).where(m.Contract.source == "PDF")).all()
    assert {c.contract_id for c in pdf} == {c.contract_id for c in md.contracts.values() if c.source == "PDF"}
    assert all(c.consumed_value == 0 for c in pdf)
    active = session.scalars(select(m.PolicyVersion)).all()
    assert [(p.version_label, p.status) for p in active] == [(load_doc()["version"], m.ACTIVE)]


def test_adapter_gives_same_rows_as_csv_path(session):
    db_result = run_batch(sample_lines(), master_from_db(session), policy_set(session))
    csv_result = run(load_doc())
    assert [r.as_dict() for r in db_result.rows] == [r.as_dict() for r in csv_result.rows]


def test_approved_policy_document_is_immutable(session):
    row = session.scalar(select(m.PolicyVersion).where(m.PolicyVersion.status == m.ACTIVE))
    doc = dict(row.document)
    doc["title"] = "edited"
    row.document = doc
    with pytest.raises(m.ImmutablePolicyError):
        session.flush()
    session.rollback()
    row = session.scalar(select(m.PolicyVersion).where(m.PolicyVersion.status == m.ACTIVE))
    session.delete(row)
    with pytest.raises(m.ImmutablePolicyError):
        session.flush()
    session.rollback()


def test_database_url_normalised():
    assert base.normalise_url("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert base.normalise_url("postgresql://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert base.normalise_url("sqlite:///x.db") == "sqlite:///x.db"
    assert os.environ["DATABASE_URL"].startswith("sqlite")
