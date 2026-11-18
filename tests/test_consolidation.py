"""PO consolidation boundaries. The window comes from the policy."""
from datetime import datetime, timedelta

import pytest

from tests.helpers import by_key, line, run

T0 = datetime(2026, 11, 3, 9, 0)


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def mk(n, created, item, plant="PUN1", qty=100, uom="NOS"):
    return line(f"PR-T-{n:03d}", ts(created), plant, item, qty, uom, "2026-12-10")


@pytest.fixture(scope="module")
def hours(policy_doc):
    return policy_doc["parameters"]["consolidation_hours"]


def rows_for(policy_doc, lines):
    return by_key(run(policy_doc, lines, include_sample=False))


# ITM-1010 and ITM-1011 are both only on contract RC-2026-013 (S007): CONTRACT_PO, same supplier.
def test_exactly_window_hours_later_shares_po(policy_doc, hours):
    r = rows_for(policy_doc, [mk(1, T0, "ITM-1010"), mk(2, T0 + timedelta(hours=hours), "ITM-1011")])
    assert r["PR-T-001/1"].route == r["PR-T-002/1"].route == "CONTRACT_PO"
    assert r["PR-T-001/1"].supplier_id == r["PR-T-002/1"].supplier_id == "S007"
    assert r["PR-T-001/1"].group_id != r["PR-T-002/1"].group_id
    assert r["PR-T-001/1"].po_id == r["PR-T-002/1"].po_id


def test_one_minute_past_window_gets_own_po(policy_doc, hours):
    r = rows_for(policy_doc, [mk(1, T0, "ITM-1010"), mk(2, T0 + timedelta(hours=hours, minutes=1), "ITM-1011")])
    assert r["PR-T-001/1"].po_id != r["PR-T-002/1"].po_id


def test_window_measured_from_first_requirement_of_the_po(policy_doc, hours):
    half = timedelta(hours=hours) / 2 + timedelta(minutes=1)
    r = rows_for(policy_doc, [mk(1, T0, "ITM-1010"), mk(2, T0 + half, "ITM-1011"), mk(3, T0 + 2 * half, "ITM-1013")])
    assert r["PR-T-001/1"].po_id == r["PR-T-002/1"].po_id
    assert r["PR-T-003/1"].po_id != r["PR-T-001/1"].po_id


def test_different_plant_never_merges(policy_doc):
    r = rows_for(policy_doc, [mk(1, T0, "ITM-1010"), mk(2, T0 + timedelta(hours=1), "ITM-1011", plant="CHK1")])
    assert r["PR-T-001/1"].po_id != r["PR-T-002/1"].po_id


def test_different_route_or_supplier_never_merges(policy_doc):
    # ITM-1044 is a spot PO to S027; ITM-1010 a contract PO to S007
    r = rows_for(policy_doc, [mk(1, T0, "ITM-1010"), mk(2, T0 + timedelta(hours=1), "ITM-1044")])
    assert r["PR-T-002/1"].route == "SPOT_PO"
    assert r["PR-T-001/1"].po_id != r["PR-T-002/1"].po_id


def test_sourcing_requests_never_consolidated(policy_doc):
    # two CMM calibration RFQs within the window
    r = rows_for(policy_doc, [line("PR-T-001", ts(T0), "PUN1", "ITM-1066", 5, "JOB", "2026-12-10"),
                              line("PR-T-002", ts(T0 + timedelta(hours=1)), "CHK1", "ITM-1066", 5, "JOB", "2026-12-10")])
    assert r["PR-T-001/1"].route == r["PR-T-002/1"].route == "RFQ"
    assert r["PR-T-001/1"].po_id == r["PR-T-002/1"].po_id == ""


def test_po_ids_numbered_in_creation_order(policy_doc):
    r = rows_for(policy_doc, [mk(2, T0 + timedelta(days=3), "ITM-1011"), mk(1, T0, "ITM-1010")])
    assert r["PR-T-001/1"].po_id == "PO-0001" and r["PR-T-002/1"].po_id == "PO-0002"


def test_example_14_shares_example_4_po(baseline):
    r = by_key(baseline)
    assert r["PR-26-00031/1"].po_id == r["PR-26-00034/1"].po_id == r["PR-26-00032/1"].po_id == r["PR-26-00035/1"].po_id


def test_window_is_a_parameter(policy_doc, hours):
    import copy
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["consolidation_hours"] = hours * 2
    lines = [mk(1, T0, "ITM-1010"), mk(2, T0 + timedelta(hours=hours, minutes=1), "ITM-1011")]
    r = rows_for(doc, lines)
    assert r["PR-T-001/1"].po_id == r["PR-T-002/1"].po_id
