"""Buyer workspace: requirements, approve, override, audit."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import User, get_db, require_role
from services import audit, workspace_service

router = APIRouter(prefix="/api", tags=["workspace"])
BUYER_ROLES = ("buyer", "procurement")


class OverrideIn(BaseModel):
    comment: str | None = None
    decision: str | None = None
    route: str | None = None
    supplier_id: str | None = None
    unit_price: str | float | None = None
    suggested_supplier_ids: list[str] | None = None


@router.get("/requirements")
def list_requirements(run_id: int | None = None, route: str | None = None, status: str | None = None,
                      db=Depends(get_db)):
    return workspace_service.list_requirements(db, run_id, route or None, status or None)


@router.get("/requirements/{req_id}")
def get_requirement(req_id: int, db=Depends(get_db)):
    return workspace_service.detail(db, req_id)


@router.post("/requirements/{req_id}/approve")
def approve(req_id: int, db=Depends(get_db), user: User = Depends(require_role(*BUYER_ROLES))):
    return workspace_service.approve(db, req_id, user=user.name, role=user.role)


@router.post("/requirements/{req_id}/override")
def override(req_id: int, body: OverrideIn, db=Depends(get_db), user: User = Depends(require_role(*BUYER_ROLES))):
    return workspace_service.override(db, req_id, body.model_dump(), user=user.name, role=user.role)


@router.get("/audit")
def audit_rows(entity_type: str | None = None, entity_id: str | None = None, db=Depends(get_db)):
    return audit.list_rows(db, entity_type, entity_id)
