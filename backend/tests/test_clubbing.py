"""Clubbing boundaries. Windows are read from the policy, so the tests hold no window numbers."""
from datetime import datetime, timedelta

import pytest

from tests.helpers import by_key, line, run

ITEM, UOM = "ITM-1044", "NOS"       # VCI bag: no contract, bought recently
T0 = datetime(2026, 11, 2, 10, 0)
NB0 = datetime(2026, 12, 15)


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def d(dt):
    return dt.strftime("%Y-%m-%d")


def mk(n, created, need_by, plant="PUN1", item=ITEM, urgency="Normal", **kw):
    return line(f"PR-T-{n:03d}", ts(created), plant, item, 100, UOM, d(need_by), urgency, **kw)


@pytest.fixture(scope="module")
def windows(policy_doc):
    p = policy_doc["parameters"]
    return p["club_created_days"], p["club_needby_days"]


def groups(result):
    return {k: r.group_id for k, r in by_key(result).items()}


def runs(policy_doc, lines):
    return groups(run(policy_doc, lines, include_sample=False))


def test_created_exactly_window_days_later_joins(policy_doc, windows):
    days, _ = windows
    g = runs(policy_doc, [mk(1, T0, NB0), mk(2, T0 + timedelta(days=days, hours=13), NB0)])
    assert g["PR-T-001/1"] == g["PR-T-002/1"]


def test_created_one_day_past_window_does_not_join(policy_doc, windows):
    days, _ = windows
    g = runs(policy_doc, [mk(1, T0, NB0), mk(2, T0 + timedelta(days=days + 1), NB0)])
    assert g["PR-T-001/1"] != g["PR-T-002/1"]


@pytest.mark.parametrize("sign", [1, -1])
def test_need_by_window_either_side(policy_doc, windows, sign):
    _, nb = windows
    inside = runs(policy_doc, [mk(1, T0, NB0), mk(2, T0 + timedelta(hours=1), NB0 + sign * timedelta(days=nb))])
    assert inside["PR-T-001/1"] == inside["PR-T-002/1"]
    outside = runs(policy_doc, [mk(1, T0, NB0), mk(2, T0 + timedelta(hours=1), NB0 + sign * timedelta(days=nb + 1))])
    assert outside["PR-T-001/1"] != outside["PR-T-002/1"]


def test_compare_to_first_line_no_chaining(policy_doc, windows):
    days, _ = windows
    g = runs(policy_doc, [mk(1, T0, NB0), mk(2, T0 + timedelta(days=days), NB0),
                          mk(3, T0 + timedelta(days=days + 1), NB0)])
    assert g["PR-T-001/1"] == g["PR-T-002/1"]
    assert g["PR-T-003/1"] != g["PR-T-001/1"]


def test_joins_earliest_qualifying_requirement(policy_doc, windows):
    _, nb = windows
    a_nb, b_nb = NB0, NB0 + timedelta(days=nb + 1)
    mid = NB0 + timedelta(days=(nb + 1) // 2)
    g = runs(policy_doc, [mk(1, T0, a_nb), mk(2, T0 + timedelta(hours=1), b_nb), mk(3, T0 + timedelta(hours=2), mid)])
    assert g["PR-T-001/1"] != g["PR-T-002/1"]
    assert g["PR-T-003/1"] == g["PR-T-001/1"]


def test_different_plant_or_item_never_clubbed(policy_doc):
    g = runs(policy_doc, [mk(1, T0, NB0), mk(2, T0, NB0, plant="CHK1"), mk(3, T0, NB0, item="ITM-1041")])
    assert len(set(g.values())) == 3


def test_new_items_never_clubbed(policy_doc):
    desc = "Drinking water purifier 50 LPH"
    lines = [line("PR-T-001", ts(T0), "PUN1", "", 1, "NOS", d(NB0), description=desc, estimated_unit_price="1000"),
             line("PR-T-002", ts(T0 + timedelta(hours=1)), "PUN1", "", 1, "NOS", d(NB0), description=desc,
                  estimated_unit_price="1000")]
    res = run(policy_doc, lines, include_sample=False)
    rows = by_key(res)
    assert rows["PR-T-001/1"].resolved_item_code == rows["PR-T-002/1"].resolved_item_code == "NEW"
    assert rows["PR-T-001/1"].group_id != rows["PR-T-002/1"].group_id


def test_emergency_and_normal_club_and_become_emergency(policy_doc):
    res = run(policy_doc, [mk(1, T0, NB0), mk(2, T0 + timedelta(hours=2), NB0, urgency="Emergency")],
              include_sample=False)
    rows = by_key(res)
    assert rows["PR-T-001/1"].group_id == rows["PR-T-002/1"].group_id
    assert res.decisions[rows["PR-T-001/1"].group_id].trace["facts"]["is_emergency"] is True


def test_group_ids_follow_first_line_order(policy_doc):
    g = runs(policy_doc, [mk(2, T0 + timedelta(hours=5), NB0, item="ITM-1041"), mk(1, T0, NB0)])
    assert g["PR-T-001/1"] == "REQ-0001" and g["PR-T-002/1"] == "REQ-0002"
