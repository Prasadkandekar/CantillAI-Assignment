"""Contracts: list, PDF extraction (nothing saved), save reviewed contract.
(File name avoids a folder/file called exactly 'contracts', which .gitignore matches.)"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from api.deps import User, current_user, get_db
from services import contract_extraction, contract_service, document_text

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


class ContractLineIn(BaseModel):
    item_code: str
    description: str | None = None
    uom: str | None = None
    rate: str | float


class ContractIn(BaseModel):
    contract_id: str
    supplier_id: str
    supplier_name: str | None = None
    start_date: str
    end_date: str
    value_cap: str | float
    consumed_value: str | float | None = None
    source: str | None = "PDF"
    pdf_filename: str | None = None
    lines: list[ContractLineIn]
    replace: bool = False


@router.get("")
def list_contracts(db=Depends(get_db)):
    return contract_service.list_contracts(db)


@router.post("/extract-pdf")
async def extract_pdf(file: UploadFile = File(...), db=Depends(get_db)):
    data = await file.read(document_text.MAX_BYTES + 1)
    text = document_text.extract(file.filename or "", data, allowed=(".pdf",))
    out = contract_extraction.extract(db, text)
    out["pdf_filename"] = file.filename
    return out


@router.post("")
def save_contract(body: ContractIn, db=Depends(get_db), user: User = Depends(current_user)):
    return contract_service.save(db, body.model_dump(), user=user.name, role=user.role)
