"""Requirement valuation: a registry of price sources walked in the policy's ladder order."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from .models import Valuation
from .money import quantize


def last_po(master, item_code: str, as_of, days: int):
    """Most recent PO for the item from any supplier within `days` before as_of (inclusive)."""
    lo = as_of - timedelta(days=days)
    best = None
    for po in master.po_by_item.get(item_code, ()):
        if lo <= po.po_date <= as_of:
            if best is None or (po.po_date, po.po_number) > (best.po_date, best.po_number):
                best = po
    return best


def _contract(req, master, params, ceval, last):
    if ceval.selected is not None:
        c = ceval.selected
        return c.lines[req.item_code].rate, {"source": "contract", "contract_id": c.contract_id, "selected": True}
    if ceval.applicable:
        c = min(ceval.applicable, key=lambda k: (k.lines[req.item_code].rate, k.contract_id))
        return c.lines[req.item_code].rate, {"source": "contract", "contract_id": c.contract_id, "selected": False}
    return None


def _last_po(req, master, params, ceval, last):
    if last is None:
        return None
    return last.unit_price, {"source": "last_po", "po_number": last.po_number, "po_date": last.po_date.isoformat(),
                             "supplier_id": last.supplier_id}


def _standard_price(req, master, params, ceval, last):
    item = master.items.get(req.item_code)
    if item is None:
        return None
    return item.standard_price, {"source": "standard_price"}


def _requester_estimate(req, master, params, ceval, last):
    est = req.first.estimated_unit_price
    if est is None:
        return None
    return est, {"source": "requester_estimate"}


PRICE_SOURCES = {
    "contract": _contract,
    "last_po": _last_po,
    "standard_price": _standard_price,
    "requester_estimate": _requester_estimate,
}


def value_requirement(req, master, params: dict, ceval, is_new: bool) -> Valuation:
    last = None if is_new else last_po(master, req.item_code, req.requirement_date, params["price_history_days"])
    ladder = [params["new_item_valuation"]] if is_new else list(params["valuation_ladder"])
    for name in ladder:
        got = PRICE_SOURCES[name](req, master, params, ceval, last)
        if got is not None:
            price, ref = got
            return Valuation(name, price, quantize(req.total_qty * price), last, (), ref)
    warning = ("no requester estimate; buyer to value" if is_new
               else "no price source in the valuation ladder; buyer to value")
    return Valuation(None, None, quantize(Decimal(0)), last, (warning,), None)
