"""SQLAlchemy models. Timestamps are stored in UTC; the UI shows IST."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, event, inspect)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from .base import Base

JSONType = JSON().with_variant(JSONB, "postgresql")
Money = Numeric(18, 2)
Rate = Numeric(18, 4)

DRAFT, ACTIVE, SUPERSEDED, DISCARDED = "DRAFT", "ACTIVE", "SUPERSEDED", "DISCARDED"
APPROVED_STATUSES = (ACTIVE, SUPERSEDED)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ImmutablePolicyError(RuntimeError):
    """An approved policy version may not be edited or deleted."""


class Plant(Base):
    __tablename__ = "plants"
    plant: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))


class Item(Base):
    __tablename__ = "items"
    item_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(String(256))
    uom: Mapped[str] = mapped_column(String(16))
    category: Mapped[str] = mapped_column(String(128))
    item_type: Mapped[str] = mapped_column(String(32))
    standard_price: Mapped[object] = mapped_column(Rate)


class Supplier(Base):
    __tablename__ = "suppliers"
    supplier_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    city: Mapped[str] = mapped_column(String(64))
    categories: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    on_time_pct: Mapped[object] = mapped_column(Numeric(8, 2))
    quality_rating: Mapped[object] = mapped_column(Numeric(8, 2))


class POHistory(Base):
    __tablename__ = "po_history"
    po_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    po_date: Mapped[object] = mapped_column(Date)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.supplier_id"))
    item_code: Mapped[str] = mapped_column(ForeignKey("items.item_code"))
    quantity: Mapped[object] = mapped_column(Rate)
    uom: Mapped[str] = mapped_column(String(16))
    unit_price: Mapped[object] = mapped_column(Rate)
    plant: Mapped[str] = mapped_column(String(16))
    delivered_on_time: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (Index("ix_po_history_item_date", "item_code", "po_date"),)


class Contract(Base):
    __tablename__ = "contracts"
    contract_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.supplier_id"))
    supplier_name: Mapped[str] = mapped_column(String(128), default="")
    start_date: Mapped[object] = mapped_column(Date)
    end_date: Mapped[object] = mapped_column(Date)
    value_cap: Mapped[object] = mapped_column(Money)
    consumed_value: Mapped[object] = mapped_column(Money, default=0)
    source: Mapped[str] = mapped_column(String(16), default="REGISTER")
    pdf_filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    warnings: Mapped[list | None] = mapped_column(JSONType, nullable=True)


class ContractLine(Base):
    __tablename__ = "contract_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id", ondelete="CASCADE"))
    item_code: Mapped[str] = mapped_column(ForeignKey("items.item_code"))
    description: Mapped[str] = mapped_column(String(256), default="")
    uom: Mapped[str] = mapped_column(String(16), default="")
    rate: Mapped[object] = mapped_column(Rate)
    __table_args__ = (UniqueConstraint("contract_id", "item_code"), Index("ix_contract_lines_item", "item_code"))


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_label: Mapped[str] = mapped_column(String(20), unique=True)
    status: Mapped[str] = mapped_column(String(16), default=DRAFT)
    effective_from: Mapped[object | None] = mapped_column(Date, nullable=True)
    document: Mapped[dict] = mapped_column(JSONType)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    base_version_id: Mapped[int | None] = mapped_column(ForeignKey("policy_versions.id"), nullable=True)
    validation: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(256), default="")
    source: Mapped[str] = mapped_column(String(16), default="CSV")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(64), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PRLine(Base):
    """The uploaded row as text, exactly as received, so later runs (dry run, chat preview) can replay it."""
    __tablename__ = "pr_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"))
    row_index: Mapped[int] = mapped_column(Integer)
    pr_no: Mapped[str] = mapped_column(String(64), default="")
    pr_line: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    requester: Mapped[str] = mapped_column(String(128), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    plant: Mapped[str] = mapped_column(String(32), default="")
    item_code: Mapped[str] = mapped_column(String(32), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[str] = mapped_column(String(32), default="")
    uom: Mapped[str] = mapped_column(String(16), default="")
    estimated_unit_price: Mapped[str] = mapped_column(String(32), default="")
    need_by_date: Mapped[str] = mapped_column(String(32), default="")
    urgency: Mapped[str] = mapped_column(String(32), default="")
    __table_args__ = (UniqueConstraint("batch_id", "row_index"),)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    pin_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    as_of: Mapped[object | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    versions_used: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    counts: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="BATCH")
    __table_args__ = (Index("ix_runs_batch", "batch_id"),)


class RunRow(Base):
    __tablename__ = "run_rows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    pr_no: Mapped[str] = mapped_column(String(64), default="")
    pr_line: Mapped[str] = mapped_column(String(16), default="")
    resolved_item_code: Mapped[str] = mapped_column(String(32), default="")
    group_id: Mapped[str] = mapped_column(String(32), default="")
    po_id: Mapped[str] = mapped_column(String(32), default="")
    decision: Mapped[str] = mapped_column(String(32), default="")
    route: Mapped[str] = mapped_column(String(64), default="")
    supplier_id: Mapped[str] = mapped_column(String(16), default="")
    unit_price: Mapped[str] = mapped_column(String(32), default="")
    group_value_inr: Mapped[str] = mapped_column(String(32), default="")
    suggested_supplier_ids: Mapped[str] = mapped_column(String(256), default="")
    policy_version: Mapped[str] = mapped_column(String(20), default="")
    reason: Mapped[str] = mapped_column(Text, default="")


class Requirement(Base):
    __tablename__ = "requirements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[str] = mapped_column(String(32))
    item_code: Mapped[str] = mapped_column(String(32))
    plant: Mapped[str] = mapped_column(String(16))
    requirement_date: Mapped[object] = mapped_column(Date)
    first_created_at: Mapped[datetime] = mapped_column(DateTime)
    total_qty: Mapped[object] = mapped_column(Rate)
    value: Mapped[object | None] = mapped_column(Money, nullable=True)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_version_id: Mapped[int | None] = mapped_column(ForeignKey("policy_versions.id"), nullable=True)
    line_ids: Mapped[list] = mapped_column(JSONType)
    lines: Mapped[list | None] = mapped_column(JSONType, nullable=True)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16), default="ENGINE")
    overrides_decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    route: Mapped[str] = mapped_column(String(64))
    supplier_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    unit_price: Mapped[object | None] = mapped_column(Rate, nullable=True)
    suggested: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    po_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contract_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    debit: Mapped[object | None] = mapped_column(Money, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    trace: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="engine")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (Index("ix_decisions_requirement", "requirement_id"),)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(16))
    route: Mapped[str] = mapped_column(String(64))
    supplier_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    plant: Mapped[str] = mapped_column(String(16))
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("run_id", "order_no"),)


class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"))
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"))
    quantity: Mapped[object] = mapped_column(Rate)
    unit_price: Mapped[object | None] = mapped_column(Rate, nullable=True)
    contract_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ContractConsumption(Base):
    __tablename__ = "contract_consumption"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(String(32), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"))
    value: Mapped[object] = mapped_column(Money)
    requirement_date: Mapped[object] = mapped_column(Date)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user: Mapped[str] = mapped_column(String(64))
    state: Mapped[dict] = mapped_column(JSONType)
    messages: Mapped[list] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Conversation(Base):
    """A saved chat shown in the sidebar history; owned by one user (email or X-User name)."""
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_owner_updated", "owner", "updated_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(120))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_sessions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_conv_messages_conv", "conversation_id", "id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    who: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict | list | None] = mapped_column(JSONType, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)


# --- immutability of approved policy versions ---------------------------------

_PROTECTED = ("document", "effective_from", "version_label")


def _committed_status(obj) -> str | None:
    hist = inspect(obj).attrs.status.history
    if hist.deleted:
        return hist.deleted[0]
    if hist.unchanged:
        return hist.unchanged[0]
    return obj.status


@event.listens_for(Session, "before_flush")
def _protect_policy_versions(session, flush_context, instances):
    for obj in session.dirty:
        if not isinstance(obj, PolicyVersion) or not session.is_modified(obj):
            continue
        status = _committed_status(obj)
        if status == DRAFT:
            continue
        state = inspect(obj)
        changed = [name for name in _PROTECTED if state.attrs[name].history.has_changes()]
        if changed:
            raise ImmutablePolicyError(
                f"Policy version {obj.version_label} is {status} and cannot be changed ({', '.join(changed)})")
    for obj in session.deleted:
        if isinstance(obj, PolicyVersion) and _committed_status(obj) in APPROVED_STATUSES:
            raise ImmutablePolicyError(f"Policy version {obj.version_label} is approved and cannot be deleted")
