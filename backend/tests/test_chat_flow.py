"""Chat intake in fallback mode (LLM disabled): slots, questions, candidates, new items, confirmation."""
import pytest

from tests.api_client import upload_sample

USER = {"X-User": "M. Shaikh", "X-Role": "requester", "X-Department": "Maintenance"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setenv("APP_TODAY", "2026-11-18")     # a Wednesday


def say(client, text, sid=None):
    r = client.post("/api/chat", json={"session_id": sid, "message": text}, headers=USER)
    assert r.status_code == 200, r.text
    return r.json()


def test_gloves_flow_to_decision(client):
    upload_sample(client)
    r = say(client, "I need 100 pairs of nitrile coated gloves for Chakan by Friday - urgent")
    assert r["mode"] == "fallback"
    slots = r["state"]["slots"]
    assert (slots["item_code"], slots["quantity"], slots["uom"], slots["plant"], slots["need_by"]) == \
        ("ITM-1048", "100", "PAIR", "CHK1", "2026-11-20")
    assert slots["urgency"] is None and "Is this an Emergency?" in r["reply"]
    r = say(client, "no", r["session_id"])
    assert r["state"]["stage"] == "awaiting_confirmation"
    card = r["card"]
    assert card["item_code"] == "ITM-1048" and card["urgency"] == "Normal"
    assert card["need_by_display"] == "Fri 20 Nov 2026"
    c = client.post(f"/api/chat/{r['session_id']}/confirm", headers=USER)
    assert c.status_code == 200, c.text
    out = c.json()
    assert out["pr_no"] == "CH-26-00001"
    assert out["row"]["route"] and out["row"]["route"] != "NOT_PROCESSED"
    assert out["requirement"]["id"] and "CH-26-00001/1" in out["requirement"]["lines"]
    assert out["decision_summary"]
    # confirming again is refused
    assert client.post(f"/api/chat/{r['session_id']}/confirm", headers=USER).status_code == 409
    detail = client.get(f"/api/requirements/{out['requirement']['id']}").json()
    assert any(l["pr_no"] == "CH-26-00001" and l["department"] == "Maintenance" for l in detail["lines"])


def test_ambiguous_item_offers_candidates_and_select(client):
    r = say(client, "gloves")
    assert r["state"]["stage"] == "awaiting_selection"
    codes = [c["item_code"] for c in r["candidates"]]
    assert len(codes) >= 2
    r2 = client.post("/api/chat", json={"session_id": r["session_id"], "action": "select", "choice": codes[1]},
                     headers=USER).json()
    assert r2["state"]["slots"]["item_code"] == codes[1]
    r3 = say(client, "2", r["session_id"])          # a stray number is now a quantity answer, not a choice
    assert r3["state"]["slots"]["item_code"] == codes[1]


def test_unknown_item_becomes_new_with_estimate(client):
    r = say(client, "need 3 flux capacitor gizmos for Bhosari tomorrow")
    assert r["state"]["stage"] == "awaiting_new_item_estimate"
    assert "estimated unit price" in r["reply"]
    r = say(client, "₹1,250 each", r["session_id"])
    s = r["state"]["slots"]
    assert s["is_new"] is True and s["item_code"] is None and s["estimate"] == "1250"
    assert s["plant"] == "PUN1" and s["need_by"] == "2026-11-19"
    assert "unit of measure" in r["reply"] and "Is this an Emergency?" in r["reply"]
    r = say(client, "NOS", r["session_id"])
    assert r["state"]["slots"]["uom"] == "NOS"
    r = say(client, "normal", r["session_id"])
    assert r["state"]["stage"] == "awaiting_confirmation"
    assert r["card"]["item_code"] == "NEW"          # never an invented code
    out = client.post(f"/api/chat/{r['session_id']}/confirm", headers=USER).json()
    assert out["row"]["route"] == "NEW_ITEM_SOURCING" and out["row"]["resolved_item_code"] == "NEW"


def test_uom_mismatch_and_past_date_reask(client):
    r = say(client, "50 kg nitrile coated gloves for CHK1 by 2026-11-01")
    s = r["state"]["slots"]
    assert s["item_code"] == "ITM-1048" and s["quantity"] is None
    assert "Please give the quantity in PAIR" in r["reply"]
    assert "in the past" in r["reply"] and s["need_by"] is None


def test_cancel_and_errors(client):
    r = say(client, "nitrile coated gloves")
    r = say(client, "cancel", r["session_id"])
    assert r["state"]["slots"]["item_code"] is None
    assert client.post("/api/chat", json={"message": "x"}).status_code == 400            # no X-User
    assert client.post("/api/chat", json={"message": ""}, headers=USER).status_code == 422
    assert client.post("/api/chat/999/confirm", headers=USER).status_code == 404
