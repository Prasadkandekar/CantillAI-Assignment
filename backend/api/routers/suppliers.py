"""Preferred supplier lists and their CSV export."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from api.deps import get_db
from api.routers.batch import parse_date
from services import preferred_service

router = APIRouter(prefix="/api/preferred-suppliers", tags=["suppliers"])


def _as_of(value: str | None):
    d = parse_date(value, "as_of")
    if d is None:
        raise HTTPException(422, "as_of is required (YYYY-MM-DD)")
    return d


@router.get("")
def preferred(as_of: str | None = None, item_code: str | None = None, policy_version: str | None = None,
              db=Depends(get_db)):
    return preferred_service.lists(db, _as_of(as_of), item_code or None, policy_version or None)


@router.get("/export")
def export(as_of: str | None = None, policy_version: str | None = None, db=Depends(get_db)):
    d = _as_of(as_of)
    text = preferred_service.export_csv(db, d, policy_version or None)
    return Response(content=text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="preferred_suppliers_{d.isoformat()}.csv"'})
