"""Preferred supplier lists and CSV export (as of the worked-example ranking date)."""
import csv
import io
from decimal import Decimal

from tests.helpers import BLOCKED_OR_INACTIVE, load_doc

AS_OF = "2026-11-01"


def test_lists_match_engine_rankings(client):
    r = client.get("/api/preferred-suppliers", params={"as_of": AS_OF, "item_code": "ITM-1036"})
    assert r.status_code == 200
    body = r.json()
    assert body["policy_version"] == load_doc()["version"]
    sup = body["items"][0]["suppliers"]
    assert [s["supplier_id"] for s in sup] == ["S023", "S022", "S024"]
    for s in sup:
        total = sum(Decimal(f["contribution"]) for f in s["factors"].values())
        assert abs(total - Decimal(s["score"])) <= Decimal("0.00001")
        assert set(s["factors"]) == set(load_doc()["parameters"]["ranking_weights"])


def test_export_csv(client):
    r = client.get("/api/preferred-suppliers/export", params={"as_of": AS_OF})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert r.text.splitlines()[0] == "item_code,rank,supplier_id,reference_price"
    top = load_doc()["parameters"]["preferred_export_count"]
    per_item = {}
    for row in rows:
        per_item.setdefault(row["item_code"], []).append(int(row["rank"]))
        assert row["supplier_id"] not in BLOCKED_OR_INACTIVE
        assert "." in row["reference_price"] and len(row["reference_price"].split(".")[1]) == 2
    assert all(ranks == list(range(1, len(ranks) + 1)) and len(ranks) <= top for ranks in per_item.values())
    assert list(per_item) == sorted(per_item)
    assert [r["supplier_id"] for r in rows if r["item_code"] == "ITM-1048"] == ["S029", "S030"]


def test_errors(client):
    assert client.get("/api/preferred-suppliers").status_code == 422
    assert client.get("/api/preferred-suppliers", params={"as_of": "2025-01-01"}).status_code == 422
    assert client.get("/api/preferred-suppliers", params={"as_of": AS_OF, "item_code": "X"}).status_code == 404
    assert client.get("/api/preferred-suppliers", params={"as_of": AS_OF, "policy_version": "9.9"}).status_code == 404
