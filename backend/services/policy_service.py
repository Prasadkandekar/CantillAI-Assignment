"""Policy versions: drafts from documents or chat, JSON editing, validation, diff, dry run, approve, discard."""
from __future__ import annotations

import copy
from collections import Counter
from datetime import date

from sqlalchemy import select

from db import models as m
from engine import PolicySet, PolicyValidationError, load_policy, run_batch, validate

from . import audit, batch_service, policy_reader
from .dates import long_date
from .engine_adapter import active_version, approved_versions, master_from_db, to_policy
from .errors import conflict, not_found, unprocessable
from .policy_diff import diff_and_bullets

COMPARED = ("decision", "route", "supplier_id", "unit_price", "group_value_inr", "suggested_supplier_ids")
EFFECTIVE_DATE_QUESTION = "From what date should this apply?"


def _get(session, version_id: int) -> m.PolicyVersion:
    row = session.get(m.PolicyVersion, version_id)
    if row is None:
        raise not_found(f"Policy version {version_id} not found")
    return row


def _base_doc(session, row: m.PolicyVersion | None = None) -> dict:
    if row is not None and row.base_version_id:
        base = session.get(m.PolicyVersion, row.base_version_id)
        if base is not None:
            return base.document
    act = active_version(session)
    return act.document if act else {}


def _validation(session, doc: dict) -> dict:
    act = active_version(session)
    return validate(doc, base=act.document if act else None).as_dict()


def summary(row: m.PolicyVersion) -> dict:
    return {"id": row.id, "version_label": row.version_label, "status": row.status,
            "effective_from": row.effective_from.isoformat() if row.effective_from else None,
            "created_by": row.created_by, "created_at": row.created_at.isoformat() + "Z",
            "approved_by": row.approved_by, "approved_at": row.approved_at.isoformat() + "Z" if row.approved_at else None,
            "source_filename": row.source_filename, "base_version_id": row.base_version_id}


def detail(session, row: m.PolicyVersion) -> dict:
    base = _base_doc(session, row) if row.base_version_id else {}
    validation = dict(row.validation or {})
    reader = validation.pop("reader", None)
    out = summary(row)
    out.update({
        "document": row.document,
        "needs_effective_date": row.status == m.DRAFT and not row.document.get("effective_from"),
        "validation": {"errors": validation.get("errors", []), "warnings": validation.get("warnings", [])},
        "diff": diff_and_bullets(base, row.document) if base else {"structural": None, "bullets": []},
        "reader": reader,
        "source_text": row.source_text,
    })
    if out["needs_effective_date"]:
        out["question"] = EFFECTIVE_DATE_QUESTION
    return out


def list_versions(session) -> list[dict]:
    return [summary(r) for r in session.scalars(select(m.PolicyVersion).order_by(m.PolicyVersion.id.desc()))]


def _parse_date(value, field="effective_from") -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise unprocessable(f"{field} must be a date in YYYY-MM-DD format") from None


def create_draft(session, text: str, *, user: str, role: str, filename: str | None = None,
                 effective_from: str | None = None, mode: str = "auto") -> m.PolicyVersion:
    base_row = active_version(session)
    if base_row is None:
        raise conflict("No active policy version to amend")
    if not (text or "").strip():
        raise unprocessable("The amendment text is empty")
    labels = list(session.scalars(select(m.PolicyVersion.version_label)))
    label = policy_reader.next_label(base_row.version_label, labels)
    plants = {p.plant: p.name for p in session.scalars(select(m.Plant))}
    categories = sorted(set(session.scalars(select(m.Item.category))))
    res = policy_reader.read(text, base_row.document, label=label, plants=plants, categories=categories, mode=mode)
    doc = res.document
    eff = _parse_date(effective_from) or (_parse_date(res.effective_from) if res.effective_from else None)
    doc["effective_from"] = eff.isoformat() if eff else None
    validation = _validation(session, doc)
    validation["reader"] = {"mode": res.mode, "unrecognised": res.unrecognised, "applied": res.applied,
                            "llm_error": res.llm_error, "informational": res.informational, "kind": res.kind}
    row = m.PolicyVersion(version_label=label, status=m.DRAFT, effective_from=eff, document=doc,
                          source_text=text[:200_000], source_filename=filename, base_version_id=base_row.id,
                          validation=validation, created_by=user)
    session.add(row)
    session.flush()
    audit.record(session, user, role, "policy_draft_created", "policy_version", row.id, None,
                 {"version_label": label, "source_filename": filename, "reader": res.mode}, None)
    session.commit()
    return row


