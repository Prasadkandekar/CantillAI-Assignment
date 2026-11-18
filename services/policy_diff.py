"""Structural diff between two policy documents and deterministic plain-language bullets.

The bullets are generated from the diff by templates, never by the LLM, so the approver reads
exactly what will be activated.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from engine.conditions import param_name
from engine.facts import FACTS
from engine.money import fmt_inr

from .dates import long_date

OP_WORDS = {"eq": "is", "ne": "is not", "lt": "is below", "lte": "is at most", "gt": "is above",
            "gte": "is at least", "in": "is one of", "not_in": "is not one of"}
DECISION_WORDS = {"PO": "PO", "SOURCING_REQUEST": "Sourcing request"}
TOP_LEVEL_FIELDS = ("schema_version", "version", "effective_from", "title", "source")
RULE_FIELDS = ("clause", "text", "when", "outcome")


# --- structural diff ---------------------------------------------------------

def _lcs(a: list, b: list) -> list:
    n, k = len(a), len(b)
    table = [[0] * (k + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(k - 1, -1, -1):
            table[i][j] = table[i + 1][j + 1] + 1 if a[i] == b[j] else max(table[i + 1][j], table[i][j + 1])
    out, i, j = [], 0, 0
    while i < n and j < k:
        if a[i] == b[j]:
            out.append(a[i]); i += 1; j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def structural(old: dict, new: dict) -> dict:
    op, np_ = old.get("parameters", {}), new.get("parameters", {})
    params = {
        "added": {k: np_[k] for k in np_ if k not in op},
        "removed": {k: op[k] for k in op if k not in np_},
        "changed": {k: {"old": op[k], "new": np_[k]} for k in np_ if k in op and op[k] != np_[k]},
    }
    old_rules = {r.get("id"): r for r in old.get("rules", [])}
    new_rules = {r.get("id"): r for r in new.get("rules", [])}
    old_ids = [r.get("id") for r in old.get("rules", [])]
    new_ids = [r.get("id") for r in new.get("rules", [])]
    common_old = [i for i in old_ids if i in new_rules]
    common_new = [i for i in new_ids if i in old_rules]
    kept = set(_lcs(common_old, common_new))
    added = []
    for idx, rid in enumerate(new_ids):
        if rid not in old_rules:
            after = new_ids[idx - 1] if idx > 0 else None
            before = new_ids[idx + 1] if idx + 1 < len(new_ids) else None
            added.append({"id": rid, "after": after, "before": before, "rule": new_rules[rid]})
    moved = []
    for rid in common_new:
        if rid not in kept:
            idx = new_ids.index(rid)
            moved.append({"id": rid, "before": new_ids[idx + 1] if idx + 1 < len(new_ids) else None,
                          "after": new_ids[idx - 1] if idx > 0 else None})
    edited = []
    for rid in common_new:
        fields = {f: {"old": old_rules[rid].get(f), "new": new_rules[rid].get(f)}
                  for f in RULE_FIELDS if old_rules[rid].get(f) != new_rules[rid].get(f)}
        if fields:
            edited.append({"id": rid, "fields": fields})
    rules = {"added": added, "removed": [{"id": rid, "rule": old_rules[rid]} for rid in old_ids if rid not in new_rules],
             "moved": moved, "edited": edited}
    top = {f: {"old": old.get(f), "new": new.get(f)} for f in TOP_LEVEL_FIELDS if old.get(f) != new.get(f)}
    meta_old, meta_new = old.get("parameter_meta", {}), new.get("parameter_meta", {})
    meta = sorted(k for k in set(meta_old) | set(meta_new) if meta_old.get(k) != meta_new.get(k))
    return {"parameters": params, "rules": rules, "top_level": top, "parameter_meta_changed": meta}


# --- plain-language rendering -----------------------------------------------------

def _meta(doc_new: dict, doc_old: dict, name: str) -> dict:
    return doc_new.get("parameter_meta", {}).get(name) or doc_old.get("parameter_meta", {}).get(name) or {}


def _unit_for(name: str, meta: dict) -> str:
    if meta.get("unit"):
        return meta["unit"]
    if name.endswith("_value"):
        return "INR"
    if name.endswith("_days"):
        return "days"
    if name.endswith("_hours"):
        return "hours"
    if name.endswith("_count"):
        return "count"
    return ""


def inr(value) -> str:
    text = fmt_inr(Decimal(str(value)))
    return text[:-3] if text.endswith(".00") else text


def fmt_value(value, unit: str = "") -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, Decimal)) and unit == "INR":
        return inr(value)
    if isinstance(value, (int, float, Decimal)) and unit in ("days", "hours"):
        return f"{value} {unit}"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "(none)"
    if isinstance(value, dict):
        return ", ".join(f"{k} {v}" for k, v in value.items())
    return str(value)


def _param_title(name: str, meta: dict) -> str:
    label = meta.get("label") or name.replace("_", " ")
    return f"{label} ({meta['clause']})" if meta.get("clause") else label


def _fact_phrase(fact: str) -> str:
    fd = FACTS.get(fact)
    label = fd.label if fd else fact.replace("_", " ")
    label = label.replace(" (INR)", "")
    return label[:1].lower() + label[1:]


def condition_text(node, params: dict) -> str:
    if not isinstance(node, dict):
        return str(node)
    for key, word in (("all", " and "), ("any", " or ")):
        if key in node:
            parts = [condition_text(c, params) for c in node[key]]
            text = word.join(parts)
            return f"({text})" if key == "any" and len(parts) > 1 else text
    fact, op, value = node.get("fact"), node.get("op"), node.get("value")
    pname = param_name(value)
    if pname is not None:
        value = params.get(pname, value)
    fd = FACTS.get(fact)
    if isinstance(value, bool) and fd is not None and fd.type == "bool" and op in ("eq", "ne"):
        positive = (op == "eq") == value
        return _fact_phrase(fact) + ("" if positive else " is false")
    unit = "INR" if fd is not None and "INR" in fd.label else ""
    return f"{_fact_phrase(fact)} {OP_WORDS.get(op, op)} {fmt_value(value, unit)}"


def outcome_text(outcome: dict, params: dict) -> str:
    decision = DECISION_WORDS.get(outcome.get("decision"), outcome.get("decision"))
    sup = outcome.get("supplier", {})
    strategy = sup.get("strategy")
    count = sup.get("count")
    pname = param_name(count)
    if pname is not None:
        count = params.get(pname, count)
    supplier = {"contract": "contract supplier at contract rate",
                "preferred_first": "1st preferred supplier at its reference price",
                "suggest": f"suggest {count} suppliers",
                "none": "no supplier"}.get(strategy, f"supplier strategy {strategy}")
    return f"{decision}, route {outcome.get('route')}, {supplier}"


def bullets(diff: dict, old: dict, new: dict) -> list[str]:
    out = []
    params_new = new.get("parameters", {})
    for name, ch in diff["parameters"]["changed"].items():
        meta = _meta(new, old, name)
        unit = _unit_for(name, meta)
        out.append(f"{_param_title(name, meta)} changes from {fmt_value(ch['old'], unit)} to {fmt_value(ch['new'], unit)}")
    for name, value in diff["parameters"]["added"].items():
        meta = _meta(new, old, name)
        out.append(f"New parameter {_param_title(name, meta)}: {fmt_value(value, _unit_for(name, meta))}")
    for name, value in diff["parameters"]["removed"].items():
        meta = _meta(new, old, name)
        out.append(f"Parameter {_param_title(name, meta)} removed (was {fmt_value(value, _unit_for(name, meta))})")
    for a in diff["rules"]["added"]:
        r = a["rule"]
        where = f" before {a['before']}" if a["before"] else (f" after {a['after']}" if a["after"] else "")
        out.append(f"New rule {a['id']}{where}: when {condition_text(r.get('when'), params_new)} → "
                   f"{outcome_text(r.get('outcome', {}), params_new)}")
    for rm in diff["rules"]["removed"]:
        out.append(f"Rule {rm['id']} removed")
    for mv in diff["rules"]["moved"]:
        if mv["before"]:
            out.append(f"Rule {mv['id']} now comes before {mv['before']}")
        else:
            out.append(f"Rule {mv['id']} now comes last (after {mv['after']})")
    for ed in diff["rules"]["edited"]:
        f = ed["fields"]
        if "when" in f:
            out.append(f"Rule {ed['id']} now applies when {condition_text(f['when']['new'], params_new)}")
        if "outcome" in f:
            out.append(f"Rule {ed['id']} outcome changes to {outcome_text(f['outcome']['new'], params_new)}")
        if "text" in f:
            out.append(f"Rule {ed['id']} wording updated")
        if "clause" in f:
            out.append(f"Rule {ed['id']} clause reference changes from {f['clause']['old']} to {f['clause']['new']}")
    top = diff["top_level"]
    if "effective_from" in top:
        new_eff = top["effective_from"]["new"]
        out.append(f"Effective from {long_date(date.fromisoformat(new_eff))}" if new_eff
                   else "Effective date not set yet")
    if "title" in top:
        out.append(f"Title changes to \"{top['title']['new']}\"")
    return out


def diff_and_bullets(old: dict, new: dict) -> dict:
    d = structural(old, new)
    return {"structural": d, "bullets": bullets(d, old, new)}
