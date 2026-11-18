"""No Blocked or Inactive supplier may ever appear in a PO or a suggestion."""
import copy

import pytest

from engine import EngineInvariantError
from tests.helpers import BLOCKED_OR_INACTIVE, master_data, rule_index, run


def leaf(f, o, v):
    return {"fact": f, "op": o, "value": v}


def variants(doc):
    out = {"v5": copy.deepcopy(doc)}
    d = copy.deepcopy(doc); d["parameters"]["spot_max_value"] = 300000; out["a"] = d
    d = copy.deepcopy(doc); d["parameters"]["emergency_max_value"] = 750000; out["c"] = d
    d = copy.deepcopy(doc); d["parameters"]["club_created_days"] = 7; out["e"] = d
    d = copy.deepcopy(doc)
    i, j = rule_index(d, "5.3"), rule_index(d, "5.4")
    d["rules"][i], d["rules"][j] = d["rules"][j], d["rules"][i]; out["f"] = d
    d = copy.deepcopy(doc)
    d["parameters"]["ranking_weights"] = {"frequency": 0, "recency": 0, "contract": 0, "on_time": 0.5, "quality": 0.5}
    out["h"] = d
    d = copy.deepcopy(doc)   # suggest more suppliers than exist, so top-up reaches every candidate
    for k in ("capex_suggestion_count", "rfq_suggestion_count", "rfp_suggestion_count"):
        d["parameters"][k] = 50
    out["max-suggestions"] = d
    d = copy.deepcopy(doc)   # every requirement goes to sourcing with suggestions
    d["rules"].insert(0, {"id": "ALL", "clause": "test", "text": "suggest for everything",
                          "when": {"all": [leaf("line_count", "gte", 1), leaf("is_new_item", "eq", False)]},
                          "outcome": {"decision": "SOURCING_REQUEST", "route": "RFQ",
                                      "supplier": {"strategy": "suggest", "count": 50}}})
    out["suggest-all"] = d
    return out


@pytest.mark.parametrize("name", ["v5", "a", "c", "e", "f", "h", "max-suggestions", "suggest-all"])
def test_no_blocked_or_inactive_supplier(policy_doc, name):
    m = master_data()
    assert all(m.suppliers[s].status in ("Blocked", "Inactive") for s in BLOCKED_OR_INACTIVE)
    res = run(variants(policy_doc)[name])
    for r in res.rows:
        assert r.supplier_id not in BLOCKED_OR_INACTIVE, (name, r)
        assert not set(r.suggested_supplier_ids.split(";")) & set(BLOCKED_OR_INACTIVE), (name, r)
    for d in res.decisions.values():
        for entry in d.trace.get("ranking", []):
            assert entry["supplier_id"] not in BLOCKED_OR_INACTIVE


def test_output_guard_rejects_ineligible_supplier(policy_doc):
    """Second line of defence: the row builder refuses an ineligible supplier even if one slipped through."""
    from engine import load_policy
    from engine.output import build_rows
    from tests.helpers import sample_lines

    res = run(policy_doc)
    req = next(r for r in res.requirements if res.decisions[r.group_id].supplier_id)
    res.decisions[req.group_id].supplier_id = "S004"
    rows_of_req = {l.row_index for l in req.lines}
    raw = [l for l in sample_lines() if l.row_index in rows_of_req]
    with pytest.raises(EngineInvariantError):
        build_rows(raw, [], [req], res.decisions, master_data(), {"5.0": load_policy(policy_doc).params})