def update_draft(session, version_id: int, *, user: str, role: str, document: dict | None = None,
                 effective_from=None, version_label: str | None = None, clear_effective_from: bool = False):
    row = _get(session, version_id)
    if row.status != m.DRAFT:
        raise conflict(f"Policy version {row.version_label} is {row.status}; only drafts can be edited")
    before = copy.deepcopy(row.document)
    doc = copy.deepcopy(document if document is not None else row.document)
    if not isinstance(doc, dict):
        raise unprocessable("document must be a JSON object")
    label = (version_label or str(doc.get("version") or row.version_label)).strip()
    if not label:
        raise unprocessable("version_label must not be empty")
    if label != row.version_label:
        clash = session.scalar(select(m.PolicyVersion).where(m.PolicyVersion.version_label == label))
        if clash is not None and clash.id != row.id:
            raise conflict(f"Version label {label} is already used")
    doc["version"] = label
    eff = _parse_date(effective_from) if effective_from not in (None, "") else None
    if eff is not None:
        doc["effective_from"] = eff.isoformat()
    elif clear_effective_from:
        doc["effective_from"] = None
    doc_eff = doc.get("effective_from")
    row.effective_from = _parse_date(doc_eff) if isinstance(doc_eff, str) and doc_eff else None
    row.version_label = label
    row.document = doc
    reader = (row.validation or {}).get("reader")
    validation = _validation(session, doc)
    if reader:
        validation["reader"] = reader
    row.validation = validation
    audit.record(session, user, role, "policy_draft_edited", "policy_version", row.id, before, doc, None)
    session.commit()
    return row


def _loaded_draft(row: m.PolicyVersion, effective_from: date | None = None):
    doc = copy.deepcopy(row.document)
    if effective_from is not None:
        doc["effective_from"] = effective_from.isoformat()
    try:
        return load_policy(doc)
    except PolicyValidationError as exc:
        raise unprocessable({"message": "The draft has validation errors",
                             "errors": [e.as_dict() for e in exc.errors]}) from None


def _changed(base_rows, new_rows) -> list[dict]:
    def key(r):
        return f"{r.pr_no}/{r.pr_line}"

    def membership(rows):
        groups: dict[str, set] = {}
        for r in rows:
            if r.group_id:
                groups.setdefault(r.group_id, set()).add(key(r))
        return {key(r): frozenset(groups.get(r.group_id, ())) for r in rows}

    mb, mn = membership(base_rows), membership(new_rows)
    new_by = {key(r): r for r in new_rows}
    out = []
    for r in base_rows:
        n = new_by.get(key(r))
        if n is None:
            continue
        if any(getattr(r, f) != getattr(n, f) for f in COMPARED) or mb[key(r)] != mn[key(r)]:
            out.append({"pr_no": r.pr_no, "pr_line": r.pr_line,
                        "before": {f: getattr(r, f) for f in COMPARED + ("group_id", "policy_version")},
                        "after": {f: getattr(n, f) for f in COMPARED + ("group_id", "policy_version")}})
    return out


def _route_deltas(base_rows, new_rows) -> dict:
    b, n = Counter(r.route for r in base_rows), Counter(r.route for r in new_rows)
    return {k: n[k] - b[k] for k in sorted(set(b) | set(n)) if n[k] != b[k]}


