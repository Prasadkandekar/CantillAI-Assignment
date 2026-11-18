"""Output rows, reason text, the final supplier-eligibility guard and the CSV writer."""
from __future__ import annotations

import csv
import io

from .eligibility import is_eligible_id
from .models import NOT_PROCESSED, OUTPUT_COLUMNS, EngineInvariantError, OutputRow
from .money import fmt_inr, fmt_plain

WARNING_SEPARATOR = " | "
SUGGESTION_SEPARATOR = ";"


def _valuation_text(val, ceval, strategy) -> str:
    ref = val.reference or {}
    src = val.source
    if src == "contract":
        if ref.get("selected"):
            return "" if strategy == "contract" else f"valued at contract {ref['contract_id']} rate {fmt_plain(val.unit_price)}"
        left = [f"{cid} {fmt_inr(amt)} left" for cid, amt in sorted(ceval.remaining_by_contract.items())]
        return (f"contract ceiling insufficient ({'; '.join(left)}); "
                f"valued at lowest contract rate {fmt_plain(val.unit_price)} ({ref['contract_id']})")
    if src == "last_po":
        return f"valued at last PO {ref['po_number']} ({ref['po_date']}) {fmt_plain(val.unit_price)}"
    if src == "standard_price":
        return f"valued at standard price {fmt_plain(val.unit_price)}"
    if src == "requester_estimate":
        return f"valued at requester estimate {fmt_plain(val.unit_price)}"
    return "not valued"


def _supplier_text(strategy, res, rule, ceval) -> str:
    if strategy == "contract":
        left = ceval.remaining_by_contract.get(res.contract_id)
        return (f"contract {res.contract_id} supplier {res.supplier_id} rate {fmt_plain(res.unit_price)}, "
                f"ceiling left {fmt_inr(left)} before this requirement")
    if strategy == "preferred_first":
        ref = res.reference or {}
        where = (f"ref PO {ref.get('po_number')} ({ref.get('po_date')})" if ref.get("source") == "po"
                 else f"ref contract {ref.get('contract_id')}")
        return f"1st preferred {res.supplier_id} {where} at {fmt_plain(res.unit_price)}"
    if strategy == "suggest":
        count = rule.count
        text = f"suggested {SUGGESTION_SEPARATOR.join(res.suggested) or 'none'}"
        if len(res.suggested) < (count or 0):
            text += f" ({len(res.suggested)} of {count} available)"
        return text
    return ""


def reason_text(policy, rule, res, val, ceval, warnings) -> str:
    if rule is None:
        main = f"No rule in policy v{policy.version} matched"
    else:
        strategy = rule.outcome["supplier"]["strategy"]
        parts = [_supplier_text(strategy, res, rule, ceval), _valuation_text(val, ceval, strategy)]
        if strategy == "contract":
            parts.reverse()
        note = rule.outcome.get("note")
        if note:
            parts.append(note)
        body = "; ".join(p for p in parts if p)
        main = f"v{policy.version} \u00a7{rule.clause}: {body}" if body else f"v{policy.version} \u00a7{rule.clause}"
    if warnings:
        main += WARNING_SEPARATOR + WARNING_SEPARATOR.join(warnings)
    return main


def build_rows(raw_lines, rejected, requirements, decisions, master, params_for_version) -> list[OutputRow]:
    by_row_rejected = {r.row_index: r for r in rejected}
    by_row_req = {}
    for req in requirements:
        for line in req.lines:
            by_row_req[line.row_index] = (req, line)
    rows = []
    for raw in raw_lines:
        rj = by_row_rejected.get(raw.row_index)
        if rj is not None:
            rows.append(OutputRow(rj.pr_no, rj.pr_line, rj.resolved_item_code, "", "", "", NOT_PROCESSED, "", "",
                                  "", "", rj.policy_version, rj.reason))
            continue
        req, line = by_row_req[raw.row_index]
        d = decisions[req.group_id]
        params = params_for_version[req.policy_version]
        for sid in ([d.supplier_id] if d.supplier_id else []) + list(d.suggested):
            if not is_eligible_id(sid, master, params):
                raise EngineInvariantError(
                    f"supplier {sid} is not eligible but was chosen for {req.group_id} ({line.key})")
        rows.append(OutputRow(
            pr_no=line.pr_no,
            pr_line=str(line.pr_line),
            resolved_item_code=line.resolved_item_code,
            group_id=req.group_id,
            po_id=d.po_id or "",
            decision=d.decision or "",
            route=d.route,
            supplier_id=d.supplier_id or "",
            unit_price=fmt_plain(d.unit_price),
            group_value_inr=fmt_plain(d.value),
            suggested_supplier_ids=SUGGESTION_SEPARATOR.join(d.suggested),
            policy_version=d.policy_version,
            reason=d.reason,
        ))
    return rows


def rows_to_csv(rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(OUTPUT_COLUMNS)
    for r in rows:
        w.writerow([getattr(r, c) for c in OUTPUT_COLUMNS])
    return buf.getvalue()


def write_csv(rows, path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(rows_to_csv(rows))
