"""Validator: every error case gives a clear path and message; nothing is silently ignored."""
import copy

import pytest

from engine import PolicyValidationError, load_policy, validate, validate_or_raise
from tests.helpers import load_doc, rule_index

V5 = load_doc()
I53, I54, I55 = rule_index(V5, "5.3"), rule_index(V5, "5.4"), rule_index(V5, "5.5")


def edited(fn):
    doc = copy.deepcopy(V5)
    fn(doc)
    return doc


def errors(doc, base=None):
    return [str(e) for e in validate(doc, base).errors]


def warnings(doc, base=None):
    return [str(w) for w in validate(doc, base).warnings]


def assert_error(doc, path, fragment):
    res = validate(doc)
    hits = [e for e in res.errors if e.path == path and fragment in e.message]
    assert hits, f"expected error at {path!r} containing {fragment!r}; got {[str(e) for e in res.errors]}"
    with pytest.raises(PolicyValidationError):
        validate_or_raise(doc)


def test_v5_is_valid_with_no_warnings():
    res = validate(copy.deepcopy(V5))
    assert res.errors == [] and res.warnings == []
    load_policy(copy.deepcopy(V5))


def rule_leaf(doc, i, j):
    return doc["rules"][i]["when"]["all"][j]


ERROR_CASES = [
    # schema
    ("unknown top-level key", lambda d: d.update(order=1), "order", "unknown top-level key"),
    ("schema_version", lambda d: d.update(schema_version=2), "schema_version", "must be 1"),
    ("version missing", lambda d: d.pop("version"), "version", "required"),
    ("parameters missing", lambda d: d.pop("parameters"), "parameters", "required object missing"),
    ("rules empty", lambda d: d.update(rules=[]), "rules", "must be a non-empty list"),
    ("effective_from bad", lambda d: d.update(effective_from="01/04/2026"), "effective_from", "must be YYYY-MM-DD"),
    # facts, ops, strategies, params
    ("unknown fact", lambda d: rule_leaf(d, I53, 1).update(fact="supplier_mood"),
     f"rules[{I53}].when.all[1].fact", "unknown fact 'supplier_mood'. Known facts: "),
    ("unknown op", lambda d: rule_leaf(d, I53, 0).update(op="between"),
     f"rules[{I53}].when.all[0].op", "unknown op 'between'. Allowed: eq, ne, lt, lte, gt, gte, in, not_in"),
    ("unknown strategy", lambda d: d["rules"][I54]["outcome"]["supplier"].update(strategy="cheapest"),
     f"rules[{I54}].outcome.supplier.strategy", "unknown strategy 'cheapest'. Allowed: contract, preferred_first, suggest, none"),
    ("missing $param", lambda d: rule_leaf(d, I53, 1).update(value="$emergency_max_value_chk1"),
     f"rules[{I53}].when.all[1].value", "parameter '$emergency_max_value_chk1' is not defined in parameters"),
    ("op/type mismatch", lambda d: d["rules"][I54]["when"]["all"].append({"fact": "plant", "op": "lt", "value": "CHK1"}),
     f"rules[{I54}].when.all[2]", "op 'lt' is not valid for string fact 'plant'"),
    ("literal type mismatch", lambda d: rule_leaf(d, I54, 0).update(value="abc"),
     f"rules[{I54}].when.all[0].value", "fact 'group_value' is decimal; got string 'abc'"),
    ("param value string", lambda d: (d["parameters"].update(chk1_emergency_max_value="2.5 lakh"),
                                      rule_leaf(d, I53, 1).update(value="$chk1_emergency_max_value")),
     f"rules[{I53}].when.all[1].value",
     "parameter 'chk1_emergency_max_value' must be a number for decimal fact 'group_value'; got string '2.5 lakh'"),
    ("param value null", lambda d: d["parameters"].update(spot_max_value=None),
     f"rules[{I54}].when.all[0].value", "parameter 'spot_max_value' must be a number for decimal fact 'group_value'; got null"),
    ("param bool for number", lambda d: d["parameters"].update(spot_max_value=True),
     f"rules[{I54}].when.all[0].value", "parameter 'spot_max_value' must be a number"),
    ("in needs list", lambda d: d["rules"][I54]["when"]["all"].append({"fact": "plant", "op": "in", "value": "CHK1"}),
     f"rules[{I54}].when.all[2].value", "op 'in' needs a list"),
    ("not_in param not list", lambda d: (d["parameters"].update(chk1_plants="CHK1"),
                                         d["rules"][I54]["when"]["all"].append(
                                             {"fact": "plant", "op": "not_in", "value": "$chk1_plants"})),
     f"rules[{I54}].when.all[2].value", "parameter 'chk1_plants' must be a list for op 'not_in'; got string 'CHK1'"),
    ("list element type", lambda d: d["rules"][I54]["when"]["all"].append({"fact": "plant", "op": "in", "value": ["CHK1", 3]}),
     f"rules[{I54}].when.all[2].value", "item 1 must be a string"),
    ("date literal", lambda d: d["rules"][I54]["when"]["all"].append({"fact": "requirement_date", "op": "gte", "value": "2026-13-01"}),
     f"rules[{I54}].when.all[2].value", "fact 'requirement_date' is date"),
    ("bool literal", lambda d: rule_leaf(d, I53, 0).update(value="yes"),
     f"rules[{I53}].when.all[0].value", "fact 'is_emergency' is bool; got string 'yes'"),
    ("ordering op null literal", lambda d: rule_leaf(d, I54, 0).update(value=None),
     f"rules[{I54}].when.all[0].value", "only eq/ne accept null"),
    # node shape
    ("node without kind", lambda d: d["rules"][I54].update(when={"every": []}),
     f"rules[{I54}].when", "a condition must have exactly one of 'all', 'any' or 'fact'"),
    ("node with two kinds", lambda d: d["rules"][I54].update(when={"all": [], "any": []}),
     f"rules[{I54}].when", "exactly one of 'all', 'any' or 'fact'"),
    ("empty all", lambda d: d["rules"][I54].update(when={"all": []}), f"rules[{I54}].when.all", "must be a non-empty list"),
    ("nested any empty", lambda d: d["rules"][I54]["when"]["all"].append({"any": []}),
     f"rules[{I54}].when.all[2].any", "must be a non-empty list"),
    # key sets (review finding: nothing silently ignored)
    ("rule unknown key", lambda d: d["rules"][2].update(order=2), "rules[2]", "unknown key 'order'"),
    ("leaf typo values", lambda d: rule_leaf(d, I53, 0).update(values=True),
     f"rules[{I53}].when.all[0]", "unknown key 'values'; a condition leaf has exactly fact, op, value"),
    ("leaf missing value", lambda d: rule_leaf(d, I53, 0).pop("value"), f"rules[{I53}].when.all[0].value", "required"),
    ("leaf missing op", lambda d: rule_leaf(d, I53, 0).pop("op"), f"rules[{I53}].when.all[0].op", "required"),
    ("outcome unknown key", lambda d: d["rules"][I55]["outcome"].update(priority=1),
     f"rules[{I55}].outcome", "unknown key 'priority'"),
    ("supplier unknown key", lambda d: d["rules"][I55]["outcome"]["supplier"].update(cnt=3),
     f"rules[{I55}].outcome.supplier", "unknown key 'cnt'"),
    ("parameter_meta unknown key", lambda d: d["parameter_meta"]["spot_max_value"].update(note="x"),
     "parameter_meta.spot_max_value", "unknown key 'note'"),
    # outcome
    ("missing route", lambda d: d["rules"][I55]["outcome"].pop("route"), f"rules[{I55}].outcome.route", "required"),
    ("empty decision", lambda d: d["rules"][I55]["outcome"].update(decision=""),
     f"rules[{I55}].outcome.decision", "must be a non-empty string"),
    ("suggest without count", lambda d: d["rules"][I55]["outcome"]["supplier"].pop("count"),
     f"rules[{I55}].outcome.supplier.count", "strategy 'suggest' needs a count"),
    ("count zero literal", lambda d: d["rules"][I55]["outcome"]["supplier"].update(count=0),
     f"rules[{I55}].outcome.supplier.count", "must be an integer >= 1"),
    ("count param zero", lambda d: d["parameters"].update(rfq_suggestion_count=0),
     f"rules[{I55}].outcome.supplier.count", "parameter 'rfq_suggestion_count' must be an integer >= 1; got 0"),
    ("count missing param", lambda d: d["rules"][I55]["outcome"]["supplier"].update(count="$nope"),
     f"rules[{I55}].outcome.supplier.count", "parameter '$nope' is not defined"),
    ("count on forbidden strategy", lambda d: d["rules"][I54]["outcome"]["supplier"].update(count=1),
     f"rules[{I54}].outcome.supplier.count", "does not take a count"),
    ("PO without supplier", lambda d: d["rules"][I54]["outcome"]["supplier"].update(strategy="none"),
     f"rules[{I54}].outcome", "decision 'PO' is in consolidate_decisions and needs a supplier; strategy 'none' gives none"),
    # rules
    ("duplicate id", lambda d: d["rules"][I55].update(id="5.4"), f"rules[{I55}].id", "duplicate rule id '5.4'"),
    ("missing clause", lambda d: d["rules"][0].pop("clause"), "rules[0].clause", "required"),
    ("missing text", lambda d: d["rules"][0].update(text=""), "rules[0].text", "must be a non-empty string"),
    # fact parameter dependency
    ("fact needs param", lambda d: d["parameters"].pop("bought_history_days"),
     f"rules[{I53}]", "fact 'bought_from_active_365d' needs parameter 'bought_history_days' (an integer >= 0)"),
    ("fact param wrong type", lambda d: d["parameters"].update(bought_history_days="a year"),
     f"rules[{I53}]", "fact 'bought_from_active_365d' needs parameter 'bought_history_days'"),
    ("bad parameter value shape", lambda d: d["parameters"].update(odd=[[1]]), "parameters.odd", "must be a scalar"),
]


