"""Shared test helpers. They use only the engine's public API."""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from engine import load_batch, load_master, load_policy, raw_line, run_batch, validate_or_raise
from engine.paths import kit_root

BACKEND = Path(__file__).resolve().parent.parent
ROOT = kit_root()
POLICY_PATH = BACKEND / "engine" / "policies" / "policy_v5_0.json"
BATCH_PATH = ROOT / "pr_batches" / "sample_pr_batch.csv"
PDF_CONTRACTS = BACKEND / "seed" / "pdf_contracts.json"
BLOCKED_OR_INACTIVE = ("S004", "S008", "S011", "S031", "S034")
COMPARED_FIELDS = ("decision", "route", "supplier_id", "unit_price", "group_value_inr", "suggested_supplier_ids")


@lru_cache(maxsize=None)
def _doc_text() -> str:
    return POLICY_PATH.read_text(encoding="utf-8")


def load_doc() -> dict:
    return json.loads(_doc_text())


@lru_cache(maxsize=None)
def master_data():
    return load_master(ROOT, PDF_CONTRACTS)


@lru_cache(maxsize=None)
def _sample():
    return tuple(load_batch(BATCH_PATH))


def sample_lines() -> list:
    return list(_sample())


def line(pr_no, created_at, plant, item_code, quantity, uom, need_by, urgency="Normal", pr_line=1,
         description="", estimated_unit_price="", department="", requester="", row_index=0):
    return dict(pr_no=pr_no, pr_line=str(pr_line), created_at=created_at, requester=requester,
                department=department, plant=plant, item_code=item_code, description=description,
                quantity=str(quantity), uom=uom, estimated_unit_price=str(estimated_unit_price),
                need_by_date=need_by, urgency=urgency)


def as_raw(dicts, start=0):
    return [raw_line(d, start + i) for i, d in enumerate(dicts)]


def run(doc, extra=(), *, include_sample=True, pin=None, as_of=None, validate=True):
    """Validate the doc, then run the sample batch (plus extra synthetic line dicts)."""
    if validate:
        validate_or_raise(doc)
    policy = load_policy(copy.deepcopy(doc))
    lines = sample_lines() if include_sample else []
    lines += as_raw(extra, start=len(lines))
    return run_batch(lines, master_data(), [policy], pin=pin, as_of=as_of)


def key(row) -> str:
    return f"{row.pr_no}/{row.pr_line}"


def by_key(result) -> dict:
    return {key(r): r for r in result.rows}


def membership(result) -> dict:
    groups: dict[str, set] = {}
    for r in result.rows:
        if r.group_id:
            groups.setdefault(r.group_id, set()).add(key(r))
    return {key(r): frozenset(groups.get(r.group_id, {key(r)})) if r.group_id else frozenset()
            for r in result.rows}


def changed(base, new) -> set:
    """Line keys whose decision fields or group membership differ. Renumbering alone does not count."""
    a, b = by_key(base), by_key(new)
    ma, mb = membership(base), membership(new)
    out = set()
    for k, ra in a.items():
        rb = b.get(k)
        if rb is None:
            continue
        if any(getattr(ra, f) != getattr(rb, f) for f in COMPARED_FIELDS) or ma[k] != mb[k]:
            out.add(k)
    return out


def fired_rule(result, k):
    r = by_key(result)[k]
    d = result.decisions[r.group_id]
    return d.fired_rule["id"] if d.fired_rule else None


def rule_index(doc, rule_id) -> int:
    return [r["id"] for r in doc["rules"]].index(rule_id)
