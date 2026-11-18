"""Amendment flow over the API: upload -> draft -> diff -> dry run -> approve -> old version SUPERSEDED."""
import copy

from sqlalchemy import select

from db import base
from db import models as m
from tests.api_client import BUYER, HEADERS, upload_sample
from tests.helpers import load_doc

SPOT_TEXT = "Corvo amendment 1.\nThe spot PO limit is raised from ₹2 lakh to ₹3 lakh.\n"


def _upload(client, text, name="amendment.txt", **data):
    return client.post("/api/policy/drafts/upload", files={"file": (name, text.encode("utf-8"), "text/plain")},
                       data=data, headers=HEADERS)


def test_full_amendment_flow(client):
    first_run = upload_sample(client).json()
    r = _upload(client, SPOT_TEXT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "DRAFT" and d["version_label"] == "5.1"
    assert d["reader"]["mode"] == "fallback"
    assert d["needs_effective_date"] is True and d["question"] == "From what date should this apply?"
    assert d["validation"]["errors"] == []
    assert "Spot PO limit (5.4) changes from ₹2,00,000 to ₹3,00,000" in d["diff"]["bullets"]

    # dry run without an effective date gives only the pinned figure
    dr = client.post(f"/api/policy/{d['id']}/dry-run", headers=HEADERS).json()
    assert (dr["total_lines"], dr["pinned_changed_lines"], dr["changed_lines"]) == (186, 14, None)

    # approve without a date -> 422, with a date before v5.0 -> 409
    assert client.post(f"/api/policy/{d['id']}/approve", json={}, headers=HEADERS).status_code == 422
    assert client.post(f"/api/policy/{d['id']}/approve", json={"effective_from": "2026-01-01"},
                       headers=HEADERS).status_code == 409
    # buyers cannot approve policies
    assert client.post(f"/api/policy/{d['id']}/approve", json={"effective_from": "2026-11-01"},
                       headers=BUYER).status_code == 403

    # set the effective date on the draft, then dry run "N of M"
    eff = load_doc()["effective_from"]
    upd = client.put(f"/api/policy/{d['id']}", json={"effective_from": eff}, headers=HEADERS).json()
    assert upd["needs_effective_date"] is False
    dr = client.post(f"/api/policy/{d['id']}/dry-run", headers=HEADERS).json()
    assert (dr["changed_lines"], dr["total_lines"]) == (14, 186)
    assert dr["headline"].startswith("14 of 186 lines change")
    assert dr["route_deltas"] == {"RFQ": -14, "SPOT_PO": 14}
    assert all(c["before"]["route"] == "RFQ" and c["after"]["route"] == "SPOT_PO" for c in dr["changes"])

    ap = client.post(f"/api/policy/{d['id']}/approve", json={}, headers=HEADERS)
    assert ap.status_code == 200, ap.text
    versions = {v["version_label"]: v["status"] for v in client.get("/api/policy").json()}
    assert versions == {"5.0": "SUPERSEDED", "5.1": "ACTIVE"}
    assert client.get("/api/health").json()["active_policy"] == "5.1"

    # approved versions are immutable: API refuses, and the DB layer refuses too
    assert client.put(f"/api/policy/{d['id']}", json={"effective_from": "2026-12-01"},
                      headers=HEADERS).status_code == 409
    with base.SessionLocal() as s:
        old = s.scalar(select(m.PolicyVersion).where(m.PolicyVersion.version_label == "5.0"))
        doc = copy.deepcopy(old.document)
        doc["parameters"]["spot_max_value"] = 1
        old.document = doc
        try:
            s.flush()
            raised = False
        except m.ImmutablePolicyError:
            raised = True
        assert raised

    # a new batch now uses 5.1 for every line (effective date equals v5.0's, approved later)
    run = upload_sample(client).json()
    assert run["versions_used"] == {"5.1": 186}
    assert run["counts_by_route"]["SPOT_PO"] - 14 == first_run["counts_by_route"]["SPOT_PO"]

    audit = client.get("/api/audit", params={"entity_type": "policy_version", "entity_id": str(d["id"])}).json()
    assert [a["action"] for a in audit][:2] == ["policy_approved", "policy_draft_edited"]


def test_chat_draft_with_effective_date_and_json_edit(client):
    r = client.post("/api/policy/drafts/from-chat",
                    json={"message": "Raise the emergency limit to ₹7.5 lakh effective from 1 December 2026."},
                    headers=HEADERS)
    d = r.json()
    assert d["effective_from"] == "2026-12-01" and d["needs_effective_date"] is False
    assert "Emergency PO limit (5.3) changes from ₹5,00,000 to ₹7,50,000" in d["reply"]
    # direct JSON editing of the draft: introduce an unknown fact -> validation error, cannot approve
    doc = copy.deepcopy(d["document"])
    doc["rules"][0]["when"]["all"][0]["fact"] = "no_such_fact"
    e = client.put(f"/api/policy/{d['id']}", json={"document": doc}, headers=HEADERS).json()
    assert any("no_such_fact" in err["message"] for err in e["validation"]["errors"])
    bad = client.post(f"/api/policy/{d['id']}/approve", json={}, headers=HEADERS)
    assert bad.status_code == 422
    # discard
    assert client.post(f"/api/policy/{d['id']}/discard", headers=HEADERS).json()["status"] == "DISCARDED"


def test_upload_errors(client):
    assert _upload(client, "x", name="a.exe").status_code == 415
    assert _upload(client, "   ", name="a.txt").status_code == 422
    assert client.post("/api/policy/drafts/from-chat", json={"message": "x"}).status_code == 400   # no X-User
    upload = client.post("/api/policy/drafts/from-chat", json={"message": "Raise the spot limit to ₹3 lakh."},
                         headers=HEADERS).json()
    # no batch uploaded yet in this database -> dry run 409
    assert client.post(f"/api/policy/{upload['id']}/dry-run", headers=HEADERS).status_code == 409
