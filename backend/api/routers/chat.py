"""Chat intake turns and confirmation, plus saved conversations (chat history)."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from api.deps import User, chat_owner, current_user, get_db
from services import chat_history_service as history
from services import chat_service
router = APIRouter(prefix="/api/chat", tags=["chat"])
log = logging.getLogger(__name__)
class ChatIn(BaseModel):
    session_id: int | None = None
    message: str | None = Field(default=None, max_length=2000)
    action: str | None = None          # select / edit
    choice: str | None = None
    fields: dict | None = None
    conversation_id: int | None = None
class ConversationIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
class RenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
# Conversation routes are declared before "/{session_id}" so "conversations" is never parsed as an id.
@router.get("/conversations")
def list_conversations(db=Depends(get_db), owner: str = Depends(chat_owner)):
    return history.list_conversations(db, owner)
@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationIn | None = None, db=Depends(get_db), owner: str = Depends(chat_owner)):
    conv = history.create_conversation(db, owner, body.title if body else None)
    db.commit()
    return history.summary(conv)
@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db=Depends(get_db), owner: str = Depends(chat_owner)):
    return history.get_conversation(db, owner, conversation_id)
@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, body: RenameIn, db=Depends(get_db), owner: str = Depends(chat_owner)):
    title = " ".join(body.title.split())
    if not title:
        raise HTTPException(422, "title must not be blank")
    return history.rename_conversation(db, owner, conversation_id, title)
@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, db=Depends(get_db), owner: str = Depends(chat_owner)):
    history.delete_conversation(db, owner, conversation_id)
    return {"ok": True}
@router.post("")
def chat_turn(body: ChatIn, db=Depends(get_db), user: User = Depends(current_user), owner: str = Depends(chat_owner)):
    if body.action not in (None, "select", "edit"):
        raise HTTPException(422, "action must be select or edit")
    if body.action is None and not (body.message or "").strip():
        raise HTTPException(422, "message must be 1-2000 characters")
    if body.action and body.session_id is None:
        raise HTTPException(422, "session_id is required with an action")
    conv = None
    if body.conversation_id is not None:
        conv = history.owned_conversation(db, owner, body.conversation_id)
    elif body.session_id is not None:
        conv = history.conversation_for_session(db, owner, body.session_id)
    res = chat_service.turn(db, user=user.name, role=user.role, department=user.department,
                            session_id=body.session_id, message=body.message, action=body.action,
                            choice=body.choice, fields=body.fields)
    user_text = body.choice if body.action == "select" else (body.message if body.action is None else None)
    # The turn is already committed; a history failure must not turn it into a 500.
    try:
        if conv is None:
            conv = history.create_conversation(db, owner, user_text)
        if user_text:
            history.record_user_message(db, conv, user_text)
        payload = {"card": res.get("card"), "candidates": res.get("candidates") or []}
        if res.get("result"):
            payload["result"] = res["result"]
        history.record_assistant(db, conv, res.get("reply"), payload)
        conv.session_id = res["session_id"]
        db.commit()
        res["conversation_id"] = conv.id
        res["conversation"] = history.summary(conv)
    except Exception:
        db.rollback()
        log.exception("could not save chat history for session %s", res.get("session_id"))
    return res

@router.get("/{session_id}")
def get_session(session_id: int, db=Depends(get_db)):
    return chat_service.get_session(db, session_id)
@router.post("/{session_id}/confirm")
def confirm(session_id: int, db=Depends(get_db), user: User = Depends(current_user), owner: str = Depends(chat_owner)):
    res = chat_service.confirm(db, session_id, user=user.name, role=user.role, department=user.department)
    try:
        conv = history.conversation_for_session(db, owner, session_id)
        if conv is not None:
            history.record_assistant(db, conv, res.get("reply"), {"result": res})
            db.commit()
            res["conversation_id"] = conv.id
            res["conversation"] = history.summary(conv)
    except Exception:
        db.rollback()
        log.exception("could not save chat history for session %s", session_id)
    return res
