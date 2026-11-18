"""Batch upload -> engine run -> persisted batch, run, rows, requirements and decisions."""
from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy import func, select

from db import models as m
from engine import BatchFormatError, PolicyNotFound, raw_line, read_batch, rows_to_csv, run_batch
from engine.loaders import BATCH_OPTIONAL_COLUMNS, BATCH_REQUIRED_COLUMNS
from engine.models import OUTPUT_COLUMNS, OutputRow

from . import audit
from .engine_adapter import master_from_db, policy_set, version_by_label
from .errors import ServiceError, bad_request, conflict, not_found

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
LINE_COLUMNS = BATCH_REQUIRED_COLUMNS + BATCH_OPTIONAL_COLUMNS
PR_LINE_FIELDS = ("pr_no", "pr_line", "created_at", "requester", "department", "plant", "item_code",
                  "description", "quantity", "uom", "estimated_unit_price", "need_by_date", "urgency")


def jsonsafe(value):
    return json.loads(json.dumps(value, default=str))


def parse_upload(data: bytes):
    if len(data) > MAX_BYTES:
        raise ServiceError(413, f"File is larger than {MAX_BYTES // (1024 * 1024)} MB")
    try:
        lines, warnings = read_batch(data)
    except BatchFormatError as exc:
        raise bad_request(str(exc)) from None
    if len(lines) > MAX_ROWS:
        raise ServiceError(413, f"File has {len(lines)} rows; the limit is {MAX_ROWS}")
    if not lines:
        raise bad_request("The file has no PR lines")
    return lines, warnings


def check_pin(session, pin: str | None) -> str | None:
    if not pin:
        return None
    row = version_by_label(session, pin)
    if row is None:
        raise not_found(f"Policy version {pin} not found")
    if row.status not in m.APPROVED_STATUSES:
        raise conflict(f"Policy version {pin} is {row.status}; only approved versions can be pinned")
    return pin


def store_batch(session, raw_lines, filename: str, source: str, sha: str, user: str) -> m.Batch:
    batch = m.Batch(filename=filename or "", source=source, sha256=sha, line_count=len(raw_lines), uploaded_by=user)
    session.add(batch)
    session.flush()
    session.add_all(m.PRLine(batch_id=batch.id, row_index=r.row_index,
                             **{f: (r.values.get(f) or "")[:4000] for f in PR_LINE_FIELDS}) for r in raw_lines)
    return batch


def raw_lines_for_batches(session, batch_ids) -> list:
    """Replay stored PR lines as engine RawLines, in batch then row order, renumbered from 0."""
    rows = session.scalars(select(m.PRLine).where(m.PRLine.batch_id.in_(list(batch_ids)))
                           .order_by(m.PRLine.batch_id, m.PRLine.row_index))
    return [raw_line({f: getattr(r, f) for f in PR_LINE_FIELDS}, i) for i, r in enumerate(rows)]


def latest_csv_batch(session) -> m.Batch | None:
    return session.scalar(select(m.Batch).where(m.Batch.source == "CSV").order_by(m.Batch.id.desc()).limit(1))


def _line_snapshot(line) -> dict:
    return {"key": line.key, "pr_no": line.pr_no, "pr_line": line.pr_line,
            "created_at": line.created_at.isoformat(sep=" ", timespec="minutes"),
            "requester": line.requester, "department": line.department, "plant": line.plant,
            "item_code_raw": line.item_code_raw, "resolved_item_code": line.resolved_item_code,
            "description": line.description, "quantity": str(line.quantity), "uom": line.uom,
            "estimated_unit_price": None if line.estimated_unit_price is None else str(line.estimated_unit_price),
            "need_by": line.need_by.isoformat(), "urgency": line.urgency}


def execute(session, raw_lines, pin=None, as_of=None, extra_policies=None):
    master = master_from_db(session)
    pset = policy_set(session, extra_policies)
    try:
        return run_batch(raw_lines, master, pset, pin=pin, as_of=as_of)
    except PolicyNotFound as exc:
        raise not_found(str(exc)) from None


