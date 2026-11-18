"""Contract PDF extraction (regex first) against the seed JSON and the register, plus the contracts API."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from services.contract_extraction import regex_extract
from services.document_text import pdf_text
from tests.helpers import PDF_CONTRACTS, ROOT, master_data

PDF_DIR = ROOT / "contracts" / "pdf"
HEADERS = {"X-User": "buyer1", "X-Role": "buyer"}


def _extract(path: Path):
    return regex_extract(pdf_text(path.read_bytes()))


@pytest.mark.parametrize("seed", json.loads(PDF_CONTRACTS.read_text("utf-8")), ids=lambda d: d["contract_id"])
def test_pdf_only_contracts_equal_seed_json(seed):
    fields, lines = _extract(PDF_DIR / seed["pdf_filename"])
    for k in ("contract_id", "supplier_id", "supplier_name", "start_date", "end_date"):
        assert fields[k] == seed[k], k
    assert Decimal(fields["value_cap"]) == Decimal(seed["value_cap"])
    assert [(l["item_code"], l["description"], l["uom"], Decimal(l["rate"])) for l in lines] == \
        [(l["item_code"], l["description"], l["uom"], Decimal(l["rate"])) for l in seed["lines"]]


def test_register_pdfs_match_register():
    md = master_data()
    register = {cid: c for cid, c in md.contracts.items() if c.source == "REGISTER"}
    assert len(register) == 10
    for cid, c in register.items():
        fields, lines = _extract(PDF_DIR / f"{cid}.pdf")
        assert fields["contract_id"] == cid
        assert fields["supplier_id"] == c.supplier_id
        assert (fields["start_date"], fields["end_date"]) == (c.start_date.isoformat(), c.end_date.isoformat())
        assert Decimal(fields["value_cap"]) == c.value_cap
        assert {l["item_code"]: Decimal(l["rate"]) for l in lines} == {k: v.rate for k, v in c.lines.items()}


def _post_pdf(client, name):
    with open(PDF_DIR / name, "rb") as fh:
        return client.post("/api/contracts/extract-pdf", files={"file": (name, fh, "application/pdf")})


def test_extract_api_and_save(client):
    r = _post_pdf(client, "RC-2026-031.pdf").json()
    assert r["exists"] is True and r["differences"] == [] and r["missing"] == []
    assert r["field_sources"]["contract_id"] == "regex"
    blocked = _post_pdf(client, "RC-2026-005.pdf").json()
    assert any("Blocked" in w for w in blocked["warnings"])
    assert client.post("/api/contracts/extract-pdf",
                       files={"file": ("a.txt", b"hello", "text/plain")}).status_code == 415

    body = {**r["fields"], "lines": r["lines"], "source": "PDF", "pdf_filename": "RC-2026-031.pdf"}
    assert client.post("/api/contracts", json=body, headers=HEADERS).status_code == 409
    saved = client.post("/api/contracts", json={**body, "replace": True}, headers=HEADERS)
    assert saved.status_code == 200, saved.text
    new_id = {**body, "contract_id": "RC-2099-001"}
    ok = client.post("/api/contracts", json=new_id, headers=HEADERS).json()
    assert ok["remaining"] == ok["value_cap"] and ok["consumed_value"] == "0"
    bad = {**new_id, "contract_id": "RC-2099-002", "lines": [{**r["lines"][0], "item_code": "NOPE-1"}]}
    assert client.post("/api/contracts", json=bad, headers=HEADERS).status_code == 422
    listed = {c["contract_id"]: c for c in client.get("/api/contracts").json()}
    assert "RC-2099-001" in listed and listed["RC-2026-005"]["supplier_status"] == "Blocked"
    audit = client.get("/api/audit", params={"entity_type": "contract"}).json()
    assert [a["action"] for a in audit] == ["contract_added", "contract_replaced"]
