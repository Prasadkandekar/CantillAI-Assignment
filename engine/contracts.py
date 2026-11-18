"""Contract applicability, ceiling ledger and selection."""
from __future__ import annotations

from decimal import Decimal

from .eligibility import is_eligible
from .models import ContractEval
from .money import quantize


class ContractLedger:
    """Consumed value per contract. Register contracts start at their consumed value,
    contracts known only from a PDF start at the value stored for them (zero when seeded)."""

    def __init__(self, contracts: dict):
        self._contracts = contracts
        self.consumed: dict[str, Decimal] = {cid: c.consumed_value for cid, c in contracts.items()}
        self.debits: list[tuple[str, str, Decimal]] = []

    def remaining(self, contract_id: str) -> Decimal:
        return quantize(self._contracts[contract_id].value_cap - self.consumed[contract_id])

    def debit(self, contract_id: str, amount: Decimal, group_id: str = "") -> None:
        self.consumed[contract_id] += amount
        self.debits.append((contract_id, group_id, amount))


def contract_cost(qty: Decimal, contract, item_code: str) -> Decimal:
    return quantize(qty * contract.lines[item_code].rate)


def evaluate_contracts(requirement, master, params: dict, ledger: ContractLedger) -> ContractEval:
    item = requirement.item_code
    d = requirement.requirement_date
    applicable, skipped = [], []
    for c in master.contracts_by_item.get(item, ()):
        supplier = master.suppliers.get(c.supplier_id)
        if not is_eligible(supplier, params):
            status = supplier.status if supplier else "unknown"
            skipped.append((c, f"supplier {c.supplier_id} status {status}"))
        elif not (c.start_date <= d <= c.end_date):
            skipped.append((c, f"not valid on {d.isoformat()} (valid {c.start_date.isoformat()} to {c.end_date.isoformat()})"))
        else:
            applicable.append(c)
    remaining = {c.contract_id: ledger.remaining(c.contract_id) for c in applicable}
    fitting = [c for c in applicable
               if ledger.consumed[c.contract_id] + contract_cost(requirement.total_qty, c, item) <= c.value_cap]
    selected = min(fitting, key=lambda c: (c.lines[item].rate, c.contract_id)) if fitting else None
    return ContractEval(tuple(applicable), tuple(skipped), tuple(fitting), selected, remaining)
