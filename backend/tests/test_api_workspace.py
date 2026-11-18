"""Buyer workspace: PO-group approval, override lifecycle, orders, contract consumption, audit."""
from sqlalchemy import func, select

from db import base
from db import models as m
from tests.api_client import BUYER, HEADERS, upload_sample

REQUESTER = {"X-User": "req1", "X-Role": "requester"}


def _reqs(client, run_id=None):
    params = {"run_id": run_id} if run_id else {}
    return client.get("/api/requirements", params=params).json()["requirements"]


def _req_with(client, line_key, run_id=None):
    return next(r for r in _reqs(client, run_id) if line_key in r["pr_lines"])


def _suppliers(client, status):
    return [s["supplier_id"] for s in client.get("/api/suppliers").json() if s["status"] == status]


def _consumption_count():
    with base.SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(m.ContractConsumption))


def test_list_detail_and_why_panel(client):
    upload_sample(client)
    data = client.get("/api/requirements").json()
    assert data["run"]["line_count"] == 186
    assert sum(len(r["pr_lines"]) for r in data["requirements"]) == 184     # 2 lines NOT_PROCESSED
    r = _req_with(client, "PR-26-00019/1")      # worked example 1: contract PO
    d = client.get(f"/api/requirements/{r['id']}").json()
    assert d["effective"]["route"] == "CONTRACT_PO"
    assert d["why"]["fired"]["clause"] == "5.2" and d["why"]["fired"]["text"]
    assert d["why"]["facts"]["contract_usable"] is True
    assert d["contract"]["contract_id"] == d["effective"]["contract_id"]
    assert d["ranking"], "ranking table is always available"
    rfq = client.get("/api/requirements", params={"route": "RFQ"}).json()["requirements"]
    assert rfq and all(x["effective"]["route"] == "RFQ" for x in rfq)


def test_approve_po_group_and_terminal_states(client):
    upload_sample(client)
    r = _req_with(client, "PR-26-00034/1")      # examples 4 and 14 share one contract PO
    other = _req_with(client, "PR-26-00031/1")
    assert r["effective"]["po_id"] == other["effective"]["po_id"]
    assert client.post(f"/api/requirements/{r['id']}/approve", headers=REQUESTER).status_code == 403
    out = client.post(f"/api/requirements/{r['id']}/approve", headers=BUYER).json()
    assert out["order_no"] == r["effective"]["po_id"] and len(out["requirements"]) == 2
    assert out["display"].startswith("R")
    assert _req_with(client, "PR-26-00031/1")["effective"]["status"] == "APPROVED"
    assert _consumption_count() == 2
    assert client.post(f"/api/requirements/{other['id']}/approve", headers=BUYER).status_code == 409
    body = {"comment": "too late", "decision": "SOURCING_REQUEST", "route": "RFQ"}
    assert client.post(f"/api/requirements/{r['id']}/override", json=body, headers=BUYER).status_code == 409
    audit = client.get("/api/audit", params={"entity_type": "requirement", "entity_id": str(r["id"])}).json()
    assert audit[0]["action"] == "approve" and audit[0]["who"] == "buyer1"
    assert audit[0]["before"]["status"] == "PROPOSED" and audit[0]["after"]["status"] == "APPROVED"


