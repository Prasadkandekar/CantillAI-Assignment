"""Amendment text -> a full draft policy JSON built from the active version.

The LLM gets the grammar, the fact registry, ops, strategies and parameter_meta and must return the
whole document. Without the LLM (no key, LLM_DISABLED, API failure, invalid reply) a rule-based
reader handles the common amendment sentences and lists every sentence it could not express.
Neither path invents numbers: every value comes from the amendment text.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

from engine import validate
from engine.conditions import OPS, param_name
from engine.facts import FACTS
from engine.strategies import STRATEGIES

from . import llm
from .amounts import find_amounts
from .dates import effective_date

# Which parameter a limit word refers to. These are parameter NAMES (data keys), not policy numbers.
LIMIT_PARAMS = {"spot": "spot_max_value", "emergency": "emergency_max_value", "rfp": "rfp_min_value",
                "rfq": "rfp_min_value"}
SUGGEST_PARAMS = {"rfq": "rfq_suggestion_count", "rfp": "rfp_suggestion_count", "capex": "capex_suggestion_count"}
WINDOW_PATTERNS = (  # (regex that must match, parameter, unit word)
    (r"need[- ]?by", "club_needby_days", "day"),
    (r"club", "club_created_days", "day"),
    (r"consolidat", "consolidation_hours", "hour"),
    (r"price history|valuation", "price_history_days", "day"),
    (r"preferred", "preferred_history_days", "day"),
    (r"bought|purchase history", "bought_history_days", "day"),
)
WEIGHT_WORDS = {"frequency": "frequency", "recency": "recency", "contract": "contract", "on-time": "on_time",
                "on time": "on_time", "ontime": "on_time", "quality": "quality"}
ROUTE_WORDS = {"rfq": "RFQ", "rfp": "RFP"}


@dataclass
class ReaderResult:
    document: dict
    effective_from: str | None
    mode: str                         # llm / fallback
    unrecognised: list = field(default_factory=list)
    applied: list = field(default_factory=list)
    llm_error: str | None = None


def next_label(base_label: str, existing) -> str:
    existing = set(existing)
    try:
        major, minor = base_label.split(".", 1)
        n = int(minor)
    except ValueError:
        major, n = base_label, 0
    while True:
        n += 1
        label = f"{major}.{n}"
        if label not in existing:
            return label


def sentences(text: str) -> list[str]:
    t = re.sub(r"\b(Rs|No|Sr)\.", r"\1", text or "", flags=re.I)
    parts = re.split(r"(?<=[.;!?])\s+|\n+", t)
    return [p.strip(" -•*\t") for p in parts if p and p.strip(" -•*\t.")]


# --- helpers over the document (generic: rules are found by the parameters they reference) ---------

def _leaves(node):
    if isinstance(node, dict):
        if "fact" in node:
            yield node
        for key in ("all", "any"):
            for child in node.get(key, []):
                yield from _leaves(child)


def rules_using_param(doc: dict, param: str) -> list[int]:
    return [i for i, r in enumerate(doc["rules"]) if any(param_name(l.get("value")) == param for l in _leaves(r["when"]))]


def _unique_rule_id(doc: dict, wanted: str) -> str:
    ids = {r["id"] for r in doc["rules"]}
    rid, n = wanted, 1
    while rid in ids:
        n += 1
        rid = f"{wanted}-{n}"
    return rid


def _amount_after_to(sentence: str):
    amounts = find_amounts(sentence)
    if not amounts:
        return None
    m_to = re.search(r"\bto\b", sentence, re.I)
    if m_to:
        after = [a for a in amounts if a[1] >= m_to.end()]
        if after:
            return after[0][0]
    return amounts[-1][0]


def _int_after_to(sentence: str, unit: str):
    nums = [(int(mt.group(1)), mt.start()) for mt in re.finditer(r"(\d{1,4})\s*" + unit + r"s?\b", sentence, re.I)]
    if not nums:
        return None
    m_to = re.search(r"\bto\b", sentence, re.I)
    if m_to:
        after = [n for n, pos in nums if pos >= m_to.end()]
        if after:
            return after[0]
    return nums[-1][0]


def _json_number(value: Decimal):
    return int(value) if value == value.to_integral_value() else float(value)


def _plant_in(sentence: str, plants: dict) -> str | None:
    s = sentence.lower()
    for code, name in plants.items():
        if re.search(r"\b" + re.escape(code.lower()) + r"\b", s):
            return code
    for code, name in plants.items():
        for word in re.findall(r"[a-z]+", name.lower()):
            if word in ("plant", "the") or len(word) < 4:
                continue
            if re.search(r"\b" + re.escape(word) + r"\b", s):
                return code
    return None


def _category_in(sentence: str, categories) -> str | None:
    s = sentence.lower()
    for cat in sorted(categories, key=len, reverse=True):
        if cat.lower() in s:
            return cat
    return None


class _Fallback:
    def __init__(self, base: dict, plants: dict, categories):
        self.doc = copy.deepcopy(base)
        self.plants = plants
        self.categories = list(categories)
        self.applied: list[str] = []
        self.unrecognised: list[str] = []
        self.effective_from = None

    def set_param(self, name: str, value, sentence: str) -> bool:
        params = self.doc["parameters"]
        if name not in params:
            return False
        params[name] = value
        self.applied.append(sentence)
        return True

    # each handler returns True when it expressed the sentence
    def plant_limit(self, s: str) -> bool:
        low = s.lower()
        plant = _plant_in(s, self.plants)
        word = next((w for w in ("emergency", "spot") if w in low), None)
        amount = _amount_after_to(s)
        if not (plant and word and amount is not None and re.search(r"limit|up to|upto|ceiling|max", low)):
            return False
        generic = LIMIT_PARAMS[word]
        idxs = rules_using_param(self.doc, generic)
        if not idxs:
            return False
        new_param = f"{plant.lower()}_{generic}"
        params = self.doc["parameters"]
        params[new_param] = _json_number(amount)
        base_meta = self.doc.get("parameter_meta", {}).get(generic, {})
        self.doc.setdefault("parameter_meta", {})[new_param] = {
            "clause": base_meta.get("clause", ""),
            "label": f"{base_meta.get('label', generic)} for {plant}", "unit": base_meta.get("unit", "INR")}
        for offset, idx in enumerate(idxs):
            idx += offset
            rule = self.doc["rules"][idx]
            plant_rule = copy.deepcopy(rule)
            for leaf in _leaves(plant_rule["when"]):
                if param_name(leaf.get("value")) == generic:
                    leaf["value"] = "$" + new_param
            plant_rule["when"] = {"all": [{"fact": "plant", "op": "eq", "value": plant}, plant_rule["when"]]}
            plant_rule["id"] = _unique_rule_id(self.doc, f"{rule['id']}-{plant}")
            plant_rule["clause"] = f"{rule['clause']} ({plant} amendment)"
            plant_rule["text"] = s
            excl = {"fact": "plant", "op": "not_in", "value": [plant]}
            existing = next((l for l in _leaves(rule["when"]) if l.get("fact") == "plant" and l.get("op") == "not_in"
                             and isinstance(l.get("value"), list)), None)
            if existing is not None:
                if plant not in existing["value"]:
                    existing["value"].append(plant)
            elif "all" in rule["when"]:
                rule["when"]["all"].insert(0, excl)
            else:
                rule["when"] = {"all": [excl, rule["when"]]}
            self.doc["rules"].insert(idx, plant_rule)
        self.applied.append(s)
        return True

    def category_rule(self, s: str) -> bool:
        low = s.lower()
        cat = _category_in(s, self.categories)
        route_word = next((w for w in ROUTE_WORDS if re.search(r"\b" + w + r"\b", low)), None)
        amounts = find_amounts(s)
        amount = amounts[0][0] if amounts else None
        if not (cat and route_word and amount is not None):
            return False
        route = ROUTE_WORDS[route_word]
        template = next((r for r in self.doc["rules"] if r["outcome"].get("route") == route), None)
        if template is None:
            return False
        op = "gt" if re.search(r"\b(above|over|more than|exceeding)\b", low) and not re.search(
            r"at or above|and above|or more|or above", low) else "gte"
        conds = []
        plant = _plant_in(s, self.plants)
        if plant:
            conds.append({"fact": "plant", "op": "eq", "value": plant})
        conds.append({"fact": "category", "op": "eq", "value": cat})
        conds.append({"fact": "group_value", "op": op, "value": _json_number(amount)})
        slug = re.sub(r"[^A-Z0-9]+", "-", cat.upper()).strip("-")[:12]
        rid = _unique_rule_id(self.doc, f"{plant + '-' if plant else ''}{slug}")
        new_rule = {"id": rid, "clause": f"{template['clause']} (amendment)", "text": s, "when": {"all": conds},
                    "outcome": copy.deepcopy(template["outcome"])}
        new_rule["outcome"].pop("note", None)
        spot_rules = rules_using_param(self.doc, LIMIT_PARAMS["spot"])
        pos = spot_rules[0] if spot_rules else self.doc["rules"].index(template)
        self.doc["rules"].insert(pos, new_rule)
        self.applied.append(s)
        return True

    def limit(self, s: str) -> bool:
        low = s.lower()
        word = next((w for w in LIMIT_PARAMS if re.search(r"\b" + w + r"\b", low)), None)
        if word is None or not re.search(r"limit|threshold|ceiling|up to|upto|max|value", low):
            return False
        amount = _amount_after_to(s)
        if amount is None:
            return False
        return self.set_param(LIMIT_PARAMS[word], _json_number(amount), s)

    def window(self, s: str) -> bool:
        low = s.lower()
        for rx, name, unit in WINDOW_PATTERNS:
            if re.search(rx, low):
                n = _int_after_to(s, unit)
                if n is not None:
                    return self.set_param(name, n, s)
        return False

    def suggest_count(self, s: str) -> bool:
        low = s.lower()
        if not re.search(r"suggest|supplier", low):
            return False
        word = next((w for w in SUGGEST_PARAMS if re.search(r"\b" + w + r"\b", low)), None)
        mt = re.search(r"(\d{1,2})\s+(?:\w+\s+)?suppliers?", low)
        if word is None or mt is None:
            return False
        return self.set_param(SUGGEST_PARAMS[word], int(mt.group(1)), s)

    def weights(self, s: str) -> bool:
        low = s.lower()
        if "weight" not in low and "rank" not in low:
            return False
        found = {}
        for word, key in WEIGHT_WORDS.items():
            mt = re.search(re.escape(word) + r"\s*(?:weight)?\s*(?:[:=]|to|of|at)?\s*(0?\.\d+|1(?:\.0+)?|\d{1,3}\s*%)", low)
            if mt:
                raw = mt.group(1).replace(" ", "")
                value = Decimal(raw[:-1]) / 100 if raw.endswith("%") else Decimal(raw)
                found[key] = float(value)
        if not found:
            return False
        weights = dict(self.doc["parameters"].get("ranking_weights", {}))
        weights.update(found)
        self.doc["parameters"]["ranking_weights"] = weights
        self.applied.append(s)
        return True

    def effective(self, s: str) -> bool:
        d = effective_date(s)
        if d is None:
            return False
        self.effective_from = d.isoformat()
        return True

    def read(self, text: str):
        handlers = (self.effective, self.plant_limit, self.category_rule, self.weights, self.suggest_count,
                    self.limit, self.window)
        for s in sentences(text):
            handled = False
            for h in handlers:
                if h(s):
                    handled = True
                    if h != self.effective:   # a date can share a sentence with a change
                        break
            if not handled and re.search(r"[a-zA-Z]{3}", s):
                self.unrecognised.append(s)


def read_fallback(text: str, base: dict, plants: dict, categories) -> tuple[dict, str | None, list, list]:
    fb = _Fallback(base, plants, categories)
    fb.read(text)
    return fb.doc, fb.effective_from, fb.unrecognised, fb.applied


# --- LLM path ---------------------------------------------------------------------

def _system_prompt(base: dict) -> str:
    facts = "\n".join(f"- {n} ({f.type}): {f.label}" for n, f in FACTS.items())
    return (
        "You edit procurement policy documents expressed as JSON. Grammar:\n"
        "- A rule is {id, clause, text, when, outcome}; rules run in list order, first match wins.\n"
        "- A condition is {fact, op, value} or {all:[...]} or {any:[...]} (nesting allowed).\n"
        f"- Ops: {', '.join(OPS)}. A value is a literal or \"$param_name\" naming a key of parameters.\n"
        f"- outcome = {{decision, route, supplier: {{strategy, count?}}, note?}}; strategies: {', '.join(STRATEGIES)}.\n"
        f"Facts:\n{facts}\n"
        f"parameter_meta (labels of parameters): {json.dumps(base.get('parameter_meta', {}), ensure_ascii=False)}\n"
        "Every outcome MUST contain decision (only PO or SOURCING_REQUEST), route and supplier {strategy}. "
        "Never invent other decisions such as NO_PO; if a sentence cannot be expressed this way, do not add a rule "
        "and list it in 'unsupported'.\n"
        "Plant-only limits: insert a copy of the generic rule with an extra {fact: plant, op: eq, value: P} "
        "condition and its own new parameter before the generic rule, and add {fact: plant, op: not_in, value: [P]} "
        "to the generic rule.\n"
        "Return the FULL policy JSON. Change only what the amendment says; keep all other rule texts. Quote the "
        "amendment sentence in new rules' text. Set effective_from only if the amendment states a date, else null. "
        "List amendment sentences you could not express in 'unsupported'. Never invent numbers."
    )


_RULE_PATH = re.compile(r"^rules\[(\d+)\]\.outcome")


def _drop_unexpressible_rules(doc: dict, base: dict) -> list[str]:
    """Remove NEW rules whose outcome the engine cannot express (e.g. a 'NO_PO' decision without
    route/supplier) so the draft stays activatable. They are reported as unsupported instead."""
    base_ids = {r.get("id") for r in base.get("rules", []) if isinstance(r, dict)}
    bad = set()
    for e in validate(doc).errors:
        m = _RULE_PATH.match(e.path or "")
        if m:
            bad.add(int(m.group(1)))
    rules = doc.get("rules", [])
    dropped = []
    for i in sorted(bad, reverse=True):
        rule = rules[i] if i < len(rules) else None
        if isinstance(rule, dict) and rule.get("id") not in base_ids:
            dropped.append(f"Not expressible as a rule (needs decision PO/SOURCING_REQUEST, a route and a supplier "
                           f"strategy): {rule.get('text') or rule.get('id')}")
            del rules[i]
    return dropped


def read_llm(text: str, base: dict, label: str) -> tuple[dict, str | None, list]:
    schema = ('{"policy": <full policy JSON>, "effective_from": "YYYY-MM-DD" or null, "version": "' + label +
              '", "unsupported": ["sentence", ...]}')
    user = f"Current policy JSON:\n{json.dumps(base, ensure_ascii=False)}\n\nAmendment:\n{text}"
    out = llm.complete_json(_system_prompt(base), user, schema, max_tokens=8000)
    doc = out.get("policy")
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        raise llm.LLMUnavailable("reply had no policy document")
    result = validate(doc)
    if result.errors:
        repair = (f"{user}\n\nYour previous policy JSON had these validation errors:\n"
                  + "\n".join(str(e) for e in result.errors) + f"\n\nPrevious JSON:\n{json.dumps(doc)}\nFix them.")
        out2 = llm.complete_json(_system_prompt(base), repair, schema, max_tokens=8000)
        if isinstance(out2.get("policy"), dict):
            out = out2
            doc = out2["policy"]
    unsupported = [str(u) for u in out.get("unsupported") or [] if str(u).strip()]
    unsupported += _drop_unexpressible_rules(doc, base)
    eff = out.get("effective_from") or doc.get("effective_from")
    if eff == base.get("effective_from"):
        eff = None
    return doc, (str(eff) if eff else None), unsupported


def read(text: str, base: dict, *, label: str, plants: dict, categories, mode: str = "auto") -> ReaderResult:
    llm_error = None
    if mode != "fallback":
        try:
            doc, eff, unsupported = read_llm(text, base, label)
            # The amendment's own words decide the effective date when it states one.
            stated = effective_date(text)
            if stated:
                eff = stated.isoformat()
            return _finish(doc, eff, "llm", unsupported, [], label)
        except llm.LLMUnavailable as exc:
            llm_error = str(exc)
    doc, eff, unrecognised, applied = read_fallback(text, base, plants, categories)
    res = _finish(doc, eff, "fallback", unrecognised, applied, label)
    res.llm_error = llm_error
    return res


def _finish(doc: dict, eff: str | None, mode: str, unrecognised, applied, label: str) -> ReaderResult:
    doc = copy.deepcopy(doc)
    doc["version"] = label
    doc["effective_from"] = eff
    return ReaderResult(doc, eff, mode, list(unrecognised), list(applied))
