"""Saved chat conversations: every query is scoped to the owner; other users' ids look like 404."""
from __future__ import annotations

from sqlalchemy import select

from db import models as m
from services.errors import not_found

TITLE_MAX = 50
DEFAULT_TITLE = "New chat"


def title_from(text: str | None) -> str:
    t = " ".join((text or "").split())
    if not t:
        return DEFAULT_TITLE
    return t if len(t) <= TITLE_MAX else t[:TITLE_MAX].rstrip() + "\u2026"


def _iso(dt) -> str:
    return dt.isoformat() + "Z"


def summary(conv: m.Conversation) -> dict:
    return {"id": conv.id, "title": conv.title, "created_at": _iso(conv.created_at), "updated_at": _iso(conv.updated_at)}


def owned_conversation(db, owner: str, conversation_id: int) -> m.Conversation:
    conv = db.scalars(select(m.Conversation).where(m.Conversation.id == conversation_id,
                                                   m.Conversation.owner == owner)).first()
    if conv is None:
        raise not_found("Conversation not found")
    return conv


def list_conversations(db, owner: str) -> list[dict]:
    rows = db.scalars(select(m.Conversation).where(m.Conversation.owner == owner)
                      .order_by(m.Conversation.updated_at.desc(), m.Conversation.id.desc())).all()
    return [summary(c) for c in rows]


def create_conversation(db, owner: str, title: str | None = None) -> m.Conversation:
    now = m.utcnow()
    conv = m.Conversation(owner=owner, title=title_from(title), created_at=now, updated_at=now)
    db.add(conv)
    db.flush()
    return conv


def get_conversation(db, owner: str, conversation_id: int) -> dict:
    conv = owned_conversation(db, owner, conversation_id)
    rows = db.scalars(select(m.ConversationMessage).where(m.ConversationMessage.conversation_id == conv.id)
                      .order_by(m.ConversationMessage.id)).all()
    stage = None
    if conv.session_id is not None:
        sess = db.get(m.ChatSession, conv.session_id)
        stage = (sess.state or {}).get("stage") if sess else None
    return {**summary(conv), "session_id": conv.session_id, "stage": stage,
            "messages": [{"id": r.id, "role": r.role, "content": r.content, "payload": r.payload,
                          "created_at": _iso(r.created_at)} for r in rows]}


def rename_conversation(db, owner: str, conversation_id: int, title: str) -> dict:
    conv = owned_conversation(db, owner, conversation_id)
    conv.title = title
    db.commit()
    return summary(conv)


def delete_conversation(db, owner: str, conversation_id: int) -> None:
    conv = owned_conversation(db, owner, conversation_id)
    for r in db.scalars(select(m.ConversationMessage).where(m.ConversationMessage.conversation_id == conv.id)).all():
        db.delete(r)
    db.flush()
    db.delete(conv)
    db.commit()


def conversation_for_session(db, owner: str, session_id: int) -> m.Conversation | None:
    return db.scalars(select(m.Conversation).where(m.Conversation.owner == owner, m.Conversation.session_id == session_id)
                      .order_by(m.Conversation.id.desc())).first()


def record_user_message(db, conv: m.Conversation, text: str) -> None:
    now = m.utcnow()
    db.add(m.ConversationMessage(conversation_id=conv.id, role="user", content=text, created_at=now))
    conv.updated_at = now


def record_assistant(db, conv: m.Conversation, reply: str, payload: dict | None) -> None:
    now = m.utcnow()
    db.add(m.ConversationMessage(conversation_id=conv.id, role="assistant", content=reply or "", payload=payload,
                                 created_at=now))
    conv.updated_at = now
