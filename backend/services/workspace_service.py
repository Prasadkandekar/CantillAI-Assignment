"""Buyer workspace: requirement list/detail, approve (creates orders) and override with audit.

Decision chain per requirement: one ENGINE decision, then OVERRIDE decisions. The effective decision
is the latest one that is not OVERRIDDEN. APPROVED and OVERRIDDEN are terminal.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select

from db import models as m
from engine import build_preferred_list, is_eligible, load_policy

from . import audit, batch_service
from .engine_adapter import dec, master_from_db, supplier_to_engine
from .errors import conflict, not_found, unprocessable

PROPOSED, APPROVED, OVERRIDDEN = "PROPOSED", "APPROVED", "OVERRIDDEN"
PO_DECISION = "PO"        # output-column value meaning "a purchase order" (the other is SOURCING_REQUEST)
MIN_COMMENT, MAX_COMMENT = 3, 2000


def _num(v) -> str | None:
    return None if v is None else str(dec(v))


def decision_dict(d: m.Decision) -> dict:
    return {"id": d.id, "kind": d.kind, "overrides_decision_id": d.overrides_decision_id, "decision": d.decision,
            "route": d.route, "supplier_id": d.supplier_id, "unit_price": _num(d.unit_price),
            "suggested": d.suggested or [], "po_id": d.po_id, "contract_id": d.contract_id, "reason": d.reason,
            "status": d.status, "comment": d.comment, "created_by": d.created_by,
            "created_at": d.created_at.isoformat() + "Z"}


def _decisions(session, req_ids) -> dict[int, list[m.Decision]]:
    out: dict[int, list] = {}
    if not req_ids:
        return out
    for d in session.scalars(select(m.Decision).where(m.Decision.requirement_id.in_(list(req_ids)))
                             .order_by(m.Decision.id)):
        out.setdefault(d.requirement_id, []).append(d)
    return out


def effective(chain: list[m.Decision]) -> m.Decision:
    live = [d for d in chain if d.status != OVERRIDDEN]
    return live[-1] if live else chain[-1]


def _resolve_run(session, run_id: int | None) -> m.Run | None:
    if run_id is not None:
        run = session.get(m.Run, run_id)
        if run is None or run.kind == "DRY_RUN":
            raise not_found(f"Run {run_id} not found")
        return run
    return batch_service.latest_run(session, "BATCH") or batch_service.latest_run(session, "CHAT_PREVIEW")


def _version_labels(session) -> dict[int, str]:
    return dict(session.execute(select(m.PolicyVersion.id, m.PolicyVersion.version_label)).all())


def _orders_for(session, req_ids) -> dict[int, dict]:
    if not req_ids:
        return {}
    rows = session.execute(select(m.OrderLine.requirement_id, m.Order.order_no, m.Order.run_id)
                           .join(m.Order, m.Order.id == m.OrderLine.order_id)
                           .where(m.OrderLine.requirement_id.in_(list(req_ids))))
    return {rid: {"order_no": no, "display": f"R{run}/{no}"} for rid, no, run in rows}


def list_requirements(session, run_id: int | None = None, route: str | None = None, status: str | None = None):
    run = _resolve_run(session, run_id)
    if run is None:
        return {"run": None, "requirements": [], "status_counts": {}}
    reqs = list(session.scalars(select(m.Requirement).where(m.Requirement.run_id == run.id)
                                .order_by(m.Requirement.first_created_at, m.Requirement.id)))
    chains = _decisions(session, [r.id for r in reqs])
    items = dict(session.execute(select(m.Item.item_code, m.Item.description)).all())
    labels = _version_labels(session)
    orders = _orders_for(session, [r.id for r in reqs])
    out, counts = [], {}
    for r in reqs:
        eff = effective(chains[r.id])
        counts[eff.status] = counts.get(eff.status, 0) + 1
        if route and eff.route != route:
            continue
        if status and eff.status != status:
            continue
        out.append({
            "id": r.id, "group_id": r.group_id, "item_code": r.item_code,
            "item_description": items.get(r.item_code) or (r.lines or [{}])[0].get("description", ""),
            "plant": r.plant, "requirement_date": r.requirement_date.isoformat(), "total_qty": _num(r.total_qty),
            "value": _num(r.value), "is_emergency": r.is_emergency, "line_count": len(r.line_ids),
            "pr_lines": r.line_ids, "policy_version": labels.get(r.policy_version_id),
            "effective": decision_dict(eff), "overridden": eff.kind == "OVERRIDE", "order": orders.get(r.id)})
    return {"run": batch_service.run_summary(session, run), "requirements": out, "status_counts": counts}


def _get_req(session, req_id: int) -> m.Requirement:
    r = session.get(m.Requirement, req_id)
    if r is None:
        raise not_found(f"Requirement {req_id} not found")
    return r


def _policy_for(session, req: m.Requirement):
    row = session.get(m.PolicyVersion, req.policy_version_id) if req.policy_version_id else None
    if row is None:
        raise conflict("The requirement has no policy version")
    return load_policy(row.document)


def _po_group(session, req: m.Requirement, eff: m.Decision):
    """Requirements of the run whose effective decision is still the ENGINE decision with this po_id."""
    if eff.kind != "ENGINE" or not eff.po_id:
        return [], 0
    reqs = list(session.scalars(select(m.Requirement).where(m.Requirement.run_id == req.run_id)))
    chains = _decisions(session, [r.id for r in reqs])
    members, excluded = [], 0
    for r in reqs:
        chain = chains[r.id]
        engine_d = chain[0]
        if engine_d.po_id != eff.po_id:
            continue
        e = effective(chain)
        if e.id == engine_d.id and e.status == PROPOSED:
            members.append((r, e))
        elif e.id != engine_d.id:
            excluded += 1
    return members, excluded


def detail(session, req_id: int) -> dict:
    req = _get_req(session, req_id)
    chain = _decisions(session, [req.id])[req.id]
    eff = effective(chain)
    engine_d = chain[0]
    trace = engine_d.trace or {}
    labels = _version_labels(session)
    suppliers = {s.supplier_id: s for s in session.scalars(select(m.Supplier))}
    item = session.get(m.Item, req.item_code)
    contract = None
    cid = engine_d.contract_id or (trace.get("contracts") or {}).get("selected")
    if cid:
        c = session.get(m.Contract, cid)
        if c is not None:
            line = session.scalar(select(m.ContractLine).where(m.ContractLine.contract_id == cid,
                                                               m.ContractLine.item_code == req.item_code))
            contract = {"contract_id": c.contract_id, "supplier_id": c.supplier_id, "supplier_name": c.supplier_name,
                        "source": c.source, "start_date": c.start_date.isoformat(), "end_date": c.end_date.isoformat(),
                        "value_cap": _num(c.value_cap), "rate": _num(line.rate) if line else None,
                        "remaining_before": (trace.get("contracts") or {}).get("remaining_before", {}).get(cid)}
    ranking = trace.get("ranking")
    if ranking is None and item is not None:
        policy = _policy_for(session, req)
        master = master_from_db(session)
        ranking = [{"supplier_id": r.supplier_id, "rank": r.rank, "score": str(r.score),
                    "reference_price": None if r.reference_price is None else str(r.reference_price),
                    "reference": r.reference,
                    "factors": {k: {"raw": f.raw if not isinstance(f.raw, Decimal) else str(f.raw),
                                    "scaled": str(f.scaled), "weight": str(f.weight),
                                    "contribution": str(f.contribution)} for k, f in r.factors.items()}}
                   for r in build_preferred_list(req.item_code, req.requirement_date, master, policy.params)]
    for r in ranking or []:
        s = suppliers.get(r["supplier_id"])
        r["name"] = s.name if s else ""
    members, excluded = _po_group(session, req, eff)
    order = _orders_for(session, [req.id]).get(req.id)
    return {
        "id": req.id, "run_id": req.run_id, "group_id": req.group_id, "item_code": req.item_code,
        "item": None if item is None else {"description": item.description, "uom": item.uom,
                                           "category": item.category, "item_type": item.item_type},
        "plant": req.plant, "requirement_date": req.requirement_date.isoformat(),
        "first_created_at": req.first_created_at.isoformat(sep=" ", timespec="minutes"),
        "total_qty": _num(req.total_qty), "value": _num(req.value), "is_emergency": req.is_emergency,
        "policy_version": labels.get(req.policy_version_id), "lines": req.lines or [],
        "effective": decision_dict(eff), "original": decision_dict(engine_d),
        "decisions": [decision_dict(d) for d in chain],
        "why": {"fired": trace.get("fired"), "policy_version": trace.get("policy_version"),
                "facts": trace.get("facts", {}), "rules_checked": trace.get("rules_checked", []),
                "valuation": trace.get("valuation"), "contracts": trace.get("contracts"),
                "warnings": trace.get("warnings", []), "supplier": trace.get("supplier")},
        "contract": contract, "ranking": ranking or [],
        "supplier_names": {sid: s.name for sid, s in suppliers.items()},
        "po_group": {"po_id": eff.po_id if eff.kind == "ENGINE" else None,
                     "display": f"R{req.run_id}/{eff.po_id}" if eff.kind == "ENGINE" and eff.po_id else None,
                     "members": [{"id": r.id, "group_id": r.group_id} for r, _ in members],
                     "excluded_overridden": excluded},
        "order": order,
        "audit": audit.list_rows(session, "requirement", str(req.id)),
    }


def _next_src(session, run_id: int) -> str:
    n = session.scalar(select(func.count()).select_from(m.Order)
                       .where(m.Order.run_id == run_id, m.Order.type == "SOURCING")) or 0
    return f"SRC-{n + 1:04d}"


def approve(session, req_id: int, *, user: str, role: str) -> dict:
    req = _get_req(session, req_id)
    chain = _decisions(session, [req.id])[req.id]
    eff = effective(chain)
    if eff.status == APPROVED:
        raise conflict("already approved")
    if not eff.decision:
        raise conflict("No decision to approve (no rule fired); override it with a decision first")
    if eff.kind == "ENGINE" and eff.po_id:
        members, excluded = _po_group(session, req, eff)
        order_no, otype = eff.po_id, "PO"
    else:
        members, excluded = [(req, eff)], 0
        if eff.decision == PO_DECISION:
            order_no, otype = (f"PO-OVR-{eff.id}" if eff.kind == "OVERRIDE" else f"PO-D{eff.id}"), "PO"
        else:
            order_no, otype = _next_src(session, req.run_id), "SOURCING"
    if session.scalar(select(m.Order).where(m.Order.run_id == req.run_id, m.Order.order_no == order_no)):
        raise conflict(f"Order R{req.run_id}/{order_no} already exists")
    order = m.Order(order_no=order_no, type=otype, route=eff.route, supplier_id=eff.supplier_id, plant=req.plant,
                    run_id=req.run_id, created_by=user)
    session.add(order)
    session.flush()
    for r, d in members:
        before = decision_dict(d)
        session.add(m.OrderLine(order_id=order.id, requirement_id=r.id, decision_id=d.id, quantity=r.total_qty,
                                unit_price=d.unit_price, contract_id=d.contract_id))
        if d.contract_id and d.debit is not None:
            session.add(m.ContractConsumption(contract_id=d.contract_id, requirement_id=r.id, value=d.debit,
                                              requirement_date=r.requirement_date, order_id=order.id))
        d.status = APPROVED
        audit.record(session, user, role, "approve", "requirement", r.id, before,
                     {**decision_dict(d), "order_no": order_no, "order_display": f"R{req.run_id}/{order_no}"}, None)
    session.commit()
    return {"order_no": order_no, "display": f"R{req.run_id}/{order_no}", "type": otype,
            "requirements": [r.id for r, _ in members], "excluded_overridden": excluded}


def _eligible_supplier(session, sid: str, params: dict) -> None:
    s = session.get(m.Supplier, sid)
    if s is None:
        raise unprocessable(f"Unknown supplier {sid}")
    if not is_eligible(supplier_to_engine(s), params):
        raise unprocessable(f"Supplier {sid} is {s.status} and cannot receive POs or suggestions")


def override(session, req_id: int, body: dict, *, user: str, role: str) -> dict:
    req = _get_req(session, req_id)
    comment = (body.get("comment") or "").strip()
    if len(comment) < MIN_COMMENT or len(comment) > MAX_COMMENT:
        raise unprocessable(f"A comment of {MIN_COMMENT} to {MAX_COMMENT} characters is required to override")
    decision = (body.get("decision") or "").strip()
    route = (body.get("route") or "").strip()
    if not decision or not route:
        raise unprocessable("decision and route are required")
    supplier_id = (body.get("supplier_id") or "").strip() or None
    suggested = [s.strip() for s in body.get("suggested_supplier_ids") or [] if s and s.strip()]
    if decision == PO_DECISION and not supplier_id:
        raise unprocessable("A PO needs a supplier_id")
    unit_price = body.get("unit_price")
    if unit_price not in (None, ""):
        try:
            unit_price = Decimal(str(unit_price))
        except InvalidOperation:
            raise unprocessable("unit_price must be a number") from None
        if unit_price < 0:
            raise unprocessable("unit_price must not be negative")
    else:
        unit_price = None
    chain = _decisions(session, [req.id])[req.id]
    prev = effective(chain)
    if prev.status == APPROVED:
        raise conflict("The decision is already approved and can no longer be overridden")
    params = _policy_for(session, req).params
    for sid in ([supplier_id] if supplier_id else []) + suggested:
        _eligible_supplier(session, sid, params)
    before = decision_dict(prev)
    prev.status = OVERRIDDEN
    new = m.Decision(requirement_id=req.id, kind="OVERRIDE", overrides_decision_id=prev.id, decision=decision,
                     route=route, supplier_id=supplier_id, unit_price=unit_price, suggested=suggested, po_id=None,
                     contract_id=None, debit=None, reason=f"Override by {user}: {comment}", trace=None,
                     status=PROPOSED, comment=comment, created_by=user)
    session.add(new)
    session.flush()
    audit.record(session, user, role, "override", "requirement", req.id, before, decision_dict(new), comment)
    session.commit()
    return decision_dict(new)


def contract_consumption(session) -> dict[str, Decimal]:
    rows = session.execute(select(m.ContractConsumption.contract_id, func.sum(m.ContractConsumption.value))
                           .group_by(m.ContractConsumption.contract_id))
    return {cid: dec(v) for cid, v in rows}
