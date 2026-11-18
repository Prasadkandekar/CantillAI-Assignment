"""Contract PDF -> fields and schedule lines. Regex first; the LLM only fills fields the regex missed.
Nothing is saved here: the buyer reviews the fields and saves them explicitly."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from db import models as m
from engine import is_eligible, load_policy

from . import llm
from .amounts import parse_inr
from .engine_adapter import active_version, dec, supplier_to_engine

FIELDS = ("contract_id", "supplier_id", "supplier_name", "start_date", "end_date", "value_cap")
_ID = re.compile(r"Contract No\.?\s*([A-Z]{2,4}-\d{4}-\d{3})")
_SUPPLIER_ID = re.compile(r"\(Supplier ID\s*(S\d{3,})\s*\)")
_SUPPLIER_NAME = re.compile(r"\band ([^,()\"]+?), [^,()]+? \(Supplier ID")
_TERM = re.compile(r"valid from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})")
_CEILING = re.compile(r"shall not exceed (?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)")
_ROW = re.compile(r"^\s*\d+\s+([A-Z]{2,5}-\d{3,6})\s+(.+?)\s+([A-Z]{2,5})\s+([\d,]+\.\d{2})\s*$", re.M)


def regex_extract(text: str) -> tuple[dict, list[dict]]:
    flat = re.sub(r"\s+", " ", text or "")
    fields: dict = {}
    if mt := _ID.search(flat):
        fields["contract_id"] = mt.group(1)
    if mt := _SUPPLIER_ID.search(flat):
        fields["supplier_id"] = mt.group(1)
    if mt := _SUPPLIER_NAME.search(flat):
        fields["supplier_name"] = mt.group(1).strip()
    if mt := _TERM.search(flat):
        fields["start_date"], fields["end_date"] = mt.group(1), mt.group(2)
    if mt := _CEILING.search(flat):
        fields["value_cap"] = mt.group(1).replace(",", "")
    lines = [{"item_code": code, "description": desc.strip(), "uom": uom, "rate": rate.replace(",", "")}
             for code, desc, uom, rate in _ROW.findall(text or "")]
    return fields, lines


def _llm_fill(text: str, missing: list[str], need_lines: bool) -> tuple[dict, list]:
    want = missing + (["lines"] if need_lines else [])
    schema = ('{"contract_id": str, "supplier_id": str, "supplier_name": str, "start_date": "YYYY-MM-DD", '
              '"end_date": "YYYY-MM-DD", "value_cap": number (INR), "lines": [{"item_code", "description", '
              '"uom", "rate"}]}')
    out = llm.complete_json(
        "Extract rate-contract fields from the document text. Use only values written in the text; use null "
        f"for anything not stated. Fields needed: {', '.join(want)}.", text[:20000], schema)
    fields = {k: out.get(k) for k in missing if out.get(k) not in (None, "")}
    lines = out.get("lines") if need_lines and isinstance(out.get("lines"), list) else []
    return fields, [ln for ln in lines if isinstance(ln, dict)]


def _norm_decimal(v) -> str | None:
    if v in (None, ""):
        return None
    try:
        return str(Decimal(str(v).replace(",", "")))
    except InvalidOperation:
        amt = parse_inr(str(v))
        return None if amt is None else str(amt)


def check(session, fields: dict, lines: list[dict]) -> list[str]:
    """Warnings and problems the buyer should see before saving."""
    warnings = []
    sid = fields.get("supplier_id")
    if sid:
        s = session.get(m.Supplier, sid)
        if s is None:
            warnings.append(f"Supplier {sid} is not in the supplier master")
        else:
            act = active_version(session)
            if act is not None and not is_eligible(supplier_to_engine(s), load_policy(act.document).params):
                warnings.append(f"Supplier {sid} is {s.status}: contract will be skipped (4.1)")
    try:
        start = date.fromisoformat(fields["start_date"]) if fields.get("start_date") else None
        end = date.fromisoformat(fields["end_date"]) if fields.get("end_date") else None
        if start and end and start > end:
            warnings.append("Start date is after end date")
    except ValueError:
        warnings.append("Dates must be YYYY-MM-DD")
    cap = _norm_decimal(fields.get("value_cap"))
    if cap is not None and Decimal(cap) <= 0:
        warnings.append("Value ceiling must be greater than zero")
    known = set(session.scalars(select(m.Item.item_code)))
    for ln in lines:
        if ln.get("item_code") not in known:
            warnings.append(f"Item {ln.get('item_code')} is not in the item master")
        rate = _norm_decimal(ln.get("rate"))
        if rate is None or Decimal(rate) <= 0:
            warnings.append(f"Rate for {ln.get('item_code')} must be greater than zero")
    return warnings


def compare_with_existing(session, fields: dict, lines: list[dict]) -> list[str]:
    cid = fields.get("contract_id")
    c = session.get(m.Contract, cid) if cid else None
    if c is None:
        return []
    diffs = []
    existing = {"supplier_id": c.supplier_id, "start_date": c.start_date.isoformat(), "end_date": c.end_date.isoformat(),
                "value_cap": str(dec(c.value_cap))}
    for k, v in existing.items():
        new = fields.get(k)
        if k == "value_cap":
            new = _norm_decimal(new)
            new = None if new is None else str(dec(Decimal(new)))
        if new is not None and str(new) != v:
            diffs.append(f"{k}: saved {v}, document {new}")
    saved_lines = {ln.item_code: str(dec(ln.rate)) for ln in
                   session.scalars(select(m.ContractLine).where(m.ContractLine.contract_id == cid))}
    for ln in lines:
        rate = _norm_decimal(ln.get("rate"))
        rate = None if rate is None else str(dec(Decimal(rate)))
        if ln.get("item_code") not in saved_lines:
            diffs.append(f"line {ln.get('item_code')}: not in the saved contract")
        elif rate != saved_lines[ln["item_code"]]:
            diffs.append(f"line {ln['item_code']}: saved rate {saved_lines[ln['item_code']]}, document {rate}")
    for code in saved_lines:
        if code not in {ln.get("item_code") for ln in lines}:
            diffs.append(f"line {code}: in the saved contract but not in the document")
    return diffs


def extract(session, text: str) -> dict:
    fields, lines = regex_extract(text)
    sources = {k: "regex" for k in fields}
    missing = [f for f in FIELDS if f not in fields]
    llm_note = None
    if missing or not lines:
        try:
            got, got_lines = _llm_fill(text, missing, not lines)
            for k, v in got.items():
                fields[k] = str(v)
                sources[k] = "llm"
            if got_lines:
                lines = [{"item_code": str(ln.get("item_code", "")), "description": str(ln.get("description", "")),
                          "uom": str(ln.get("uom", "")), "rate": _norm_decimal(ln.get("rate")) or ""}
                         for ln in got_lines]
                sources["lines"] = "llm"
        except llm.LLMUnavailable as exc:
            llm_note = f"AI fallback unavailable ({exc}); fill the missing fields by hand"
    if lines and "lines" not in sources:
        sources["lines"] = "regex"
    if fields.get("supplier_id") and not fields.get("supplier_name"):
        s = session.get(m.Supplier, fields["supplier_id"])
        if s is not None:
            fields["supplier_name"] = s.name
            sources["supplier_name"] = "supplier master"
    missing = [f for f in FIELDS if not fields.get(f)] + ([] if lines else ["lines"])
    warnings = check(session, fields, lines)
    if llm_note:
        warnings.append(llm_note)
    existing = compare_with_existing(session, fields, lines)
    return {"fields": {f: fields.get(f) for f in FIELDS}, "lines": lines, "field_sources": sources,
            "missing": missing, "warnings": warnings, "exists": bool(fields.get("contract_id") and
                                                                    session.get(m.Contract, fields["contract_id"])),
            "differences": existing}
