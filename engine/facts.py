"""Fact registry: fact name -> function computing it for a requirement.

Adding a fact is one decorated function. A fact that needs a parameter names it in
`params`; if the parameter is new, register its rule with `PARAM_RULES` next to the fact.
No window, limit or count appears here: they all come from ctx.params.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from .eligibility import is_eligible
from .models import NEW_ITEM
from .parameters import PARAM_RULES, int_min
from .ranking import build_preferred_list

FACT_TYPES = ("string", "int", "decimal", "bool", "date")


@dataclass(frozen=True)
class FactDef:
    fn: Callable
    type: str
    params: tuple
    label: str


FACTS: dict[str, FactDef] = {}


def fact(name: str, *, type: str, params=(), label: str = ""):
    assert type in FACT_TYPES, type

    def deco(fn):
        FACTS[name] = FactDef(fn, type, tuple(params), label or name.replace("_", " "))
        return fn
    return deco


class FactContext:
    """Everything a fact may read for one requirement. Facts are memoised."""

    def __init__(self, requirement, master, params, contract_eval, valuation):
        self.requirement = requirement
        self.master = master
        self.params = params
        self.contract_eval = contract_eval
        self.valuation = valuation
        self.cache: dict = {}
        self._preferred = None

    @property
    def item(self):
        return self.master.items.get(self.requirement.item_code)

    def preferred(self):
        if self._preferred is None:
            self._preferred = build_preferred_list(
                self.requirement.item_code, self.requirement.requirement_date, self.master, self.params)
        return self._preferred

    def fact(self, name: str):
        if name not in self.cache:
            self.cache[name] = FACTS[name].fn(self)
        return self.cache[name]


# --- item -------------------------------------------------------------------

@fact("item_code", type="string", label="Item code")
def item_code(ctx):
    return ctx.requirement.item_code


@fact("is_new_item", type="bool", label="New item (no item master match)")
def is_new_item(ctx):
    return ctx.requirement.item_code == NEW_ITEM


@fact("item_type", type="string", label="Item type")
def item_type(ctx):
    return ctx.item.item_type if ctx.item else None


@fact("category", type="string", label="Item category")
def category(ctx):
    return ctx.item.category if ctx.item else None


@fact("uom", type="string", label="Unit of measure")
def uom(ctx):
    return ctx.item.uom if ctx.item else ctx.requirement.uom


# --- requirement ----------------------------------------------------------------

@fact("plant", type="string", label="Plant")
def plant(ctx):
    return ctx.requirement.plant


@fact("is_emergency", type="bool", params=("emergency_urgency_values",), label="Emergency requirement")
def is_emergency(ctx):
    values = ctx.params["emergency_urgency_values"]
    return any(l.urgency in values for l in ctx.requirement.lines)


@fact("urgency", type="string", params=("emergency_urgency_values",), label="Urgency")
def urgency(ctx):
    values = ctx.params["emergency_urgency_values"]
    for v in values:
        if any(l.urgency == v for l in ctx.requirement.lines):
            return v
    return ctx.requirement.first.urgency


@fact("group_value", type="decimal", label="Requirement value (INR)")
def group_value(ctx):
    return ctx.valuation.value


@fact("value_source", type="string", label="Price source used for the value")
def value_source(ctx):
    return ctx.valuation.source


@fact("total_quantity", type="decimal", label="Total quantity")
def total_quantity(ctx):
    return ctx.requirement.total_qty


@fact("line_count", type="int", label="Number of PR lines")
def line_count(ctx):
    return len(ctx.requirement.lines)


@fact("requirement_date", type="date", label="Requirement date")
def requirement_date(ctx):
    return ctx.requirement.requirement_date


@fact("need_by_lead_days", type="int", label="Days from requirement date to earliest need-by")
def need_by_lead_days(ctx):
    return (ctx.requirement.earliest_need_by - ctx.requirement.requirement_date).days


@fact("department", type="string", label="Department")
def department(ctx):
    return ctx.requirement.first.department


@fact("requester", type="string", label="Requester")
def requester(ctx):
    return ctx.requirement.first.requester


# --- contracts --------------------------------------------------------------------

@fact("contract_exists", type="bool", params=("eligible_supplier_statuses",), label="An applicable contract exists")
def contract_exists(ctx):
    return bool(ctx.contract_eval.applicable)


@fact("contract_usable", type="bool", params=("eligible_supplier_statuses",), label="A contract can be used (has ceiling)")
def contract_usable(ctx):
    return ctx.contract_eval.selected is not None


@fact("contract_remaining_ceiling", type="decimal", label="Contract ceiling left before this requirement (INR)")
def contract_remaining_ceiling(ctx):
    ce = ctx.contract_eval
    if ce.selected is not None:
        return ce.remaining_by_contract[ce.selected.contract_id]
    if ce.remaining_by_contract:
        return max(ce.remaining_by_contract.values())
    return None


# --- history ----------------------------------------------------------------------

PARAM_RULES.setdefault("bought_history_days", int_min(0))


@fact("bought_from_active_365d", type="bool", params=("bought_history_days", "eligible_supplier_statuses"),
      label="Bought from an eligible supplier within the bought-history window")
def bought_from_active_365d(ctx):
    req = ctx.requirement
    lo = req.requirement_date - timedelta(days=ctx.params["bought_history_days"])
    for po in ctx.master.po_by_item.get(req.item_code, ()):
        if lo <= po.po_date <= req.requirement_date and is_eligible(ctx.master.suppliers.get(po.supplier_id), ctx.params):
            return True
    return False


@fact("last_po_price", type="decimal", params=("price_history_days",), label="Last PO price within the price-history window")
def last_po_price(ctx):
    po = ctx.valuation.last_po
    return po.unit_price if po else None


# --- preferred suppliers ----------------------------------------------------------

@fact("preferred_list_size", type="int", params=("preferred_history_days",), label="Suppliers on the preferred list")
def preferred_list_size(ctx):
    return len(ctx.preferred())


@fact("top_supplier_on_time_pct", type="decimal", params=("preferred_history_days",), label="On-time % of the 1st preferred supplier")
def top_supplier_on_time_pct(ctx):
    pl = ctx.preferred()
    return ctx.master.suppliers[pl[0].supplier_id].on_time_pct if pl else None


@fact("top_supplier_quality", type="decimal", params=("preferred_history_days",), label="Quality rating of the 1st preferred supplier")
def top_supplier_quality(ctx):
    pl = ctx.preferred()
    return ctx.master.suppliers[pl[0].supplier_id].quality_rating if pl else None
