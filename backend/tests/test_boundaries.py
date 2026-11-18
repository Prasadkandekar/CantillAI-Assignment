"""Value boundaries, built from the policy parameters. A synthetic item bought at 0.01 lets the
test hit any value exactly: quantity = value / 0.01."""
import copy
from datetime import date
from decimal import Decimal

import pytest

from engine import build_master, load_policy, raw_line, run_batch
from engine.models import Item, PORecord
from tests.helpers import load_doc, master_data

PRICE = Decimal("0.01")
CODE = "ITM-T001"


@pytest.fixture(scope="module")
def master():
    m = master_data()
    items = dict(m.items)
    items[CODE] = Item(CODE, "Boundary test widget", "NOS", "Bearings & Transmission", "Material", PRICE)
    pos = [p for ps in m.po_by_item.values() for p in ps]
    pos.append(PORecord("T-1", date(2026, 10, 1), "S014", CODE, Decimal(1), "NOS", PRICE, "PUN1", True))
    return build_master(m.plants, items, m.suppliers, pos, m.contracts)


def decide(master, value, urgency="Normal"):
    qty = (Decimal(value) / PRICE).to_integral_value()
    rl = raw_line(dict(pr_no="PR-T-B", pr_line="1", created_at="2026-11-10 10:00", plant="PUN1", item_code=CODE,
                       description="", quantity=str(qty), uom="NOS", need_by_date="2026-11-30", urgency=urgency), 0)
    res = run_batch([rl], master, [load_policy(load_doc())])
    row = res.rows[0]
    assert Decimal(row.group_value_inr) == Decimal(value).quantize(PRICE)
    return row.route


P = load_doc()["parameters"]
CENT = Decimal("0.01")


def test_spot_limit_is_exclusive(master):
    assert decide(master, Decimal(P["spot_max_value"])) == "RFQ"
    assert decide(master, Decimal(P["spot_max_value"]) - CENT) == "SPOT_PO"


def test_emergency_limit_is_inclusive(master):
    assert decide(master, Decimal(P["emergency_max_value"]), "Emergency") == "EMERGENCY_PO"
    assert decide(master, Decimal(P["emergency_max_value"]) + CENT, "Emergency") == "RFQ"


def test_rfp_threshold_is_inclusive(master):
    assert decide(master, Decimal(P["rfp_min_value"])) == "RFP"
    assert decide(master, Decimal(P["rfp_min_value"]) - CENT) == "RFQ"


def test_boundaries_follow_the_json(master):
    # change only the JSON: the boundary moves with it
    doc = copy.deepcopy(load_doc())
    i = [r["id"] for r in doc["rules"]].index("5.4")
    doc["rules"][i]["when"]["all"][0]["op"] = "lte"
    qty = (Decimal(P["spot_max_value"]) / PRICE).to_integral_value()
    rl = raw_line(dict(pr_no="PR-T-B", pr_line="1", created_at="2026-11-10 10:00", plant="PUN1", item_code=CODE,
                       description="", quantity=str(qty), uom="NOS", need_by_date="2026-11-30", urgency="Normal"), 0)
    assert run_batch([rl], master, [load_policy(doc)]).rows[0].route == "SPOT_PO"