@pytest.mark.parametrize("name,edit,path,fragment", ERROR_CASES, ids=[c[0] for c in ERROR_CASES])
def test_error_case(name, edit, path, fragment):
    assert_error(edited(edit), path, fragment)


# every REQUIRED_PARAMETERS rule: missing / wrong type / bool for number / out of range
REQUIRED_CASES = [
    ("club_keys", [], ["item_code", "colour"], None),
    ("club_created_days", 14.5, -1, True),
    ("club_needby_days", "7", -1, True),
    ("club_new_items", "no", None, None),
    ("urgency_values", [], ["Normal", "normal"], None),
    ("emergency_urgency_values", "Emergency", ["Critical"], None),
    ("valuation_ladder", [], ["requester_estimate"], None),
    ("new_item_valuation", 3, "guess", None),
    ("price_history_days", 1.5, -1, True),
    ("eligible_supplier_statuses", [], [""], None),
    ("preferred_history_days", "x", -5, True),
    ("ranking_weights", {"frequency": 1}, {"frequency": -1, "recency": 0, "contract": 0, "on_time": 0, "quality": 0}, None),
    ("ranking_recency_decay_days", 1.5, 0, True),
    ("ranking_tie_break", "recency", ["mood"], None),
    ("on_time_pct_scale", "100", 0, True),
    ("quality_rating_scale", "5", -5, True),
    ("topup_weights", [], {"on_time": 0, "quality": 0}, None),
    ("preferred_export_count", 2.5, 0, True),
    ("consolidate_decisions", "PO", ["PO", "PO"], None),
    ("consolidation_keys", [], ["supplier_id", "colour"], None),
    ("consolidation_hours", "a day", -1, True),
]


