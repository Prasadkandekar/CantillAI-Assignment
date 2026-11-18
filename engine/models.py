"""Engine data classes. Money and quantities are Decimal; timestamps are naive IST."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

OUTPUT_COLUMNS = (
    "pr_no", "pr_line", "resolved_item_code", "group_id", "po_id", "decision", "route",
    "supplier_id", "unit_price", "group_value_inr", "suggested_supplier_ids",
    "policy_version", "reason",
)

NEW_ITEM = "NEW"
NOT_PROCESSED = "NOT_PROCESSED"


class EngineInvariantError(RuntimeError):
    """A bug: the engine produced something the policy forbids."""


@dataclass(frozen=True)
class RawLine:
    row_index: int
    values: dict


@dataclass(frozen=True)
class MatchResult:
    code: str | None
    score: Decimal | None = None
    candidates: tuple = ()
    method: str = "none"          # code / auto / none
    flags: tuple = ()             # note flags found in the text


@dataclass(frozen=True)
class PRLine:
    row_index: int
    pr_no: str
    pr_line: int
    created_at: datetime
    requester: str | None
    department: str | None
    plant: str
    item_code_raw: str | None
    description: str
    quantity: Decimal
    uom: str
    estimated_unit_price: Decimal | None
    need_by: date
    urgency: str
    policy_version: str
    resolved_item_code: str
    match: MatchResult
    flags: tuple = ()

    @property
    def key(self) -> str:
        return f"{self.pr_no}/{self.pr_line}"


@dataclass(frozen=True)
class Item:
    item_code: str
    description: str
    uom: str
    category: str
    item_type: str
    standard_price: Decimal


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    city: str
    categories: tuple
    status: str
    on_time_pct: Decimal
    quality_rating: Decimal


@dataclass(frozen=True)
class PORecord:
    po_number: str
    po_date: date
    supplier_id: str
    item_code: str
    quantity: Decimal
    uom: str
    unit_price: Decimal
    plant: str
    delivered_on_time: bool


@dataclass(frozen=True)
class ContractLine:
    contract_id: str
    item_code: str
    description: str
    uom: str
    rate: Decimal


@dataclass(frozen=True)
class Contract:
    contract_id: str
    supplier_id: str
    supplier_name: str
    start_date: date
    end_date: date
    value_cap: Decimal
    consumed_value: Decimal
    source: str                    # REGISTER / PDF
    lines: dict                    # item_code -> ContractLine


@dataclass(frozen=True)
class MasterData:
    plants: dict
    items: dict
    suppliers: dict
    po_by_item: dict               # item_code -> tuple[PORecord] sorted by (po_date, po_number)
    contracts: dict
    contracts_by_item: dict        # item_code -> tuple[Contract]


@dataclass(frozen=True)
class Requirement:
    group_id: str
    lines: tuple
    item_code: str
    plant: str
    uom: str
    requirement_date: date
    first_created_at: datetime
    earliest_need_by: date
    total_qty: Decimal
    policy_version: str

    @property
    def first(self) -> PRLine:
        return self.lines[0]


@dataclass(frozen=True)
class ContractEval:
    applicable: tuple = ()
    skipped: tuple = ()            # (Contract, reason)
    fitting: tuple = ()
    selected: Contract | None = None
    remaining_by_contract: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Valuation:
    source: str | None
    unit_price: Decimal | None
    value: Decimal
    last_po: PORecord | None
    warnings: tuple = ()
    reference: dict | None = None


@dataclass(frozen=True)
class FactorContribution:
    raw: Any
    scaled: Decimal
    weight: Decimal
    contribution: Decimal


@dataclass(frozen=True)
class RankedSupplier:
    supplier_id: str
    rank: int
    score: Decimal
    factors: dict
    reference_price: Decimal | None
    reference: dict
    po_count: int
    last_po_date: date | None
    has_contract: bool


@dataclass(frozen=True)
class StrategyResult:
    fulfilled: bool
    supplier_id: str | None = None
    unit_price: Decimal | None = None
    suggested: tuple = ()
    reference: dict | None = None
    contract_id: str | None = None
    debit: Decimal | None = None
    reason: str = ""


@dataclass
class Decision:
    group_id: str
    policy_version: str
    fired_rule: dict | None
    decision: str | None
    route: str
    supplier_id: str | None
    unit_price: Decimal | None
    suggested: tuple
    contract_id: str | None
    reason: str
    trace: dict
    value: Decimal | None = None
    po_id: str | None = None
    debit: Decimal | None = None


@dataclass(frozen=True)
class OutputRow:
    pr_no: str
    pr_line: str
    resolved_item_code: str
    group_id: str
    po_id: str
    decision: str
    route: str
    supplier_id: str
    unit_price: str
    group_value_inr: str
    suggested_supplier_ids: str
    policy_version: str
    reason: str

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in OUTPUT_COLUMNS}


@dataclass
class BatchResult:
    rows: list
    requirements: list
    decisions: dict
    versions_used: dict
    warnings: list
    counts: dict                                   # route -> number of output rows
    requirement_counts: dict = field(default_factory=dict)   # route -> number of requirements
    rejected: list = field(default_factory=list)
    ledger: dict = field(default_factory=dict)     # contract_id -> consumed value after the run