def dry_run(session, version_id: int, user: str) -> dict:
    row = _get(session, version_id)
    if row.status != m.DRAFT:
        raise conflict(f"Policy version {row.version_label} is {row.status}; dry runs are for drafts")
    batch = batch_service.latest_csv_batch(session)
    if batch is None:
        raise conflict("No batch uploaded yet")
    raw = batch_service.raw_lines_for_batches(session, [batch.id])
    draft = _loaded_draft(row)
    master = master_from_db(session)
    approved = [to_policy(r) for r in approved_versions(session)]
    baseline = run_batch(raw, master, PolicySet(approved))
    pinned = run_batch(raw, master, PolicySet(approved + [draft]), pin=draft.version)
    pinned_changes = _changed(baseline.rows, pinned.rows)
    out = {"batch_id": batch.id, "filename": batch.filename, "total_lines": len(baseline.rows),
           "pinned_changed_lines": len(pinned_changes), "version_label": row.version_label,
           "effective_from": draft.effective_from.isoformat() if draft.effective_from else None}
    if draft.effective_from is not None:
        candidate = run_batch(raw, master, PolicySet(approved + [draft]))
        changes = _changed(baseline.rows, candidate.rows)
        before_eff = sum(1 for r in raw if (r.values.get("created_at") or "")[:10] < draft.effective_from.isoformat())
        out.update(changed_lines=len(changes), lines_before_effective_date=before_eff,
                   route_deltas=_route_deltas(baseline.rows, candidate.rows), changes=changes,
                   versions_used=candidate.versions_used)
        result_for_store = candidate
    else:
        out.update(changed_lines=None, lines_before_effective_date=None,
                   route_deltas=_route_deltas(baseline.rows, pinned.rows), changes=pinned_changes,
                   versions_used=pinned.versions_used)
        result_for_store = pinned
    out["pinned_route_deltas"] = _route_deltas(baseline.rows, pinned.rows)
    out["headline"] = headline(out)
    run = batch_service.store_run(session, batch, result_for_store, user, None if draft.effective_from else draft.version,
                                  None, "DRY_RUN")
    out["run_id"] = run.id
    session.commit()
    return out


def headline(out: dict) -> str:
    m_, p = out["total_lines"], out["pinned_changed_lines"]
    if out.get("changed_lines") is None:
        return f"{p} of {m_} lines change if applied to every line (set an effective date for the dated figure)"
    text = f"{out['changed_lines']} of {m_} lines change ({p} if applied to every line)"
    k = out.get("lines_before_effective_date") or 0
    if k:
        text += (f"; {k} of {m_} lines fall before this version's effective date and keep the version in force "
                 "on their dates")
    return text


def approve(session, version_id: int, *, user: str, role: str, effective_from=None) -> m.PolicyVersion:
    row = _get(session, version_id)
    if row.status != m.DRAFT:
        raise conflict(f"Policy version {row.version_label} is {row.status}; only drafts can be approved")
    eff = _parse_date(effective_from) or row.effective_from or _parse_date(row.document.get("effective_from"))
    if eff is None:
        raise unprocessable("Effective date required")
    doc = copy.deepcopy(row.document)
    doc["effective_from"] = eff.isoformat()
    doc["version"] = row.version_label
    act = active_version(session)
    result = validate(doc, base=act.document if act else None)
    if result.errors:
        raise unprocessable({"message": "The draft has validation errors",
                             "errors": [e.as_dict() for e in result.errors]})
    if act is not None and act.effective_from and eff < act.effective_from:
        raise conflict(f"effective date must be on or after {act.effective_from.isoformat()} (v{act.version_label})")
    now = m.utcnow()
    reader = (row.validation or {}).get("reader")
    validation = result.as_dict()
    if reader:
        validation["reader"] = reader
    row.document = doc
    row.effective_from = eff
    row.validation = validation
    row.status = m.ACTIVE
    row.approved_by = user
    row.approved_at = now
    if act is not None:
        act.status = m.SUPERSEDED
    audit.record(session, user, role, "policy_approved", "policy_version", row.id,
                 {"previous_active_id": act.id if act else None,
                  "previous_active_label": act.version_label if act else None},
                 {"version_label": row.version_label, "effective_from": eff.isoformat(), "document": doc,
                  "source_filename": row.source_filename, "source_text": (row.source_text or "")[:5000]},
                 f"Activated from {long_date(eff)}")
    session.commit()
    return row


def discard(session, version_id: int, *, user: str, role: str) -> m.PolicyVersion:
    row = _get(session, version_id)
    if row.status != m.DRAFT:
        raise conflict(f"Policy version {row.version_label} is {row.status}; only drafts can be discarded")
    row.status = m.DISCARDED
    audit.record(session, user, role, "policy_discarded", "policy_version", row.id, None,
                 {"version_label": row.version_label}, None)
    session.commit()
    return row


def get(session, version_id: int) -> m.PolicyVersion:
    return _get(session, version_id)