@pytest.mark.parametrize("name,wrong_type,out_of_range,bool_check", REQUIRED_CASES, ids=[c[0] for c in REQUIRED_CASES])
def test_required_parameter(name, wrong_type, out_of_range, bool_check):
    path = f"parameters.{name}"
    assert_error(edited(lambda d: d["parameters"].pop(name)), path, "required, must be")
    assert_error(edited(lambda d: d["parameters"].update({name: wrong_type})), path, "got")
    if out_of_range is not None:
        assert_error(edited(lambda d: d["parameters"].update({name: out_of_range})), path, "got")
    if bool_check:
        assert_error(edited(lambda d: d["parameters"].update({name: True})), path, "got boolean")


def test_club_created_days_message():
    doc = edited(lambda d: d["parameters"].update(club_created_days=14.5))
    assert "parameters.club_created_days: required, must be an integer >= 0; got 14.5" in errors(doc)


def test_ranking_weights_missing_key_message():
    doc = edited(lambda d: d["parameters"]["ranking_weights"].pop("quality"))
    assert any("ranking_weights" in e and "missing 'quality'" in e for e in errors(doc))


def test_unreferenced_extra_parameter_is_only_a_warning():
    doc = edited(lambda d: d["parameters"].update(spare_limit=123))
    assert errors(doc) == []
    assert "parameters.spare_limit: defined but never referenced" in warnings(doc)


