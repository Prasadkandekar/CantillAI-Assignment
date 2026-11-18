"""Audit log writer. Rows are added to the caller's transaction."""
from __future__ import annotations

from sqlalchemy import select

from db import models as m


def record(session, who: str, role: str, action: str, entity_type: str, entity_id, before=None, after=None,
           comment: str | None = None) -> m.AuditLog:
    row = m.AuditLog(who=who, role=role, action=action, entity_type=entity_type, entity_id=str(entity_id),
                     before=before, after=after, comment=comment)
    session.add(row)
    return row


def as_dict(row: m.AuditLog) -> dict:
    return {"id": row.id, "who": row.who, "role": row.role, "at": row.at.isoformat() + "Z", "action": row.action,
            "entity_type": row.entity_type, "entity_id": row.entity_id, "before": row.before, "after": row.after,
            "comment": row.comment}


def list_rows(session, entity_type: str | None = None, entity_id: str | None = None, limit: int = 500) -> list[dict]:
    q = select(m.AuditLog).order_by(m.AuditLog.id.desc()).limit(limit)
    if entity_type:
        q = q.where(m.AuditLog.entity_type == entity_type)
    if entity_id:
        q = q.where(m.AuditLog.entity_id == str(entity_id))
    return [as_dict(r) for r in session.scalars(q)]
