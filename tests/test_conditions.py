"""Generic condition evaluator: ops, None semantics, nesting, $param and $$ literals."""
from datetime import date
from decimal import Decimal

import pytest

from engine.conditions import OPS, compile_node, evaluate

TYPES = {"v": "decimal", "n": "int", "s": "string", "b": "bool", "d": "date", "missing": "decimal"}


def ev(node, facts, params=None):
    compiled = compile_node(node, params or {}, TYPES)
    return evaluate(compiled, lambda name: facts.get(name))


FACTS = {"v": Decimal("200000.00"), "n": 3, "s": "CHK1", "b": True, "d": date(2026, 11, 5), "missing": None}


@pytest.mark.parametrize("op,value,expected", [
    ("eq", 200000, True), ("ne", 200000, False), ("lt", 200000, False), ("lte", 200000, True),
    ("gt", 199999.99, True), ("gte", 200000.01, False),
])
def test_decimal_ops(op, value, expected):
    assert ev({"fact": "v", "op": op, "value": value}, FACTS)[0] is expected


def test_membership_ops():
    assert ev({"fact": "s", "op": "in", "value": ["CHK1", "PUN1"]}, FACTS)[0] is True
    assert ev({"fact": "s", "op": "not_in", "value": ["CHK1"]}, FACTS)[0] is False
    assert ev({"fact": "n", "op": "in", "value": [1, 3]}, FACTS)[0] is True


def test_date_compare_from_iso_string():
    assert ev({"fact": "d", "op": "gte", "value": "2026-11-01"}, FACTS)[0] is True
    assert ev({"fact": "d", "op": "lt", "value": "2026-11-05"}, FACTS)[0] is False


@pytest.mark.parametrize("op,value,expected", [
    ("lt", 1, False), ("lte", 1, False), ("gt", 1, False), ("gte", 1, False),
    ("eq", None, True), ("ne", 1, True), ("in", [1], False), ("not_in", [1], True),
])
def test_none_semantics(op, value, expected):
    passed, trace = ev({"fact": "missing", "op": op, "value": value}, FACTS)
    assert passed is expected
    assert trace["actual"] is None


def test_nested_all_any_without_short_circuit():
    node = {"all": [{"fact": "b", "op": "eq", "value": False},
                    {"any": [{"fact": "s", "op": "eq", "value": "PUN1"}, {"fact": "n", "op": "gte", "value": 3}]}]}
    passed, trace = ev(node, FACTS)
    assert passed is False
    assert len(trace["all"]) == 2                     # second child evaluated although the first failed
    assert trace["all"][1]["passed"] is True
    assert [c["passed"] for c in trace["all"][1]["any"]] == [False, True]


def test_param_reference_and_trace():
    passed, trace = ev({"fact": "v", "op": "lt", "value": "$limit"}, FACTS, {"limit": 300000})
    assert passed is True
    assert trace["value"] == "$limit" and trace["resolved"] == "300000" and trace["actual"] == "200000.00"


def test_param_list_reference():
    assert ev({"fact": "s", "op": "not_in", "value": "$plants"}, FACTS, {"plants": ["PUN1"]})[0] is True


def test_double_dollar_is_a_literal():
    assert ev({"fact": "s", "op": "eq", "value": "$$CHK1"}, {"s": "$CHK1"})[0] is True


def test_ops_registry_is_exactly_the_eight():
    assert set(OPS) == {"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in"}
