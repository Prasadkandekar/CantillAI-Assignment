"""Supplier strategies a rule outcome can name."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .contracts import contract_cost
from .models import StrategyResult
from .ranking import suggestions


@dataclass(frozen=True)
class StrategyDef:
    fn: Callable
    count: str              # "required" or "forbidden"
    gives_supplier: bool    # True when a fulfilled result always names one supplier


def _contract(ctx, count):
    sel = ctx.contract_eval.selected
    if sel is None:
        return StrategyResult(False, reason="no applicable contract has enough ceiling left")
    item = ctx.requirement.item_code
    rate = sel.lines[item].rate
    return StrategyResult(
        True, supplier_id=sel.supplier_id, unit_price=rate, contract_id=sel.contract_id,
        debit=contract_cost(ctx.requirement.total_qty, sel, item),
        reference={"source": "contract", "contract_id": sel.contract_id},
        reason=f"contract {sel.contract_id} supplier {sel.supplier_id} at contract rate {rate}")


def _preferred_first(ctx, count):
    pl = ctx.preferred()
    if not pl:
        return StrategyResult(False, reason="no eligible supplier on the preferred list")
    top = pl[0]
    return StrategyResult(True, supplier_id=top.supplier_id, unit_price=top.reference_price,
                          reference=dict(top.reference),
                          reason=f"1st preferred supplier {top.supplier_id} at reference price {top.reference_price}")


def _suggest(ctx, count):
    req = ctx.requirement
    ids, topped = suggestions(req.item_code, req.requirement_date, ctx.master, ctx.params, count,
                              preferred=ctx.preferred())
    reason = f"suggested {len(ids)} of {count}"
    if topped:
        reason += f" (category top-up: {', '.join(topped)})"
    return StrategyResult(True, suggested=tuple(ids), reason=reason,
                          reference={"source": "suggestions", "topped_up": list(topped)})


def _none(ctx, count):
    return StrategyResult(True, reason="no supplier selected")


STRATEGIES: dict[str, StrategyDef] = {
    "contract": StrategyDef(_contract, "forbidden", True),
    "preferred_first": StrategyDef(_preferred_first, "forbidden", True),
    "suggest": StrategyDef(_suggest, "required", False),
    "none": StrategyDef(_none, "forbidden", False),
}
