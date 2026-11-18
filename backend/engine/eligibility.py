"""The single supplier-status check (supplier eligibility filter).

Every place that can put a supplier on a PO or a suggestion list goes through here.
"""
from __future__ import annotations


def is_eligible(supplier, params: dict) -> bool:
    if supplier is None:
        return False
    return supplier.status in params["eligible_supplier_statuses"]


def is_eligible_id(supplier_id: str | None, master, params: dict) -> bool:
    if not supplier_id:
        return False
    return is_eligible(master.suppliers.get(supplier_id), params)
