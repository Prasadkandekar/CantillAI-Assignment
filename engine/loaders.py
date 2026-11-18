"""CSV and JSON loaders shared by the seed script, the API and the tests."""
from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path

from .models import Contract, ContractLine, Item, MasterData, PORecord, RawLine, Supplier
from .money import to_decimal

BATCH_REQUIRED_COLUMNS = (
    "pr_no", "pr_line", "created_at", "plant", "item_code", "description",
    "quantity", "uom", "need_by_date", "urgency",
)
BATCH_OPTIONAL_COLUMNS = ("requester", "department", "estimated_unit_price")


class BatchFormatError(ValueError):
    pass


def decode_bytes(data: bytes) -> str:
    """UTF-8 (with or without BOM) first, then cp1252."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise BatchFormatError("File is not valid UTF-8 or Windows-1252 text") from exc


def _read_text(source) -> str:
    if isinstance(source, bytes):
        return decode_bytes(source)
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).exists()):
        return decode_bytes(Path(source).read_bytes())
    return str(source)


def _rows(path: Path) -> list[dict]:
    text = decode_bytes(Path(path).read_bytes())
    return [{k.strip(): (v or "").strip() for k, v in r.items() if k is not None}
            for r in csv.DictReader(io.StringIO(text))]


def read_batch(source) -> tuple[list[RawLine], list[str]]:
    """Batch CSV (path, bytes or text) -> raw lines and file-level warnings."""
    text = _read_text(source)
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in BATCH_REQUIRED_COLUMNS if c not in header]
    if missing:
        raise BatchFormatError("Missing required columns: " + ", ".join(missing))
    known = set(BATCH_REQUIRED_COLUMNS) | set(BATCH_OPTIONAL_COLUMNS)
    extra = [h for h in header if h and h not in known]
    warnings = [f"Ignored extra columns: {', '.join(extra)}"] if extra else []
    lines = []
    for i, row in enumerate(reader):
        values = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
        if not any(values.values()):
            continue
        for col in BATCH_OPTIONAL_COLUMNS:
            values.setdefault(col, "")
        lines.append(RawLine(row_index=len(lines), values=values))
    return lines, warnings


def load_batch(source) -> list[RawLine]:
    return read_batch(source)[0]


def raw_line(values: dict, row_index: int) -> RawLine:
    """Build a RawLine from a dict of column -> text (chat intake, tests)."""
    vals = {k: ("" if v is None else str(v).strip()) for k, v in values.items()}
    for col in BATCH_REQUIRED_COLUMNS + BATCH_OPTIONAL_COLUMNS:
        vals.setdefault(col, "")
    return RawLine(row_index=row_index, values=vals)


def build_master(plants, items, suppliers, po_records, contracts) -> MasterData:
    po_by_item: dict[str, list] = {}
    for po in po_records:
        po_by_item.setdefault(po.item_code, []).append(po)
    contracts_by_item: dict[str, list] = {}
    for c in contracts.values():
        for code in c.lines:
            contracts_by_item.setdefault(code, []).append(c)
    return MasterData(
        plants=dict(plants),
        items=dict(items),
        suppliers=dict(suppliers),
        po_by_item={k: tuple(sorted(v, key=lambda p: (p.po_date, p.po_number))) for k, v in po_by_item.items()},
        contracts=dict(contracts),
        contracts_by_item={k: tuple(sorted(v, key=lambda c: c.contract_id)) for k, v in contracts_by_item.items()},
    )


def contract_from_dict(d: dict, source: str = "PDF") -> Contract:
    cid = d["contract_id"]
    lines = {
        ln["item_code"]: ContractLine(cid, ln["item_code"], ln.get("description", ""), ln.get("uom", ""),
                                      to_decimal(ln["rate"]))
        for ln in d.get("lines", [])
    }
    return Contract(
        contract_id=cid, supplier_id=d["supplier_id"], supplier_name=d.get("supplier_name", ""),
        start_date=date.fromisoformat(str(d["start_date"])), end_date=date.fromisoformat(str(d["end_date"])),
        value_cap=to_decimal(d["value_cap"]), consumed_value=to_decimal(d.get("consumed_value", "0") or "0"),
        source=d.get("source", source), lines=lines,
    )


def load_master(root, pdf_contracts=None) -> MasterData:
    """Kit layout: root/master_data/*.csv and root/contracts/*.csv, plus an optional PDF-contracts JSON."""
    root = Path(root)
    md, cd = root / "master_data", root / "contracts"
    plants = {r["plant"]: r["name"] for r in _rows(md / "plants.csv")}
    items = {
        r["item_code"]: Item(r["item_code"], r["description"], r["uom"], r["category"], r["item_type"],
                             to_decimal(r["standard_price"]))
        for r in _rows(md / "item_master.csv")
    }
    suppliers = {
        r["supplier_id"]: Supplier(
            r["supplier_id"], r["name"], r["city"],
            tuple(c.strip() for c in r["categories"].split(";") if c.strip()),
            r["status"], to_decimal(r["on_time_pct"]), to_decimal(r["quality_rating"]))
        for r in _rows(md / "supplier_master.csv")
    }
    pos = [
        PORecord(r["po_number"], date.fromisoformat(r["po_date"]), r["supplier_id"], r["item_code"],
                 to_decimal(r["quantity"]), r["uom"], to_decimal(r["unit_price"]), r["plant"],
                 r["delivered_on_time"].strip().lower() == "true")
        for r in _rows(md / "po_history.csv")
    ]
    lines_by_contract: dict[str, dict] = {}
    for r in _rows(cd / "contract_lines.csv"):
        lines_by_contract.setdefault(r["contract_id"], {})[r["item_code"]] = ContractLine(
            r["contract_id"], r["item_code"], r["description"], r["uom"], to_decimal(r["rate"]))
    contracts = {}
    for r in _rows(cd / "contract_register.csv"):
        cid = r["contract_id"]
        contracts[cid] = Contract(
            cid, r["supplier_id"], r["supplier_name"], date.fromisoformat(r["start_date"]),
            date.fromisoformat(r["end_date"]), to_decimal(r["value_cap"]), to_decimal(r["consumed_value"]),
            "REGISTER", lines_by_contract.get(cid, {}))
    if pdf_contracts is not None:
        for d in json.loads(Path(pdf_contracts).read_text(encoding="utf-8")):
            c = contract_from_dict(d, "PDF")
            contracts[c.contract_id] = c
    return build_master(plants, items, suppliers, pos, contracts)
