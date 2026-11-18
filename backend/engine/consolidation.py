"""PO consolidation: requirements ending in a PO share a PO when their keys match and they were
raised within the consolidation window of the PO's first requirement."""
from __future__ import annotations

from datetime import timedelta

CONSOLIDATION_KEY_FIELDS = ("supplier_id", "plant", "route", "decision", "contract_id")
PO_ID_FORMAT = "PO-{:04d}"


def _key(req, decision, keys):
    values = {
        "supplier_id": decision.supplier_id,
        "plant": req.plant,
        "route": decision.route,
        "decision": decision.decision,
        "contract_id": decision.contract_id,
    }
    return tuple(values[k] for k in keys)


def consolidate(requirements, decisions: dict, params_for_version: dict) -> dict:
    """Assign po_id on each consolidated decision; returns group_id -> po_id."""
    eligible = []
    for req in requirements:
        d = decisions.get(req.group_id)
        if d is None or d.decision is None:
            continue
        if d.decision in params_for_version[req.policy_version]["consolidate_decisions"]:
            eligible.append(req)
    eligible.sort(key=lambda r: (r.first_created_at, r.first.pr_no, r.first.pr_line))
    open_pos = []   # (first_created_at, version, key, po_id)
    assigned = {}
    for req in eligible:
        d = decisions[req.group_id]
        target = None
        for first_at, version, key, po_id in open_pos:
            if version != req.policy_version:
                continue
            params = params_for_version[version]
            if key != _key(req, d, params["consolidation_keys"]):
                continue
            gap = req.first_created_at - first_at
            if timedelta(0) <= gap <= timedelta(hours=float(params["consolidation_hours"])):
                target = po_id
                break
        if target is None:
            target = PO_ID_FORMAT.format(len(open_pos) + 1)
            params = params_for_version[req.policy_version]
            open_pos.append((req.first_created_at, req.policy_version,
                             _key(req, d, params["consolidation_keys"]), target))
        d.po_id = target
        assigned[req.group_id] = target
    return assigned
