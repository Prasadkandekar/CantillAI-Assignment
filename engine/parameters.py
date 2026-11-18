"""Type and range rules for the parameters the engine reads.

PARAM_RULES maps a parameter name to its rule. REQUIRED_PARAMETERS are the ones the
pipeline itself reads, so every policy must define them. Facts that need a parameter
register its rule here next to the fact (see facts.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from .clubbing import CLUB_KEY_FIELDS
from .consolidation import CONSOLIDATION_KEY_FIELDS
from .ranking import RANKING_FACTORS, TIE_BREAK_KEYS, TOPUP_FACTORS
from .valuation import PRICE_SOURCES


def json_type(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, (float, Decimal)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def describe(v) -> str:
    if isinstance(v, str):
        return f"string '{v}'"
    if v is None:
        return "null"
    return f"{json_type(v)} {v!r}" if not isinstance(v, (int, float, Decimal)) or isinstance(v, bool) else f"{v}"


def is_number(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


@dataclass(frozen=True)
class ParamRule:
    expect: str
    check: Callable[[Any, dict], str | None]   # returns an extra detail on failure, "" for plain failure

    def problem(self, value, params: dict) -> str | None:
        detail = self.check(value, params)
        if detail is None:
            return None
        msg = f"must be {self.expect}; got {describe(value)}"
        return f"{msg} ({detail})" if detail else msg


def _ok(cond: bool, detail: str = "") -> str | None:
    return None if cond else detail


def int_min(minimum: int) -> ParamRule:
    return ParamRule(f"an integer >= {minimum}", lambda v, p: _ok(is_int(v) and v >= minimum))


def int_gt(bound: int) -> ParamRule:
    return ParamRule(f"an integer > {bound}", lambda v, p: _ok(is_int(v) and v > bound))


def number_min(minimum) -> ParamRule:
    return ParamRule(f"a number >= {minimum}", lambda v, p: _ok(is_number(v) and Decimal(str(v)) >= minimum))


def number_gt(bound) -> ParamRule:
    return ParamRule(f"a number > {bound}", lambda v, p: _ok(is_number(v) and Decimal(str(v)) > bound))


BOOL = ParamRule("true or false", lambda v, p: _ok(isinstance(v, bool)))


def _distinct(items, key=lambda x: x) -> bool:
    keys = [key(x) for x in items]
    return len(keys) == len(set(keys))


def string_list(*, allowed=None, non_empty=False, case_insensitive=False, subset_of=None) -> ParamRule:
    parts = ["a non-empty" if non_empty else "a", "list of distinct strings"]
    if allowed is not None:
        parts.append("from " + ", ".join(sorted(allowed)))
    if subset_of:
        parts.append(f"each also in {subset_of}")
    expect = " ".join(parts)

    def check(v, params):
        if not isinstance(v, list) or (non_empty and not v):
            return ""
        if not all(isinstance(x, str) and x.strip() for x in v):
            return ""
        if not _distinct(v, (lambda x: x.lower()) if case_insensitive else (lambda x: x)):
            return "duplicates"
        if allowed is not None:
            bad = [x for x in v if x not in allowed]
            if bad:
                return "unknown " + ", ".join(f"'{b}'" for b in bad)
        if subset_of:
            other = params.get(subset_of)
            if isinstance(other, list):
                bad = [x for x in v if x not in other]
                if bad:
                    return f"not in {subset_of}: " + ", ".join(f"'{b}'" for b in bad)
        return None

    return ParamRule(expect, check)


def one_of(allowed) -> ParamRule:
    return ParamRule("one of " + ", ".join(sorted(allowed)), lambda v, p: _ok(isinstance(v, str) and v in allowed))


def weights(keys) -> ParamRule:
    names = ", ".join(sorted(keys))

    def check(v, params):
        if not isinstance(v, dict):
            return ""
        missing = sorted(set(keys) - set(v))
        extra = sorted(set(v) - set(keys))
        if missing or extra:
            return "; ".join(filter(None, [
                "missing " + ", ".join(f"'{m}'" for m in missing) if missing else "",
                "unknown " + ", ".join(f"'{e}'" for e in extra) if extra else ""]))
        if not all(is_number(x) and Decimal(str(x)) >= 0 for x in v.values()):
            return "each weight must be a number >= 0"
        if sum(Decimal(str(x)) for x in v.values()) <= 0:
            return "weights must sum to more than 0"
        return None

    return ParamRule(f"an object with exactly the keys {names}", check)


def ladder() -> ParamRule:
    allowed = set(PRICE_SOURCES) - {"requester_estimate"}
    return string_list(allowed=allowed, non_empty=True)


PARAM_RULES: dict[str, ParamRule] = {
    "club_keys": string_list(allowed=CLUB_KEY_FIELDS, non_empty=True),
    "club_created_days": int_min(0),
    "club_needby_days": int_min(0),
    "club_new_items": BOOL,
    "urgency_values": string_list(non_empty=True, case_insensitive=True),
    "emergency_urgency_values": string_list(subset_of="urgency_values"),
    "valuation_ladder": ladder(),
    "new_item_valuation": one_of(set(PRICE_SOURCES)),
    "price_history_days": int_min(0),
    "eligible_supplier_statuses": string_list(non_empty=True),
    "preferred_history_days": int_min(0),
    "ranking_weights": weights(RANKING_FACTORS),
    "ranking_recency_decay_days": int_gt(0),
    "ranking_tie_break": string_list(allowed=TIE_BREAK_KEYS),
    "on_time_pct_scale": number_gt(0),
    "quality_rating_scale": number_gt(0),
    "topup_weights": weights(TOPUP_FACTORS),
    "preferred_export_count": int_min(1),
    "consolidate_decisions": string_list(),
    "consolidation_keys": string_list(allowed=CONSOLIDATION_KEY_FIELDS, non_empty=True),
    "consolidation_hours": number_min(0),
}

REQUIRED_PARAMETERS: frozenset = frozenset(PARAM_RULES)

SUGGESTION_COUNT_RULE = int_min(1)
