"""Chat history: owner isolation, bearer-over-header, persistence, confirm payload, migration round trip."""
import pytest
from tests.api_client import upload_sample

A = {"X-User": "alice", "X-Role": "requester", "X-Department": "Maintenance"}
B = {"X-User": "bob", "X-Role": "requester", "X-Department": "Maintenance"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setenv("APP_TODAY", "2026-11-18")


def say(client, text, headers=A, **extra):
    r = client.post("/api/chat", json={"message": text, **extra}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_conversation_crud_and_isolation(client):
    first = say(client, "I need 100 pairs of nitrile coated gloves for Chakan by Friday")
    cid = first["conversation_id"]
    assert first["conversation"]["title"].startswith("I need 100 pairs")
    second = say(client, "no", session_id=first["session_id"], conversation_id=cid)
    assert second["conversation_id"] == cid
    rows = client.get(f"/api/chat/conversations/{cid}", headers=A).json()["messages"]
    assert [r["role"] for r in rows] == ["user", "assistant", "user", "assistant"]
    assert [c["id"] for c in client.get("/api/chat/conversations", headers=A).json()] == [cid]

    assert client.get("/api/chat/conversations", headers=B).json() == []
    url = f"/api/chat/conversations/{cid}"
    assert client.get(url, headers=B).status_code == 404
    assert client.patch(url, json={"title": "x"}, headers=B).status_code == 404
    assert client.delete(url, headers=B).status_code == 404
    assert client.post("/api/chat", json={"message": "hi", "conversation_id": cid}, headers=B).status_code == 404

    assert client.patch(url, json={"title": "  Gloves  "}, headers=A).json()["title"] == "Gloves"
    assert client.patch(url, json={"title": "   "}, headers=A).status_code == 422
    assert client.delete(url, headers=A).json() == {"ok": True}
    assert client.get(url, headers=A).status_code == 404


def test_chat_without_conversation_id_still_works(client):
    r = say(client, "50 litres of cutting oil for Pune next Monday")
    assert r["session_id"] and r["conversation_id"]
    r2 = say(client, "yes", session_id=r["session_id"])
    assert r2["conversation_id"] == r["conversation_id"]


def test_bearer_token_wins_over_header(client):
    login = client.post("/api/auth/login", json={"email": "buyer@corvo.demo", "password": "corvo-demo"})
    assert login.status_code == 200, login.text
    token = {"Authorization": "Bearer " + login.json()["token"]}
    cid = say(client, "10 safety helmets for Chakan tomorrow", headers={**token, **A})["conversation_id"]
    assert [c["id"] for c in client.get("/api/chat/conversations", headers={**token, **B}).json()] == [cid]
    assert client.get("/api/chat/conversations", headers={"Authorization": "Bearer bad", **A}).status_code == 401


def test_confirm_persists_result(client):
    upload_sample(client)
    r = say(client, "I need 100 pairs of nitrile coated gloves for Chakan by Friday - urgent")
    r = say(client, "no", session_id=r["session_id"])
    out = client.post(f"/api/chat/{r['session_id']}/confirm", headers=A).json()
    assert out["conversation_id"] == r["conversation_id"]
    conv = client.get(f"/api/chat/conversations/{r['conversation_id']}", headers=A).json()
    assert conv["stage"] == "created"
    assert conv["messages"][-1]["payload"]["result"]["pr_no"] == out["pr_no"]
