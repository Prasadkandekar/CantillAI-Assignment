"""Structural diff and deterministic bullets for the proof-test style edits (a-d, f)."""
import copy

from services.policy_diff import diff_and_bullets
from tests.helpers import load_doc, rule_index


def leaf(f, o, v):
    return {"fact": f, "op": o, "value": v}


def test_a_parameter_bullet():
    old = load_doc()
    new = copy.deepcopy(old)
    new["parameters"]["spot_max_value"] = 300000
    out = diff_and_bullets(old, new)
    assert out["structural"]["parameters"]["changed"] == {"spot_max_value": {"old": 200000, "new": 300000}}
    assert out["bullets"] == ["Spot PO limit (5.4) changes from ₹2,00,000 to ₹3,00,000"]


def test_b_new_rule_bullet():
    old = load_doc()
    new = copy.deepcopy(old)
    new["rules"].insert(rule_index(new, "5.4"), {
        "id": "CHK1-PPE", "clause": "amendment", "text": "x",
        "when": {"all": [leaf("plant", "eq", "CHK1"), leaf("category", "eq", "Safety & PPE"),
                         leaf("group_value", "gte", 100000)]},
        "outcome": {"decision": "SOURCING_REQUEST", "route": "RFQ",
                    "supplier": {"strategy": "suggest", "count": "$rfq_suggestion_count"}}})
    out = diff_and_bullets(old, new)
    assert out["structural"]["rules"]["added"][0]["before"] == "5.4"
    assert out["structural"]["rules"]["moved"] == []
    assert out["bullets"] == [
        "New rule CHK1-PPE before 5.4: when plant is CHK1 and item category is Safety & PPE and requirement value "
        "is at least ₹1,00,000 → Sourcing request, route RFQ, suggest 3 suppliers"]


def test_c_emergency_limit_bullet():
    old = load_doc()
    new = copy.deepcopy(old)
    new["parameters"]["emergency_max_value"] = 750000
    assert diff_and_bullets(old, new)["bullets"] == ["Emergency PO limit (5.3) changes from ₹5,00,000 to ₹7,50,000"]


def test_d_plant_rule_and_edit_bullets():
    old = load_doc()
    new = copy.deepcopy(old)
    new["parameters"]["chk1_emergency_max_value"] = 250000
    i = rule_index(new, "5.3")
    new["rules"][i]["when"]["all"].insert(0, leaf("plant", "not_in", ["CHK1"]))
    new["rules"].insert(i, {"id": "5.3-CHK1", "clause": "5.3 (CHK1)", "text": "t",
                            "when": {"all": [leaf("plant", "eq", "CHK1"), leaf("is_emergency", "eq", True),
                                             leaf("group_value", "lte", "$chk1_emergency_max_value")]},
                            "outcome": {"decision": "PO", "route": "EMERGENCY_PO",
                                        "supplier": {"strategy": "preferred_first"}}})
    b = diff_and_bullets(old, new)["bullets"]
    assert "New parameter chk1 emergency max value: ₹2,50,000" in b
    assert any(x.startswith("New rule 5.3-CHK1 before 5.3: when plant is CHK1 and emergency requirement and "
                            "requirement value is at most ₹2,50,000 → PO, route EMERGENCY_PO") for x in b)
    assert any(x.startswith("Rule 5.3 now applies when plant is not one of CHK1 and") for x in b)


def test_f_move_and_effective_date():
    old = load_doc()
    new = copy.deepcopy(old)
    i, j = rule_index(new, "5.3"), rule_index(new, "5.4")
    new["rules"][i], new["rules"][j] = new["rules"][j], new["rules"][i]
    new["effective_from"] = "2026-12-01"
    out = diff_and_bullets(old, new)
    assert len(out["structural"]["rules"]["moved"]) == 1
    assert "Effective from 1 Dec 2026" in out["bullets"]
    assert any(x in out["bullets"] for x in ("Rule 5.4 now comes before 5.3", "Rule 5.3 now comes before 5.5"))


def test_no_change_no_bullets():
    assert diff_and_bullets(load_doc(), load_doc())["bullets"] == []
