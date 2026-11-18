"""Proof tests a-h: each edits ONLY the policy JSON (in memory), reruns the same batch and asserts
the exact set of changed lines. No engine code is patched or imported beyond the public API."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest

from engine import PolicyValidationError, build_preferred_list, load_policy, validate, validate_or_raise
from tests.helpers import by_key, changed, fired_rule, line, master_data, rule_index, run

EXPECTED_DIR = Path(__file__).parent / "expected"


def keys(*items):
    return {i if "/" in i else f"{i}/1" for i in items}


SYNTHETIC_EMERGENCIES = [
    line("PR-T-C001", "2026-11-25 10:00", "PUN1", "ITM-1026", 6000, "NOS", "2026-12-05", "Emergency"),
    line("PR-T-C002", "2026-12-05 10:00", "CHK1", "ITM-1026", 6000, "NOS", "2026-12-15", "Emergency"),
]
SYNTHETIC_KEYS = {"PR-T-C001/1", "PR-T-C002/1"}


def leaf(fact, op, value):
    return {"fact": fact, "op": op, "value": value}


# a. spot limit 200000 -> 300000 --------------------------------------------------------------
def test_a_raise_spot_limit(policy_doc, baseline):
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["spot_max_value"] = 300000
    new = run(doc)
    expected = keys("PR-26-00004", "PR-26-00026", "PR-26-00001", "PR-26-00007", "PR-26-00015", "PR-26-00039",
                    "PR-26-00041", "PR-26-00077", "PR-26-00096", "PR-26-00104", "PR-26-00107", "PR-26-00120",
                    "PR-26-00164/1", "PR-26-00164/3")
    assert changed(baseline, new) == expected
    b, n = by_key(baseline), by_key(new)
    for k in expected:
        assert b[k].route == "RFQ" and n[k].route == "SPOT_PO", k
        assert fired_rule(new, k) == "5.4"
    ex3 = n["PR-26-00004/1"]
    assert (ex3.supplier_id, ex3.unit_price, ex3.group_value_inr) == ("S014", "640.23", "220255.60")
    assert n["PR-26-00026/1"].po_id == ex3.po_id
    assert n["PR-26-00001/1"].supplier_id == "S032"
    assert n["PR-26-00007/1"].supplier_id == "S006"
    assert n["PR-26-00104/1"].supplier_id == n["PR-26-00107/1"].supplier_id == "S028"
    for k in ("PR-26-00053/1", "PR-26-00165/2"):     # never bought: still RFQ
        assert n[k].route == "RFQ" and n[k].group_value_inr == "203000.00"


# b. inserted CHK1 Safety & PPE rule ------------------------------------------------------------
def test_b_insert_chk1_ppe_rule_before_spot(policy_doc, baseline):
    doc = copy.deepcopy(policy_doc)
    doc["rules"].insert(rule_index(doc, "5.4"), {
        "id": "CHK1-PPE", "clause": "amendment",
        "text": "At CHK1, Safety & PPE requirements of \u20b91,00,000 or more go to RFQ.",
        "when": {"all": [leaf("plant", "eq", "CHK1"), leaf("category", "eq", "Safety & PPE"),
                         leaf("group_value", "gte", 100000)]},
        "outcome": {"decision": "SOURCING_REQUEST", "route": "RFQ",
                    "supplier": {"strategy": "suggest", "count": "$rfq_suggestion_count"}}})
    new = run(doc)
    expected = keys("PR-26-00136", "PR-26-00137", "PR-26-00138", "PR-26-00139")
    assert changed(baseline, new) == expected
    b, n = by_key(baseline), by_key(new)
    for k in expected:
        assert (b[k].route, b[k].supplier_id) == ("SPOT_PO", "S029")
        assert (n[k].route, n[k].suggested_supplier_ids, n[k].supplier_id) == ("RFQ", "S029;S030", "")
        assert n[k].group_value_inr == "121326.00"
        assert fired_rule(new, k) == "CHK1-PPE"
    assert fired_rule(new, "PR-26-00060/1") == "5.3"
    assert fired_rule(new, "PR-26-00023/1") == "5.2"
    assert n["PR-26-00076/1"].route == b["PR-26-00076/1"].route


# c. emergency limit 500000 -> 750000 -------------------------------------------------------------
def test_c_raise_emergency_limit(policy_doc):
    base = run(policy_doc, SYNTHETIC_EMERGENCIES)
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["emergency_max_value"] = 750000
    new = run(doc, SYNTHETIC_EMERGENCIES)
    assert changed(base, new) == SYNTHETIC_KEYS        # no sample line changes
    b, n = by_key(base), by_key(new)
    for k in SYNTHETIC_KEYS:
        assert b[k].route == "RFQ"
        assert (n[k].route, n[k].supplier_id, n[k].unit_price, n[k].group_value_inr) == \
            ("EMERGENCY_PO", "S014", "106.38", "638280.00")
        assert fired_rule(new, k) == "5.3"
        # the synthetic lines club with nothing
        assert sum(1 for r in new.rows if r.group_id == n[k].group_id) == 1


# d. plant-only emergency limit for CHK1 --------------------------------------------------------
def chk1_emergency_doc(policy_doc, limit):
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["chk1_emergency_max_value"] = limit
    i = rule_index(doc, "5.3")
    generic = doc["rules"][i]
    generic["when"]["all"].insert(0, leaf("plant", "not_in", ["CHK1"]))
    doc["rules"].insert(i, {
        "id": "5.3-CHK1", "clause": "5.3 (CHK1 amendment)",
        "text": "For plant CHK1, an emergency within the CHK1 limit bought from an Active supplier may be placed as an Emergency PO.",
        "when": {"all": [leaf("plant", "eq", "CHK1"), leaf("is_emergency", "eq", True),
                         leaf("group_value", "lte", "$chk1_emergency_max_value"),
                         leaf("bought_from_active_365d", "eq", True)]},
        "outcome": {"decision": "PO", "route": "EMERGENCY_PO", "supplier": {"strategy": "preferred_first"}}})
    return doc


def test_d1_lower_chk1_emergency_limit_changes_only_chk1(policy_doc, baseline):
    new = run(chk1_emergency_doc(policy_doc, 250000))
    ch = changed(baseline, new)
    assert ch == {"PR-26-00058/1"}
    n, b = by_key(new), by_key(baseline)
    assert b["PR-26-00058/1"].route == "EMERGENCY_PO"
    assert (n["PR-26-00058/1"].route, n["PR-26-00058/1"].suggested_supplier_ids) == ("RFQ", "S009;S010;S012")
    for k in ("PR-26-00057/1", "PR-26-00060/1"):
        assert n[k].route == "EMERGENCY_PO" and fired_rule(new, k) == "5.3-CHK1"
    for k in ("PR-26-00055/1", "PR-26-00059/1", "PR-26-00056/1"):
        assert n[k].route == b[k].route
    lines = {f"{r['pr_no']}/{r['pr_line']}": r for r in _sample_dicts()}
    assert all(lines[k]["plant"] == "CHK1" for k in ch)


def test_d_control_generic_limit_changes_both_plants(policy_doc, baseline):
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["emergency_max_value"] = 250000
    assert changed(baseline, run(doc)) == keys("PR-26-00055", "PR-26-00058", "PR-26-00059")


def test_d2_raise_chk1_emergency_limit_changes_only_chk1(policy_doc):
    base = run(policy_doc, SYNTHETIC_EMERGENCIES)
    new = run(chk1_emergency_doc(policy_doc, 750000), SYNTHETIC_EMERGENCIES)
    assert changed(base, new) == {"PR-T-C002/1"}
    n = by_key(new)
    assert n["PR-T-C002/1"].route == "EMERGENCY_PO" and fired_rule(new, "PR-T-C002/1") == "5.3-CHK1"
    assert n["PR-T-C001/1"].route == "RFQ"


# e. club_created_days 14 -> 7 ----------------------------------------------------------------
def test_e_shorter_clubbing_window_changes_grouping(policy_doc, baseline):
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["club_created_days"] = 7
    new = run(doc)
    co2 = keys("PR-26-00102", "PR-26-00126", "PR-26-00127", "PR-26-00128", "PR-26-00129")
    argon = keys("PR-26-00069", "PR-26-00091")
    contactor = keys("PR-26-00081", "PR-26-00119")
    taper = keys("PR-26-00027", "PR-26-00009")
    assert changed(baseline, new) == co2 | argon | contactor | taper
    b, n = by_key(baseline), by_key(new)
    assert (b["PR-26-00102/1"].route, b["PR-26-00102/1"].group_value_inr) == ("RFP", "1574857.06")
    assert (n["PR-26-00102/1"].route, n["PR-26-00102/1"].group_value_inr) == ("RFP", "1342248.18")
    rest = co2 - {"PR-26-00102/1"}
    assert len({n[k].group_id for k in rest}) == 1
    assert all((n[k].route, n[k].group_value_inr) == ("RFQ", "232608.88") for k in rest)
    assert (n["PR-26-00069/1"].route, n["PR-26-00069/1"].supplier_id, n["PR-26-00069/1"].group_value_inr) == \
        ("SPOT_PO", "S012", "178966.26")
    assert (n["PR-26-00091/1"].route, n["PR-26-00091/1"].group_value_inr) == ("RFQ", "386034.66")
    assert (n["PR-26-00081/1"].route, n["PR-26-00081/1"].supplier_id, n["PR-26-00081/1"].group_value_inr) == \
        ("SPOT_PO", "S019", "163137.60")
    assert n["PR-26-00027/1"].group_id != n["PR-26-00009/1"].group_id
    # hex bolt requirements of examples 4 and 14 are unchanged
    assert n["PR-26-00034/1"].group_id == n["PR-26-00032/1"].group_id
    assert n["PR-26-00031/1"].group_id == n["PR-26-00035/1"].group_id


# f. reorder two rules ------------------------------------------------------------------------
def test_f_swap_emergency_and_spot_rules(policy_doc, baseline):
    doc = copy.deepcopy(policy_doc)
    i, j = rule_index(doc, "5.3"), rule_index(doc, "5.4")
    doc["rules"][i], doc["rules"][j] = doc["rules"][j], doc["rules"][i]
    new = run(doc)
    assert changed(baseline, new) == keys("PR-26-00057", "PR-26-00060")
    b, n = by_key(baseline), by_key(new)
    for k in keys("PR-26-00057", "PR-26-00060"):
        assert (b[k].route, n[k].route) == ("EMERGENCY_PO", "SPOT_PO")
        assert b[k].supplier_id == n[k].supplier_id
        assert fired_rule(new, k) == "5.4"
    assert n["PR-26-00057/1"].supplier_id == "S023" and n["PR-26-00060/1"].supplier_id == "S029"


# g. unknown fact is rejected ------------------------------------------------------------------
def test_g_unknown_fact_rejected(policy_doc):
    doc = copy.deepcopy(policy_doc)
    i = rule_index(doc, "5.4")
    doc["rules"][i]["when"]["all"].append(leaf("supplier_mood", "eq", "happy"))
    res = validate(doc)
    assert any(e.path == f"rules[{i}].when.all[2].fact" and "unknown fact 'supplier_mood'" in e.message
               for e in res.errors), res.errors
    with pytest.raises(PolicyValidationError):
        validate_or_raise(doc)
    with pytest.raises(PolicyValidationError):
        load_policy(doc)


# h. ranking weights ---------------------------------------------------------------------------
def test_h_ranking_weights_change_preferred_order(policy_doc, baseline):
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["ranking_weights"] = {"frequency": 0, "recency": 0, "contract": 0, "on_time": 0.5, "quality": 0.5}
    validate_or_raise(doc)
    as_of = date(2026, 11, 1)
    before = build_preferred_list("ITM-1036", as_of, master_data(), load_policy(policy_doc).params)
    after = build_preferred_list("ITM-1036", as_of, master_data(), load_policy(doc).params)
    assert [r.supplier_id for r in before] == ["S023", "S022", "S024"]
    assert [r.supplier_id for r in after] == ["S024", "S023", "S022"]
    for r, s in zip(after, (0.855, 0.760, 0.735)):
        assert float(r.score) == pytest.approx(s, abs=0.005)
    new = run(doc)
    expected = set(json.loads((EXPECTED_DIR / "proof_h_changed.json").read_text(encoding="utf-8")))
    assert len(expected) == 38
    assert changed(baseline, new) == expected
    b, n = by_key(baseline), by_key(new)
    assert (b["PR-26-00042/1"].supplier_id, b["PR-26-00042/1"].unit_price) == ("S023", "4360.80")
    assert (n["PR-26-00042/1"].route, n["PR-26-00042/1"].supplier_id, n["PR-26-00042/1"].unit_price) == \
        ("SPOT_PO", "S024", "3700.35")
    assert n["PR-26-00042/1"].group_value_inr == b["PR-26-00042/1"].group_value_inr == "174432.00"
    assert b["PR-26-00089/1"].suggested_supplier_ids == "S043;S044;S042"
    assert n["PR-26-00089/1"].suggested_supplier_ids == "S044;S043;S042"


def _sample_dicts():
    import csv
    from tests.helpers import BATCH_PATH
    with open(BATCH_PATH, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))