def test_parameter_meta_for_missing_parameter_is_a_warning():
    doc = edited(lambda d: d["parameter_meta"].update(spot_max_valu={"label": "typo"}))
    assert errors(doc) == []
    assert "parameter_meta.spot_max_valu: no such parameter" in warnings(doc)


def test_weights_summing_to_one_in_decimal_give_no_warning():
    doc = edited(lambda d: d["parameters"].update(topup_weights={"on_time": 0.3, "quality": 0.7},
                                                  ranking_weights={"frequency": 0.1, "recency": 0.2, "contract": 0.7,
                                                                   "on_time": 0, "quality": 0}))
    assert errors(doc) == [] and warnings(doc) == []


def test_weights_not_summing_to_one_warn():
    doc = edited(lambda d: d["parameters"].update(topup_weights={"on_time": 0.5, "quality": 0.6}))
    assert errors(doc) == []
    assert any(w.startswith("parameters.topup_weights: weights sum to 1.1") for w in warnings(doc))


def test_new_route_warning_only_with_base():
    def add(d):
        d["rules"].insert(I54, {"id": "CAT", "clause": "x", "text": "x",
                                "when": {"all": [{"fact": "category", "op": "eq", "value": "Packaging"}]},
                                "outcome": {"decision": "SOURCING_REQUEST", "route": "CATEGORY_RFQ",
                                            "supplier": {"strategy": "suggest", "count": 3}}})
    doc = edited(add)
    assert not any("new route" in w for w in warnings(doc))
    assert any("new route 'CATEGORY_RFQ'" in w for w in warnings(doc, base=V5))


def test_other_warnings():
    doc = edited(lambda d: d.update(effective_from=None))
    assert errors(doc) == [] and any(w.startswith("effective_from") for w in warnings(doc))
    doc = edited(lambda d: d["rules"][I55]["outcome"].update(decision="MAYBE"))
    assert any("decision 'MAYBE'" in w for w in warnings(doc))
    doc = edited(lambda d: d["parameters"].update(ranking_tie_break=["recency"]))
    assert any("supplier_id is not listed" in w for w in warnings(doc))
    doc = edited(lambda d: d["parameters"].update(consolidate_decisions=[]))
    assert any("no decision receives a PO number" in w for w in warnings(doc))
    doc = edited(lambda d: d["rules"].insert(I55 + 1, copy.deepcopy(d["rules"][I55]) | {"id": "dup"}))
    assert any("identical to" in w for w in warnings(doc))


def test_nested_any_all_and_escaped_dollar_are_valid():
    def add(d):
        d["rules"].insert(I54, {"id": "N", "clause": "x", "text": "x",
                                "when": {"any": [{"all": [{"fact": "plant", "op": "in", "value": ["CHK1"]},
                                                          {"fact": "department", "op": "eq", "value": "$$weird"}]},
                                                 {"fact": "line_count", "op": "gte", "value": 99}]},
                                "outcome": {"decision": "SOURCING_REQUEST", "route": "RFQ",
                                            "supplier": {"strategy": "suggest", "count": "$rfq_suggestion_count"}}})
    doc = edited(add)
    assert errors(doc) == []


def test_errors_are_never_silently_ignored_on_load():
    doc = edited(lambda d: rule_leaf(d, I53, 0).update(values=True))
    with pytest.raises(PolicyValidationError) as exc:
        load_policy(doc)
    assert "unknown key 'values'" in str(exc.value)
