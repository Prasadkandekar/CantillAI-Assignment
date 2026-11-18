"""Policy versions, amendment drafts (upload / chat / JSON edit), dry run, approve, discard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from api.deps import User, current_user, get_db, require_role
from services import document_text, policy_service

router = APIRouter(prefix="/api/policy", tags=["policy"])


class ChatDraftIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    effective_from: str | None = None


class DraftUpdateIn(BaseModel):
    document: dict | None = None
    effective_from: str | None = None
    version_label: str | None = Field(default=None, max_length=20)


class ApproveIn(BaseModel):
    effective_from: str | None = None


@router.get("")
def list_versions(db=Depends(get_db)):
    return policy_service.list_versions(db)


@router.get("/{version_id}")
def get_version(version_id: int, db=Depends(get_db)):
    return policy_service.detail(db, policy_service.get(db, version_id))


@router.post("/drafts/upload")
async def upload_draft(file: UploadFile = File(...), effective_from: str | None = Form(default=None),
                       mode: str = Form(default="auto"), db=Depends(get_db), user: User = Depends(current_user)):
    data = await file.read(document_text.MAX_BYTES + 1)
    text = document_text.extract(file.filename or "", data)
    row = policy_service.create_draft(db, text, user=user.name, role=user.role, filename=file.filename,
                                      effective_from=effective_from, mode=mode)
    return policy_service.detail(db, row)


@router.post("/drafts/from-chat")
def chat_draft(body: ChatDraftIn, db=Depends(get_db), user: User = Depends(current_user)):
    row = policy_service.create_draft(db, body.message, user=user.name, role=user.role, filename=None,
                                      effective_from=body.effective_from)
    out = policy_service.detail(db, row)
    bullets = out["diff"]["bullets"]
    reply = ("I drafted v" + row.version_label + ": " + "; ".join(bullets)) if bullets else \
        "I could not turn that into a policy change. Try e.g. 'Raise the spot limit to ₹3 lakh'."
    if out["needs_effective_date"]:
        reply += " " + policy_service.EFFECTIVE_DATE_QUESTION
    out["reply"] = reply
    return out


@router.put("/{version_id}")
def update_draft(version_id: int, body: DraftUpdateIn, db=Depends(get_db), user: User = Depends(current_user)):
    row = policy_service.update_draft(db, version_id, user=user.name, role=user.role, document=body.document,
                                      effective_from=body.effective_from, version_label=body.version_label)
    return policy_service.detail(db, row)


@router.post("/{version_id}/dry-run")
def dry_run(version_id: int, db=Depends(get_db), user: User = Depends(current_user)):
    return policy_service.dry_run(db, version_id, user.name)


@router.post("/{version_id}/approve")
def approve(version_id: int, body: ApproveIn | None = None, db=Depends(get_db),
            user: User = Depends(require_role("procurement"))):
    row = policy_service.approve(db, version_id, user=user.name, role=user.role,
                                 effective_from=body.effective_from if body else None)
    return policy_service.detail(db, row)


@router.post("/{version_id}/discard")
def discard(version_id: int, db=Depends(get_db), user: User = Depends(require_role("procurement"))):
    return policy_service.detail(db, policy_service.discard(db, version_id, user=user.name, role=user.role))
