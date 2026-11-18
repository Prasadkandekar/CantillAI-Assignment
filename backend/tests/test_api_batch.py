"""POST /api/process-batch and the runs endpoints (TestClient, SQLite, no network)."""
import csv
import io

from engine.models import OUTPUT_COLUMNS
from tests.api_client import HEADERS, SAMPLE, upload_sample
from tests.helpers import load_doc, run

EXPECTED_HEADER = ("pr_no,pr_line,resolved_item_code,group_id,po_id,decision,route,supplier_id,unit_price,"
                   "group_value_inr,suggested_supplier_ids,policy_version,reason")


def _post(client, content: bytes, name="b.csv", **kw):
    return client.post("/api/process-batch", files={"file": (name, content, "text/csv")}, headers=HEADERS, **kw)


def test_json_default_has_186_rows_matching_engine(client):
    r = upload_sample(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["line_count"] == 186 and len(body["rows"]) == 186
    assert tuple(body["rows"][0].keys()) == OUTPUT_COLUMNS
    engine_rows = [row.as_dict() for row in run(load_doc()).rows]
    assert body["rows"] == engine_rows
    assert sum(body["counts_by_route"].values()) == 186
    assert body["versions_used"] == {load_doc()["version"]: 186}


def test_csv_format_exact_header_and_rows(client):
    r = upload_sample(client, params={"format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.splitlines()
    assert lines[0] == EXPECTED_HEADER
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 186
    assert sum(1 for x in rows if x["route"] == "NOT_PROCESSED" and x["reason"]) == 2
    assert all("," not in x["suggested_supplier_ids"] for x in rows)
    assert any(";" in x["suggested_supplier_ids"] for x in rows)


def test_runs_list_detail_and_export(client):
    run_id = upload_sample(client).json()["run_id"]
    runs = client.get("/api/runs").json()
    assert runs[0]["run_id"] == run_id
    assert client.get(f"/api/runs/{run_id}").json()["line_count"] == 186
    exp = client.get(f"/api/runs/{run_id}/export")
    assert exp.text.splitlines()[0] == EXPECTED_HEADER and len(exp.text.splitlines()) == 187
    assert client.get("/api/runs/9999").status_code == 404


def test_pin_and_as_of(client):
    label = load_doc()["version"]
    r = upload_sample(client, data={"policy_version": label, "as_of": "2026-11-18"})
    assert r.status_code == 200
    assert r.json()["pin_version"] == label
    assert upload_sample(client, data={"policy_version": "99.9"}).status_code == 404
    assert upload_sample(client, data={"as_of": "18/11/2026"}).status_code == 422


def test_pin_of_draft_is_409(client):
    d = client.post("/api/policy/drafts/from-chat", json={"message": "Raise the spot limit to ₹3 lakh."},
                    headers=HEADERS).json()
    assert d["status"] == "DRAFT"
    assert upload_sample(client, data={"policy_version": d["version_label"]}).status_code == 409


def test_error_codes(client):
    assert _post(client, b"pr_no,pr_line\nX,1\n").status_code == 400
    assert "Missing required columns" in _post(client, b"pr_no,pr_line\nX,1\n").json()["detail"]
    header = SAMPLE.read_bytes().splitlines()[0] + b"\n"
    assert _post(client, header).status_code == 400
    big = header + b"x" * (5 * 1024 * 1024 + 10)
    assert _post(client, big).status_code == 413
    assert _post(client, SAMPLE.read_bytes(), params={"format": "xml"}).status_code == 400


def test_batch_without_headers_is_recorded_as_api(client):
    with open(SAMPLE, "rb") as fh:
        r = client.post("/api/process-batch", files={"file": ("s.csv", fh, "text/csv")})
    assert r.status_code == 200
    assert r.json()["created_by"] == "api"
