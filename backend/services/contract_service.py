"""Contract register: list with remaining ceilings, and saving a reviewed (PDF or manual) contract."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select

from db import models as m

from . import audit
from .contract_extraction import check
from .engine_adapter import dec
from .errors import conflict, unprocessable
from .workspace_service import contract_consumption

SOURCES = ("REGISTER", "PDF")


def _s(v) -> str | None:
    return None if v is None else str(dec(v))


def list_contracts(session) -> list[dict]:
    approved = contract_consumption(session)
    lines: dict[str, list] = {}
    for ln in session.scalars(select(m.ContractLine).order_by(m.ContractLine.contract_id, m.ContractLine.item_code)):
        lines.setdefault(ln.contract_id, []).append(
            {"item_code": ln.item_code, "description": ln.description, "uom": ln.uom, "rate": _s(ln.rate)})
    suppliers = {s.supplier_id: s.status for s in session.scalars(select(m.Supplier))}
    out = []
    for c in session.scalars(select(m.Contract).order_by(m.Contract.contract_id)):
        cap, used = dec(c.value_cap), dec(c.consumed_value or 0)
        out.append({"contract_id": c.contract_id, "supplier_id": c.supplier_id, "supplier_name": c.supplier_name,
                    "supplier_status": suppliers.get(c.supplier_id), "start_date": c.start_date.isoformat(),
                    "end_date": c.end_date.isoformat(), "value_cap": str(cap), "consumed_value": str(used),
                    "remaining": str(cap - used), "approved_orders_value": _s(approved.get(c.contract_id, Decimal(0))),
                    "source": c.source, "pdf_filename": c.pdf_filename, "warnings": c.warnings or [],
                    "lines": lines.get(c.contract_id, [])})
    return out


def _dec(v, field: str) -> Decimal:
    try:
        d = Decimal(str(v).replace(",", ""))
    except (InvalidOperation, AttributeError):
        raise unprocessable(f"{field} must be a number") from None
    if not d.is_finite():
        raise unprocessable(f"{field} must be a number")
    return d


def save(session, body: dict, *, user: str, role: str) -> dict:
    cid = (body.get("contract_id") or "").strip()
    sid = (body.get("supplier_id") or "").strip()
    if not cid or not sid:
        raise unprocessable("contract_id and supplier_id are required")
    supplier = session.get(m.Supplier, sid)
    if supplier is None:
        raise unprocessable(f"Unknown supplier {sid}")
    try:
        start, end = date.fromisoformat(str(body.get("start_date"))), date.fromisoformat(str(body.get("end_date")))
    except ValueError:
        raise unprocessable("start_date and end_date must be YYYY-MM-DD") from None
    if start > end:
        raise unprocessable("start_date must be on or before end_date")
    cap = _dec(body.get("value_cap"), "value_cap")
    if cap <= 0:
        raise unprocessable("value_cap must be greater than zero")
    consumed = _dec(body.get("consumed_value") or 0, "consumed_value")
    if consumed < 0:
        raise unprocessable("consumed_value must not be negative")
    source = (body.get("source") or "PDF").upper()
    if source not in SOURCES:
        raise unprocessable(f"source must be one of {', '.join(SOURCES)}")
    raw_lines = body.get("lines") or []
    if not raw_lines:
        raise unprocessable("A contract needs at least one line")
    items = {i.item_code: i for i in session.scalars(select(m.Item))}
    lines, seen = [], set()
    for ln in raw_lines:
        code = (ln.get("item_code") or "").strip()
        if code not in items:
            raise unprocessable(f"Unknown item {code or '(blank)'}")
        if code in seen:
            raise unprocessable(f"Item {code} appears twice")
        seen.add(code)
        rate = _dec(ln.get("rate"), f"rate for {code}")
        if rate <= 0:
            raise unprocessable(f"rate for {code} must be greater than zero")
        lines.append((code, (ln.get("description") or items[code].description).strip(),
                      (ln.get("uom") or items[code].uom).strip(), rate))
    warnings = check(session, {"supplier_id": sid}, [])
    existing = session.get(m.Contract, cid)
    before = None
    if existing is not None:
        if not body.get("replace"):
            raise conflict(f"Contract {cid} already exists; choose replace to overwrite it with this document")
        before = next((c for c in list_contracts(session) if c["contract_id"] == cid), None)
        session.execute(delete(m.ContractLine).where(m.ContractLine.contract_id == cid))
        row = existing
    else:
        row = m.Contract(contract_id=cid)
    row.supplier_id, row.supplier_name = sid, (body.get("supplier_name") or supplier.name).strip()
    row.start_date, row.end_date, row.value_cap, row.consumed_value = start, end, cap, consumed
    row.source, row.pdf_filename, row.created_by = source, body.get("pdf_filename"), user
    row.warnings = warnings
    if existing is None:
        session.add(row)
    session.flush()
    for code, desc, uom, rate in lines:
        session.add(m.ContractLine(contract_id=cid, item_code=code, description=desc, uom=uom, rate=rate))
    session.flush()
    after = next(c for c in list_contracts(session) if c["contract_id"] == cid)
    audit.record(session, user, role, "contract_replaced" if before else "contract_added", "contract", cid,
                 before, after, None)
    session.commit()
    return after
