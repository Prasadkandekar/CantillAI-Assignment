"""Chat intake turns and confirmation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import User, current_user, get_db
from services import chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatIn(BaseModel):
    session_id: int | None = None
    message: str | None = Field(default=None, max_length=2000)
    action: str | None = None          # select / edit
    choice: str | None = None
    fields: dict | None = None


@router.post("")
def chat_turn(body: ChatIn, db=Depends(get_db), user: User = Depends(current_user)):
    if body.action not in (None, "select", "edit"):
        raise HTTPException(422, "action must be select or edit")
    if body.action is None and not (body.message or "").strip():
        raise HTTPException(422, "message must be 1-2000 characters")
    if body.action and body.session_id is None:
        raise HTTPException(422, "session_id is required with an action")
    return chat_service.turn(db, user=user.name, role=user.role, department=user.department,
                             session_id=body.session_id, message=body.message, action=body.action,
                             choice=body.choice, fields=body.fields)


@router.get("/{session_id}")
def get_session(session_id: int, db=Depends(get_db)):
    return chat_service.get_session(db, session_id)


@router.post("/{session_id}/confirm")
def confirm(session_id: int, db=Depends(get_db), user: User = Depends(current_user)):
    return chat_service.confirm(db, session_id, user=user.name, role=user.role, department=user.department)