def test_override_validation(client):
    upload_sample(client)
    r = _req_with(client, "PR-26-00089/1")      # worked example 9: RFQ
    url = f"/api/requirements/{r['id']}/override"
    active, blocked = _suppliers(client, "Active"), _suppliers(client, "Blocked")
    assert client.post(url, json={"decision": "PO", "route": "SPOT_PO", "supplier_id": active[0]},
                       headers=BUYER).status_code == 422                    # no comment
    assert client.post(url, json={"comment": "  ", "decision": "PO", "route": "SPOT_PO",
                                  "supplier_id": active[0]}, headers=BUYER).status_code == 422
    assert client.post(url, json={"comment": "use blocked", "decision": "PO", "route": "SPOT_PO",
                                  "supplier_id": blocked[0]}, headers=BUYER).status_code == 422
    assert client.post(url, json={"comment": "no supplier", "decision": "PO", "route": "SPOT_PO"},
                       headers=BUYER).status_code == 422
    assert client.post(url, json={"comment": "bad suggestion", "decision": "SOURCING_REQUEST", "route": "RFQ",
                                  "suggested_supplier_ids": [blocked[0]]}, headers=BUYER).status_code == 422
    assert client.post(url, json={"comment": "unknown", "decision": "PO", "route": "SPOT_PO",
                                  "supplier_id": "NOPE"}, headers=BUYER).status_code == 422


def test_override_lifecycle_and_po_override_order(client):
    upload_sample(client)
    r = _req_with(client, "PR-26-00034/1")      # contract PO in a 2-requirement PO group
    other = _req_with(client, "PR-26-00031/1")
    before = client.get(f"/api/requirements/{r['id']}").json()["original"]
    active = _suppliers(client, "Active")
    body = {"comment": "Supplier asked for a separate order", "decision": "PO", "route": "SPOT_PO",
            "supplier_id": active[0], "unit_price": "7.10"}
    new = client.post(f"/api/requirements/{r['id']}/override", json=body, headers=BUYER).json()
    assert new["status"] == "PROPOSED" and new["kind"] == "OVERRIDE" and new["po_id"] is None
    assert new["contract_id"] is None
    d = client.get(f"/api/requirements/{r['id']}").json()
    orig = d["original"]
    assert orig["status"] == "OVERRIDDEN"
    assert {k: v for k, v in orig.items() if k != "status"} == {k: v for k, v in before.items() if k != "status"}
    assert d["effective"]["id"] == new["id"]
    # approving the other member of the PO group excludes the overridden requirement
    out = client.post(f"/api/requirements/{other['id']}/approve", headers=BUYER).json()
    assert out["requirements"] == [other["id"]] and out["excluded_overridden"] == 1
    assert _consumption_count() == 1
    # the override can be approved on its own; an overridden contract PO writes no consumption
    ovr = client.post(f"/api/requirements/{r['id']}/approve", headers=BUYER).json()
    assert ovr["order_no"] == f"PO-OVR-{new['id']}"
    assert _consumption_count() == 1
    actions = [a["action"] for a in client.get("/api/audit", params={"entity_type": "requirement",
                                                                     "entity_id": str(r["id"])}).json()]
    assert actions == ["approve", "override"]


def test_sourcing_orders_and_orders_unique_per_run(client):
    run1 = upload_sample(client).json()["run_id"]
    run2 = upload_sample(client).json()["run_id"]
    rfq = [x for x in _reqs(client, run1) if x["effective"]["decision"] == "SOURCING_REQUEST"][:2]
    o1 = client.post(f"/api/requirements/{rfq[0]['id']}/approve", headers=BUYER).json()
    o2 = client.post(f"/api/requirements/{rfq[1]['id']}/approve", headers=BUYER).json()
    assert (o1["order_no"], o2["order_no"]) == ("SRC-0001", "SRC-0002")
    a = _req_with(client, "PR-26-00034/1", run1)
    b = _req_with(client, "PR-26-00034/1", run2)
    oa = client.post(f"/api/requirements/{a['id']}/approve", headers=BUYER).json()
    ob = client.post(f"/api/requirements/{b['id']}/approve", headers=BUYER).json()
    assert oa["order_no"] == ob["order_no"] and oa["display"] != ob["display"]
    with base.SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(m.Order).where(m.Order.order_no == oa["order_no"])) == 2


def test_audit_endpoint_lists_batch_runs(client):
    upload_sample(client)
    rows = client.get("/api/audit", params={"entity_type": "run"}).json()
    assert rows and rows[0]["action"] == "process_batch" and rows[0]["who"] == HEADERS["X-User"]
