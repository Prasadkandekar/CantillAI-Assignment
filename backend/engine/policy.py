"""Policy documents: loading, parameter conversion, condition compilation and version selection."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from .conditions import compile_node, param_name
from .facts import FACTS
from .policy_validator import validate_or_raise


class PolicyNotFound(LookupError):
    pass


def convert_params(value):
    """JSON floats become Decimal(str(x)); ints stay int; containers recurse."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [convert_params(v) for v in value]
    if isinstance(value, dict):
        return {k: convert_params(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class Rule:
    id: str
    clause: str
    text: str
    when: object
    outcome: dict
    count: int | None          # resolved supplier count, if any

    @property
    def summary(self) -> dict:
        return {"id": self.id, "clause": self.clause, "text": self.text}


@dataclass(frozen=True)
class Policy:
    version: str
    effective_from: date | None
    params: dict
    rules: tuple
    document: dict
    parameter_meta: dict

    @property
    def label(self) -> str:
        return self.version


def _read(doc_or_path) -> dict:
    if isinstance(doc_or_path, dict):
        return copy.deepcopy(doc_or_path)
    return json.loads(Path(doc_or_path).read_text(encoding="utf-8"))


def load_policy(doc_or_path, *, validate: bool = True) -> Policy:
    doc = _read(doc_or_path)
    if validate:
        validate_or_raise(doc)
    params = convert_params(doc["parameters"])
    fact_types = {name: f.type for name, f in FACTS.items()}
    rules = []
    for r in doc["rules"]:
        supplier = r["outcome"]["supplier"]
        count = supplier.get("count")
        name = param_name(count)
        if name is not None:
            count = params[name]
        rules.append(Rule(r["id"], r["clause"], r["text"], compile_node(r["when"], params, fact_types),
                          copy.deepcopy(r["outcome"]), count))
    eff = doc.get("effective_from")
    return Policy(
        version=str(doc["version"]),
        effective_from=date.fromisoformat(eff) if eff else None,
        params=params,
        rules=tuple(rules),
        document=doc,
        parameter_meta=copy.deepcopy(doc.get("parameter_meta", {})),
    )


class PolicySet:
    """Approved policy versions. Later entries count as approved later (tie-break on equal dates)."""

    def __init__(self, policies):
        self.policies = [p if isinstance(p, Policy) else load_policy(p) for p in policies]

    def by_label(self, label: str) -> Policy:
        for p in self.policies:
            if p.version == label:
                return p
        raise PolicyNotFound(f"Policy version {label} not found")

    def select(self, d: date, pin: str | None = None, as_of: date | None = None) -> Policy | None:
        if pin:
            return self.by_label(pin)
        when = as_of or d
        best, best_idx = None, -1
        for idx, p in enumerate(self.policies):
            if p.effective_from is None or p.effective_from > when:
                continue
            if best is None or (p.effective_from, idx) > (best.effective_from, best_idx):
                best, best_idx = p, idx
        return best
