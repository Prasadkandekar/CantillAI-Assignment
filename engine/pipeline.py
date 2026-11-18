"""Orchestration: normalise -> match -> club -> per requirement (contracts, value, rules) -> consolidate -> rows."""
from __future__ import annotations

from collections import Counter

from .clubbing import club
from .conditions import jsonable
from .consolidation import consolidate
from .contracts import ContractLedger, evaluate_contracts
from .facts import FactContext
from .matching import Matcher
from .models import NEW_ITEM, NOT_PROCESSED, BatchResult, ContractEval, Decision
from .normalise import normalise
from .output import build_rows, reason_text
from .policy import Policy, PolicySet
from .rules import walk_rules
from .valuation import value_requirement

FLAG_TEXT = {
    "urgent_in_text": "description mentions 'urgent' but urgency is {urgency}",
    "as_per_sample": "'as per sample': the supplier needs the sample",
}


def _policy_set(policies) -> PolicySet:
    if isinstance(policies, PolicySet):
        return policies
    if isinstance(policies, (Policy, dict)):
        return PolicySet([policies])
    return PolicySet(list(policies))


def _warnings(req, ceval, val) -> list[str]:
    out = []
    multi = len(req.lines) > 1
    for line in req.lines:
        prefix = f"{line.key}: " if multi else ""
        for flag in line.flags:
            if flag in FLAG_TEXT:
                out.append(prefix + FLAG_TEXT[flag].format(urgency=line.urgency))
            elif flag == "low_confidence":
                cands = ", ".join(c for c, _ in line.match.candidates)
                out.append(prefix + f"low-confidence match; candidates {cands}; buyer to verify")
    for c, why in ceval.skipped:
        out.append(f"contract {c.contract_id} skipped: {why}")
    out.extend(val.warnings)
    return out


def _ranking_trace(preferred):
    return [{
        "supplier_id": r.supplier_id, "rank": r.rank, "score": str(r.score),
        "reference_price": jsonable(r.reference_price), "reference": r.reference,
        "factors": {k: {"raw": jsonable(f.raw), "scaled": str(f.scaled), "weight": str(f.weight),
                        "contribution": str(f.contribution)} for k, f in r.factors.items()},
    } for r in preferred]


def decide_requirement(req, master, policy, ledger) -> Decision:
    params = policy.params
    is_new = req.item_code == NEW_ITEM
    ceval = ContractEval() if is_new else evaluate_contracts(req, master, params, ledger)
    val = value_requirement(req, master, params, ceval, is_new)
    ctx = FactContext(req, master, params, ceval, val)
    rule, res, trace = walk_rules(policy, ctx)
    warnings = _warnings(req, ceval, val)
    trace.update({
        "group_id": req.group_id,
        "lines": [l.key for l in req.lines],
        "valuation": {"source": val.source, "unit_price": jsonable(val.unit_price), "value": str(val.value),
                      "reference": val.reference,
                      "last_po": None if val.last_po is None else {
                          "po_number": val.last_po.po_number, "po_date": val.last_po.po_date.isoformat(),
                          "supplier_id": val.last_po.supplier_id, "unit_price": str(val.last_po.unit_price)}},
        "contracts": {
            "applicable": [c.contract_id for c in ceval.applicable],
            "skipped": [{"contract_id": c.contract_id, "reason": why} for c, why in ceval.skipped],
            "fitting": [c.contract_id for c in ceval.fitting],
            "selected": ceval.selected.contract_id if ceval.selected else None,
            "remaining_before": {k: str(v) for k, v in ceval.remaining_by_contract.items()},
        },
        "warnings": warnings,
    })
    if ctx._preferred is not None:
        trace["ranking"] = _ranking_trace(ctx._preferred)
    reason = reason_text(policy, rule, res, val, ceval, warnings)
    if rule is None:
        return Decision(req.group_id, policy.version, None, None, NOT_PROCESSED, None, None, (), None,
                        reason, trace, value=val.value)
    out = rule.outcome
    trace["outcome"] = jsonable(out)
    trace["supplier"] = {"strategy": out["supplier"]["strategy"], "supplier_id": res.supplier_id,
                         "unit_price": jsonable(res.unit_price), "suggested": list(res.suggested),
                         "reference": res.reference, "contract_id": res.contract_id}
    if res.debit is not None and res.contract_id:
        ledger.debit(res.contract_id, res.debit, req.group_id)
    return Decision(req.group_id, policy.version, rule.summary, out["decision"], out["route"], res.supplier_id,
                    res.unit_price, tuple(res.suggested), res.contract_id, reason, trace, value=val.value,
                    debit=res.debit)


def run_batch(raw_lines, master, policies, pin: str | None = None, as_of=None,
              matcher: Matcher | None = None) -> BatchResult:
    pset = _policy_set(policies)
    if pin:
        pset.by_label(pin)
    valid, rejected = normalise(raw_lines, master, pset, pin=pin, as_of=as_of, matcher=matcher)
    by_version = {p.version: p for p in pset.policies}
    params_for_version = {k: p.params for k, p in by_version.items()}
    requirements = club(valid, params_for_version)
    order = sorted(requirements, key=lambda r: (r.first_created_at, r.first.pr_no, r.first.pr_line))
    ledger = ContractLedger(master.contracts)
    decisions = {}
    for req in order:
        decisions[req.group_id] = decide_requirement(req, master, by_version[req.policy_version], ledger)
    consolidate(order, decisions, params_for_version)
    for req in order:
        d = decisions[req.group_id]
        d.trace["po_id"] = d.po_id
    rows = build_rows(raw_lines, rejected, requirements, decisions, master, params_for_version)
    versions_used = Counter(r.policy_version for r in rows if r.policy_version)
    return BatchResult(
        rows=rows,
        requirements=requirements,
        decisions=decisions,
        versions_used=dict(versions_used),
        warnings=[],
        counts=dict(Counter(r.route for r in rows)),
        requirement_counts=dict(Counter(decisions[r.group_id].route for r in requirements)),
        rejected=rejected,
        ledger=dict(ledger.consumed),
    )
