"""Generic condition grammar: {fact, op, value} leaves combined with all / any.

Values may be literals or "$param" references ("$$x" is the literal string "$x").
The evaluator knows nothing about any particular rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable


def _ordered(fn):
    def op(actual, expected):
        if actual is None or expected is None:
            return False
        return fn(actual, expected)
    return op


def _in(actual, expected):
    if actual is None:
        return False
    return actual in expected


def _not_in(actual, expected):
    if actual is None:
        return True
    return actual not in expected


OPS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": _ordered(lambda a, b: a < b),
    "lte": _ordered(lambda a, b: a <= b),
    "gt": _ordered(lambda a, b: a > b),
    "gte": _ordered(lambda a, b: a >= b),
    "in": _in,
    "not_in": _not_in,
}

# Fact types each op accepts.
ALL_TYPES = frozenset({"string", "int", "decimal", "bool", "date"})
OP_FACT_TYPES: dict[str, frozenset] = {
    "eq": ALL_TYPES,
    "ne": ALL_TYPES,
    "lt": frozenset({"decimal", "int", "date"}),
    "lte": frozenset({"decimal", "int", "date"}),
    "gt": frozenset({"decimal", "int", "date"}),
    "gte": frozenset({"decimal", "int", "date"}),
    "in": frozenset({"string", "int", "decimal", "bool"}),
    "not_in": frozenset({"string", "int", "decimal", "bool"}),
}
LIST_OPS = frozenset({"in", "not_in"})
GROUP_KEYS = ("all", "any")
LEAF_KEYS = frozenset({"fact", "op", "value"})
PARAM_PREFIX = "$"


def param_name(value) -> str | None:
    """Name of the parameter a value references, or None for a literal."""
    if isinstance(value, str) and value.startswith(PARAM_PREFIX) and not value.startswith(PARAM_PREFIX * 2):
        return value[len(PARAM_PREFIX):]
    return None


def unescape(value):
    if isinstance(value, str) and value.startswith(PARAM_PREFIX * 2):
        return value[len(PARAM_PREFIX):]
    return value


def resolve_value(value, params: dict):
    name = param_name(value)
    if name is not None:
        return params[name]
    return unescape(value)


def coerce_scalar(value, fact_type: str):
    """Convert a validated JSON value to the fact's Python type."""
    if value is None:
        return None
    if fact_type == "decimal":
        return value if isinstance(value, Decimal) else Decimal(str(value))
    if fact_type == "int":
        return int(value)
    if fact_type == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    return value


def coerce(value, fact_type: str, op: str):
    if op in LIST_OPS:
        return tuple(coerce_scalar(v, fact_type) for v in value)
    return coerce_scalar(value, fact_type)


def jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class Leaf:
    fact: str
    op: str
    raw: Any                 # the value as written in the JSON
    resolved: Any            # coerced to the fact type


@dataclass(frozen=True)
class Group:
    kind: str                # "all" or "any"
    children: tuple


def compile_node(node: dict, params: dict, fact_types: dict):
    """Turn a validated JSON condition into Leaf / Group objects with coerced values."""
    for kind in GROUP_KEYS:
        if kind in node:
            return Group(kind, tuple(compile_node(c, params, fact_types) for c in node[kind]))
    raw = node["value"]
    value = resolve_value(raw, params)
    return Leaf(node["fact"], node["op"], raw, coerce(value, fact_types[node["fact"]], node["op"]))


def evaluate(node, get_fact: Callable[[str], Any]) -> tuple[bool, dict]:
    """Evaluate every child (no short-circuit) so the trace shows each condition."""
    if isinstance(node, Group):
        results = [evaluate(c, get_fact) for c in node.children]
        flags = [r[0] for r in results]
        passed = all(flags) if node.kind == "all" else any(flags)
        return passed, {node.kind: [r[1] for r in results], "passed": passed}
    actual = get_fact(node.fact)
    passed = bool(OPS[node.op](actual, node.resolved))
    return passed, {
        "fact": node.fact, "op": node.op, "value": jsonable(node.raw),
        "resolved": jsonable(node.resolved), "actual": jsonable(actual), "passed": passed,
    }


def leaves(node):
    if isinstance(node, Group):
        for c in node.children:
            yield from leaves(c)
    else:
        yield node