def store_run(session, batch: m.Batch, result, user: str, pin, as_of, kind: str, warnings=()) -> m.Run:
    run = m.Run(batch_id=batch.id, pin_version=pin, as_of=as_of, created_by=user, kind=kind,
                versions_used=result.versions_used, counts=result.counts, warnings=list(warnings))
    session.add(run)
    session.flush()
    if kind == "DRY_RUN":
        return run
    session.add_all(m.RunRow(run_id=run.id, row_index=i, **r.as_dict()) for i, r in enumerate(result.rows))
    label_to_id = dict(session.execute(select(m.PolicyVersion.version_label, m.PolicyVersion.id)).all())
    for req in result.requirements:
        d = result.decisions[req.group_id]
        facts = d.trace.get("facts", {})
        row = m.Requirement(
            run_id=run.id, group_id=req.group_id, item_code=req.item_code, plant=req.plant,
            requirement_date=req.requirement_date, first_created_at=req.first_created_at, total_qty=req.total_qty,
            value=d.value, is_emergency=bool(facts.get("is_emergency")),
            policy_version_id=label_to_id.get(req.policy_version),
            line_ids=[l.key for l in req.lines], lines=[_line_snapshot(l) for l in req.lines])
        session.add(row)
        session.flush()
        session.add(m.Decision(
            requirement_id=row.id, kind="ENGINE", decision=d.decision, route=d.route, supplier_id=d.supplier_id,
            unit_price=d.unit_price, suggested=list(d.suggested), po_id=d.po_id, contract_id=d.contract_id,
            debit=d.debit, reason=d.reason, trace=jsonsafe(d.trace), status="PROPOSED", created_by="engine"))
    return run


def process_upload(session, data: bytes, filename: str, user: str, role: str, pin: str | None = None,
                   as_of: date | None = None):
    raw, warnings = parse_upload(data)
    pin = check_pin(session, pin)
    result = execute(session, raw, pin=pin, as_of=as_of)
    batch = store_batch(session, raw, filename, "CSV", hashlib.sha256(data).hexdigest(), user)
    run = store_run(session, batch, result, user, pin, as_of, "BATCH", warnings)
    audit.record(session, user, role, "process_batch", "run", run.id, None,
                 {"batch_id": batch.id, "filename": filename, "lines": len(raw), "pin": pin,
                  "as_of": as_of.isoformat() if as_of else None, "counts": result.counts})
    session.commit()
    return run, result.rows


def run_summary(session, run: m.Run, include_rows: bool = False) -> dict:
    out = {"run_id": run.id, "batch_id": run.batch_id, "kind": run.kind, "pin_version": run.pin_version,
           "as_of": run.as_of.isoformat() if run.as_of else None, "created_by": run.created_by,
           "created_at": run.created_at.isoformat() + "Z", "versions_used": run.versions_used or {},
           "counts_by_route": run.counts or {}, "warnings": run.warnings or [],
           "line_count": sum((run.counts or {}).values())}
    batch = session.get(m.Batch, run.batch_id)
    out["filename"] = batch.filename if batch else ""
    if include_rows:
        out["rows"] = [r.as_dict() for r in run_rows(session, run.id)]
    return out


def run_rows(session, run_id: int) -> list[OutputRow]:
    rows = session.scalars(select(m.RunRow).where(m.RunRow.run_id == run_id).order_by(m.RunRow.row_index))
    return [OutputRow(**{c: getattr(r, c) or "" for c in OUTPUT_COLUMNS}) for r in rows]


def export_csv(session, run_id: int) -> str:
    return rows_to_csv(run_rows(session, run_id))


def get_run(session, run_id: int) -> m.Run:
    run = session.get(m.Run, run_id)
    if run is None or run.kind == "DRY_RUN":
        raise not_found(f"Run {run_id} not found")
    return run


def list_runs(session, limit: int = 50) -> list[dict]:
    runs = session.scalars(select(m.Run).where(m.Run.kind != "DRY_RUN").order_by(m.Run.id.desc()).limit(limit))
    return [run_summary(session, r) for r in runs]


def latest_run(session, kind: str = "BATCH") -> m.Run | None:
    return session.scalar(select(m.Run).where(m.Run.kind == kind).order_by(m.Run.id.desc()).limit(1))


def chat_line_count(session) -> int:
    return session.scalar(select(func.count()).select_from(m.PRLine).join(m.Batch, m.Batch.id == m.PRLine.batch_id)
                          .where(m.Batch.source == "CHAT")) or 0
