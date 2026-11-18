"""Preferred supplier lists per item as of a date, with factor contributions, and the CSV export."""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from engine import PolicyNotFound, build_preferred_list
from engine.money import fmt_plain

from .engine_adapter import master_from_db, policy_set
from .errors import not_found, unprocessable

EXPORT_COLUMNS = ("item_code", "rank", "supplier_id", "reference_price")


def _policy(session, as_of: date, pin: str | None):
    pset = policy_set(session)
    try:
        policy = pset.select(as_of, pin=pin or None)
    except PolicyNotFound as exc:
        raise not_found(str(exc)) from None
    if policy is None:
        raise unprocessable(f"No approved policy version is effective on {as_of.isoformat()}")
    return policy


def _jsonable(v):
    return str(v) if isinstance(v, Decimal) else v


def lists(session, as_of: date, item_code: str | None = None, pin: str | None = None) -> dict:
    policy = _policy(session, as_of, pin)
    master = master_from_db(session)
    if item_code and item_code not in master.items:
        raise not_found(f"Item {item_code} not found")
    codes = [item_code] if item_code else sorted(master.items)
    out = []
    for code in codes:
        item = master.items[code]
        ranked = build_preferred_list(code, as_of, master, policy.params)
        out.append({
            "item_code": code, "description": item.description, "category": item.category,
            "suppliers": [{
                "rank": r.rank, "supplier_id": r.supplier_id, "name": master.suppliers[r.supplier_id].name,
                "score": str(r.score), "reference_price": fmt_plain(r.reference_price), "reference": r.reference,
                "po_count": r.po_count, "last_po_date": r.last_po_date.isoformat() if r.last_po_date else None,
                "has_contract": r.has_contract,
                "factors": {k: {"raw": _jsonable(f.raw), "scaled": str(f.scaled), "weight": str(f.weight),
                                "contribution": str(f.contribution)} for k, f in r.factors.items()},
            } for r in ranked]})
    return {"as_of": as_of.isoformat(), "policy_version": policy.version,
            "weights": {k: str(v) for k, v in policy.params["ranking_weights"].items()},
            "export_count": policy.params["preferred_export_count"], "items": out}


def export_csv(session, as_of: date, pin: str | None = None) -> str:
    data = lists(session, as_of, None, pin)
    top = data["export_count"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(EXPORT_COLUMNS)
    for item in data["items"]:
        for s in item["suppliers"][:top]:
            w.writerow([item["item_code"], s["rank"], s["supplier_id"], s["reference_price"]])
    return buf.getvalue()
