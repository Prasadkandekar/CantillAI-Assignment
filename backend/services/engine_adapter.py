"""DB rows -> engine MasterData / PolicySet. The only place that translates between the two worlds."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from db import models as m
from engine import Policy, PolicySet, build_master, load_policy
from engine.models import Contract, ContractLine, Item, PORecord, Supplier


def dec(value) -> Decimal | None:
    """DB numerics come back padded to the column scale (84.9800); give the engine the plain value."""
    if value is None:
        return None
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return d.quantize(Decimal(1))
    return d.normalize()


def supplier_to_engine(s: m.Supplier) -> Supplier:
    return Supplier(s.supplier_id, s.name, s.city,
                    tuple(c.strip() for c in (s.categories or "").split(";") if c.strip()),
                    s.status, dec(s.on_time_pct), dec(s.quality_rating))


def contract_to_engine(c: m.Contract, lines) -> Contract:
    return Contract(
        c.contract_id, c.supplier_id, c.supplier_name or "", c.start_date, c.end_date, dec(c.value_cap),
        dec(c.consumed_value or 0), c.source,
        {ln.item_code: ContractLine(c.contract_id, ln.item_code, ln.description or "", ln.uom or "", dec(ln.rate))
         for ln in lines})


def master_from_db(session):
    plants = {p.plant: p.name for p in session.scalars(select(m.Plant))}
    items = {i.item_code: Item(i.item_code, i.description, i.uom, i.category, i.item_type, dec(i.standard_price))
             for i in session.scalars(select(m.Item))}
    suppliers = {s.supplier_id: supplier_to_engine(s) for s in session.scalars(select(m.Supplier))}
    pos = [PORecord(p.po_number, p.po_date, p.supplier_id, p.item_code, dec(p.quantity), p.uom, dec(p.unit_price),
                    p.plant, bool(p.delivered_on_time)) for p in session.scalars(select(m.POHistory))]
    lines_by_contract: dict[str, list] = {}
    for ln in session.scalars(select(m.ContractLine)):
        lines_by_contract.setdefault(ln.contract_id, []).append(ln)
    contracts = {c.contract_id: contract_to_engine(c, lines_by_contract.get(c.contract_id, []))
                 for c in session.scalars(select(m.Contract))}
    return build_master(plants, items, suppliers, pos, contracts)


def approved_versions(session) -> list[m.PolicyVersion]:
    """ACTIVE and SUPERSEDED versions in approval order (later approval wins a tie on effective date)."""
    rows = session.scalars(select(m.PolicyVersion).where(m.PolicyVersion.status.in_(m.APPROVED_STATUSES)))
    return sorted(rows, key=lambda r: (r.approved_at or r.created_at, r.id))


def to_policy(row: m.PolicyVersion) -> Policy:
    return load_policy(row.document)


def policy_set(session, extra: list[Policy] | None = None) -> PolicySet:
    policies = [to_policy(r) for r in approved_versions(session)]
    return PolicySet(policies + list(extra or []))


def active_version(session) -> m.PolicyVersion | None:
    return session.scalar(select(m.PolicyVersion).where(m.PolicyVersion.status == m.ACTIVE))


def version_by_label(session, label: str) -> m.PolicyVersion | None:
    return session.scalar(select(m.PolicyVersion).where(m.PolicyVersion.version_label == label))
