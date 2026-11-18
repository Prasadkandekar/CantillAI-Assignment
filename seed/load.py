"""Seed the database from the kit CSVs, the PDF-only contracts JSON and policy v5.0.

    python -m seed.load [--if-empty]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from db import models as m
from db.base import SessionLocal
from engine import load_master, validate

ROOT = Path(__file__).resolve().parent.parent
PDF_CONTRACTS = ROOT / "seed" / "pdf_contracts.json"
POLICY_FILE = ROOT / "engine" / "policies" / "policy_v5_0.json"
SEED_USER = "seed"


def is_empty(session) -> bool:
    return session.scalar(select(func.count()).select_from(m.PolicyVersion)) == 0


def seed(session, root: Path = ROOT) -> dict:
    master = load_master(root, PDF_CONTRACTS)
    pdf_files = {d["contract_id"]: d.get("pdf_filename") for d in json.loads(PDF_CONTRACTS.read_text("utf-8"))}
    session.add_all(m.Plant(plant=k, name=v) for k, v in master.plants.items())
    session.add_all(m.Item(item_code=i.item_code, description=i.description, uom=i.uom, category=i.category,
                           item_type=i.item_type, standard_price=i.standard_price) for i in master.items.values())
    session.add_all(m.Supplier(supplier_id=s.supplier_id, name=s.name, city=s.city,
                               categories="; ".join(s.categories), status=s.status, on_time_pct=s.on_time_pct,
                               quality_rating=s.quality_rating) for s in master.suppliers.values())
    session.flush()
    po_count = 0
    for pos in master.po_by_item.values():
        for p in pos:
            session.add(m.POHistory(po_number=p.po_number, po_date=p.po_date, supplier_id=p.supplier_id,
                                    item_code=p.item_code, quantity=p.quantity, uom=p.uom, unit_price=p.unit_price,
                                    plant=p.plant, delivered_on_time=p.delivered_on_time))
            po_count += 1
    for c in master.contracts.values():
        session.add(m.Contract(contract_id=c.contract_id, supplier_id=c.supplier_id, supplier_name=c.supplier_name,
                               start_date=c.start_date, end_date=c.end_date, value_cap=c.value_cap,
                               consumed_value=c.consumed_value, source=c.source,
                               pdf_filename=pdf_files.get(c.contract_id), created_by=SEED_USER, warnings=[]))
        session.flush()
        for ln in c.lines.values():
            session.add(m.ContractLine(contract_id=c.contract_id, item_code=ln.item_code,
                                       description=ln.description, uom=ln.uom, rate=ln.rate))
    doc = json.loads(POLICY_FILE.read_text("utf-8"))
    result = validate(doc)
    if result.errors:
        raise SystemExit(f"Seed policy is invalid: {[str(e) for e in result.errors]}")
    session.add(m.PolicyVersion(
        version_label=str(doc["version"]), status=m.ACTIVE, effective_from=date.fromisoformat(doc["effective_from"]),
        document=doc, source_text=None, source_filename=POLICY_FILE.name, validation=result.as_dict(),
        created_by=SEED_USER, approved_by=SEED_USER, approved_at=m.utcnow()))
    session.commit()
    return {"plants": len(master.plants), "items": len(master.items), "suppliers": len(master.suppliers),
            "po_history": po_count, "contracts": len(master.contracts), "policy": doc["version"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m seed.load")
    ap.add_argument("--if-empty", action="store_true", help="do nothing when the database already has data")
    args = ap.parse_args(argv)
    with SessionLocal() as session:
        if args.if_empty and not is_empty(session):
            print("seed: database already has data, skipped")
            return 0
        counts = seed(session)
    print("seed: loaded " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
