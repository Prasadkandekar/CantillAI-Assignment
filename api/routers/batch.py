"""POST /api/process-batch and the runs endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from api.deps import User, get_db, optional_user
from services import batch_service

router = APIRouter(prefix="/api", tags=["batch"])


def _csv_response(text: str, filename: str) -> Response:
    return Response(content=text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def parse_date(value: str | None, field: str) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(422, f"{field} must be a date in YYYY-MM-DD format") from None


@router.post("/process-batch")
async def process_batch(file: UploadFile = File(...), policy_version: str | None = Form(default=None),
                        as_of: str | None = Form(default=None), format: str = Query(default="json"),
                        db=Depends(get_db), user: User = Depends(optional_user)):
    if format not in ("json", "csv"):
        raise HTTPException(400, "format must be json or csv")
    as_of_date = parse_date(as_of, "as_of")
    data = await file.read(batch_service.MAX_BYTES + 1)
    run, rows = batch_service.process_upload(db, data, file.filename or "upload.csv", user.name, user.role,
                                             pin=(policy_version or "").strip() or None, as_of=as_of_date)
    if format == "csv":
        return _csv_response(batch_service.export_csv(db, run.id), f"decisions_run{run.id}.csv")
    return batch_service.run_summary(db, run, include_rows=True)


@router.get("/runs")
def list_runs(db=Depends(get_db)):
    return batch_service.list_runs(db)


@router.get("/runs/{run_id}")
def get_run(run_id: int, rows: bool = False, db=Depends(get_db)):
    return batch_service.run_summary(db, batch_service.get_run(db, run_id), include_rows=rows)


@router.get("/runs/{run_id}/export")
def export_run(run_id: int, db=Depends(get_db)):
    batch_service.get_run(db, run_id)
    return _csv_response(batch_service.export_csv(db, run_id), f"decisions_run{run_id}.csv")
