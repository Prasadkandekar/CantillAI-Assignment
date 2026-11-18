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
from engine.parameters import REQUIRED_PARAMETERS
from engine.policy_validator import PARAMETER_META_KEYS, SCHEMA_VERSION, TOP_LEVEL_OPTIONAL, TOP_LEVEL_REQUIRED
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
    informational: list = field(default_factory=list)   # clauses the engine builds in; not errors
    kind: str = "amendment"                              # amendment / full


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
    if is_full_policy(text):
        return read_full_policy(text, base, label=label, plants=plants, mode=mode)
    llm_error = None
    if mode != "fallback":
        try:
            doc, eff, unsupported = read_llm(text, base, label)
            # The amendment's own words decide the effective date when it states one.
            stated = effective_date(text)
            if stated:
                eff = stated.isoformat()
            return _finish(doc, eff, "llm", unsupported, [], label, base)
        except llm.LLMUnavailable as exc:
            llm_error = str(exc)
    doc, eff, unrecognised, applied = read_fallback(text, base, plants, categories)
    res = _finish(doc, eff, "fallback", unrecognised, applied, label, base)
    res.llm_error = llm_error
    return res


def _stamp(doc: dict, base: dict | None, label: str, eff: str | None) -> dict:
    """Structural fields the document cannot know are set here, never trusted to the LLM."""
    doc = copy.deepcopy(doc)
    doc["schema_version"] = SCHEMA_VERSION
    doc["version"] = label
    doc["effective_from"] = eff
    for key in list(doc):
        if key not in TOP_LEVEL_REQUIRED and key not in TOP_LEVEL_OPTIONAL:
            del doc[key]
    base = base or {}
    for key in ("title", "source"):
        if key not in doc and key in base:
            doc[key] = copy.deepcopy(base[key])
    params = doc.get("parameters")
    if not isinstance(params, dict):
        params = doc["parameters"] = {}
    for name in REQUIRED_PARAMETERS:     # gaps in the engine's required parameters come from the base
        if name not in params and name in base.get("parameters", {}):
            params[name] = copy.deepcopy(base["parameters"][name])
    meta = {}
    base_meta = base.get("parameter_meta") if isinstance(base.get("parameter_meta"), dict) else {}
    new_meta = doc.get("parameter_meta") if isinstance(doc.get("parameter_meta"), dict) else {}
    for name in params:
        entry = {}
        for src in (base_meta.get(name), new_meta.get(name)):
            if isinstance(src, dict):
                entry.update({k: v for k, v in src.items() if k in PARAMETER_META_KEYS and isinstance(v, str)})
        if entry:
            meta[name] = entry
    doc["parameter_meta"] = meta
    return doc


def _finish(doc: dict, eff: str | None, mode: str, unrecognised, applied, label: str,
            base: dict | None = None) -> ReaderResult:
    doc = _stamp(doc, base, label, eff)
    return ReaderResult(doc, eff, mode, list(unrecognised), list(applied))


# --- full replacement policy documents ------------------------------------------------
# A full policy (not a small amendment) is read clause by clause. The section-5 decision table is turned
# into rules with the engine's registered facts and ops; every number comes from the document text.
# The LLM is only asked when the deterministic reader could not express every row, and its reply is a
# patch (changed parameters + rule list) that is stamped, repaired and checked before it is trusted.

_CLAUSE = re.compile(r"^(\d{1,2}\.\d{1,2})\s+\S")
_HEADING = re.compile(r"^\d{1,2}\.\s+\S")
_INFO_SECTIONS = {"1", "2", "3", "4", "6", "7", "8", "9"}
_ROUTE_TOKEN = re.compile(r"\b(CAPEX_SOURCING|CONTRACT_PO|EMERGENCY_PO|SPOT_PO)\b")
_SUGGEST = re.compile(r"suggest\s+(\d{1,2})\s+suppliers?", re.I)
_PLANT_AMOUNT = re.compile(r"\(\s*plant\s+([A-Za-z0-9]+)\s*\)", re.I)
_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").lower()).strip(" .;:-")


def is_full_policy(text: str) -> bool:
    """A whole policy document (header, numbered clauses, a decision-rule table) rather than a short amendment."""
    t = text or ""
    clauses = len(re.findall(r"(?m)^\d{1,2}\.\d{1,2}\s+\S", t))
    signals = (re.search(r"\bversion\s+\d+(\.\d+)?\b", t, re.I) is not None and "supersede" in t.lower(),
               re.search(r"decision rules", t, re.I) is not None,
               clauses >= 5,
               len(t) > 3000)
    return sum(signals) >= 3


def paragraphs(text: str) -> list[str]:
    """Lines joined into clause paragraphs (PDF text wraps lines and table cells)."""
    out, cur = [], []

    def flush():
        if cur:
            out.append(_WS.sub(" ", " ".join(cur)).strip())
            cur.clear()

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if re.search(r"\bpage\s+\d+\s+of\s+\d+\b", line, re.I):
            flush()
            out.append(line)
            continue
        if _CLAUSE.match(line) or _HEADING.match(line) or line.startswith("#"):
            flush()
        cur.append(line)
        if _HEADING.match(line) and len(line) < 70 and not line.endswith("."):
            flush()
    flush()
    return out


def _clause_of(par: str) -> str | None:
    m_ = _CLAUSE.match(par)
    return m_.group(1) if m_ else None


def _inr(value) -> str:
    s = str(int(value))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def _money(value) -> str:
    return "\u20b9" + _inr(value)


def _cond(fact, op, value):
    return {"fact": fact, "op": op, "value": value}


_BOUGHT = _cond("bought_from_active_365d", "eq", True)


class _Full:
    def __init__(self, base: dict, plants: dict):
        self.base = base
        self.plants = plants
        self.doc = copy.deepcopy(base)
        self.applied: list[str] = []
        self.unrecognised: list[str] = []
        self.informational: list[str] = []
        self.extracted: dict = {}
        self.complete = False

    # -- parameter helpers ---------------------------------------------------------------
    def setp(self, name, value, clause, label=None, unit=None):
        old = self.doc["parameters"].get(name)
        self.doc["parameters"][name] = value
        self.extracted[name] = value
        meta = self.doc.setdefault("parameter_meta", {}).setdefault(name, {})
        meta["clause"] = clause
        if label and "label" not in meta:
            meta["label"] = label
        if unit and "unit" not in meta:
            meta["unit"] = unit
        if old != value:
            self.applied.append(f"{name}: {old if old is not None else '(new)'} -> {value}")

    def _first_int(self, pattern, text):
        mt = re.search(pattern, text, re.I)
        return int(mt.group(1)) if mt else None

    def base_rule(self, route):
        for r in self.base.get("rules", []):
            if isinstance(r, dict) and isinstance(r.get("outcome"), dict) and r["outcome"].get("route") == route:
                return copy.deepcopy(r)
        return None

    # -- rows ----------------------------------------------------------------------------
    def row_rules(self, clause, par, svc_count_param):
        """Rules for one decision-table row, or None when the row cannot be expressed."""
        amounts = [a[0] for a in find_amounts(par)]
        sug = _SUGGEST.search(par)
        count = int(sug.group(1)) if sug else None
        tok = _ROUTE_TOKEN.search(par)
        route = tok.group(1) if tok else None
        sourcing = re.search(r"\bsourcing\b", par, re.I) is not None
        if route is None and sourcing:
            for word in ("RFQ", "RFP"):
                if re.search(r"\b" + word + r"\b", par):
                    route = word
        if route is None:
            return None
        if route == "CAPEX_SOURCING":
            if count is not None:
                self.setp("capex_suggestion_count", count, clause, "Suppliers suggested for capex sourcing", "count")
            return [{"id": clause, "clause": clause,
                     "text": f"The item type is Capex: Sourcing request, route CAPEX_SOURCING, suggest "
                             f"{self.doc['parameters'].get('capex_suggestion_count')} suppliers (6.4). Needs capex approval.",
                     "when": {"all": [_cond("item_type", "eq", "Capex")]},
                     "outcome": {"decision": "SOURCING_REQUEST", "route": route,
                                 "supplier": {"strategy": "suggest", "count": "$capex_suggestion_count"},
                                 "note": "Needs capex approval."}}]
        if route == "CONTRACT_PO":
            return [{"id": clause, "clause": clause,
                     "text": "A contract can be used (4.1 to 4.3): PO, route CONTRACT_PO, contract supplier at contract rate.",
                     "when": {"all": [_cond("contract_usable", "eq", True)]},
                     "outcome": {"decision": "PO", "route": route, "supplier": {"strategy": "contract"}}}]
        if route == "EMERGENCY_PO":
            return self._emergency(clause, par)
        if route == "SPOT_PO":
            if not amounts:
                return None
            self.setp("spot_max_value", _json_number(amounts[0]), clause, "Spot PO limit", "INR")
            return [{"id": clause, "clause": clause,
                     "text": f"Value below {_money(amounts[0])}, and the item was bought from an Active supplier in the "
                             "last 365 days: PO, route SPOT_PO, 1st preferred supplier at its reference price.",
                     "when": {"all": [_cond("group_value", "lt", "$spot_max_value"), _BOUGHT]},
                     "outcome": {"decision": "PO", "route": route, "supplier": {"strategy": "preferred_first"}}}]
        if route == "RFQ" and re.search(r"\bservice\b", par, re.I):
            if not amounts:
                return None
            self.setp("service_rfq_min_value", _json_number(amounts[0]), clause, "Service RFQ threshold", "INR")
            cp = svc_count_param
            if count is not None:
                self.setp(cp, count, clause, "Suppliers suggested for an RFQ", "count")
            return [{"id": clause, "clause": clause,
                     "text": f"The item type is Service and the value is {_money(amounts[0])} or more: Sourcing request, "
                             f"route RFQ, suggest {self.doc['parameters'].get(cp)} suppliers (6.4).",
                     "when": {"all": [_cond("item_type", "eq", "Service"),
                                      _cond("group_value", "gte", "$service_rfq_min_value")]},
                     "outcome": {"decision": "SOURCING_REQUEST", "route": route,
                                 "supplier": {"strategy": "suggest", "count": "$" + cp}}}]
        if route == "RFQ":
            if not amounts:
                return None
            self.rfq_limit = amounts[0]
            if count is not None:
                self.setp("rfq_suggestion_count", count, clause, "Suppliers suggested for an RFQ", "count")
            return [{"id": clause, "clause": clause,
                     "text": f"Value below {_money(amounts[0])} (including small items never bought in the last 365 "
                             f"days): Sourcing request, route RFQ, suggest {self.doc['parameters'].get('rfq_suggestion_count')} "
                             "suppliers (6.4).",
                     "when": {"all": [_cond("group_value", "lt", "$rfp_min_value")]},
                     "outcome": {"decision": "SOURCING_REQUEST", "route": route,
                                 "supplier": {"strategy": "suggest", "count": "$rfq_suggestion_count"}}}]
        if route == "RFP":
            if not amounts:
                return None
            self.rfp_limit = amounts[0]
            self.setp("rfp_min_value", _json_number(amounts[0]), clause, "RFP threshold", "INR")
            if count is not None:
                self.setp("rfp_suggestion_count", count, clause, "Suppliers suggested for an RFP", "count")
            return [{"id": clause, "clause": clause,
                     "text": f"Value {_money(amounts[0])} or more: Sourcing request, route RFP, suggest "
                             f"{self.doc['parameters'].get('rfp_suggestion_count')} suppliers (6.4).",
                     "when": {"all": [_cond("group_value", "gte", "$rfp_min_value")]},
                     "outcome": {"decision": "SOURCING_REQUEST", "route": route,
                                 "supplier": {"strategy": "suggest", "count": "$rfp_suggestion_count"}}}]
        return None

    def _emergency(self, clause, par):
        found = []   # (plant, amount)
        for amount, _start, end in find_amounts(par):
            mt = _PLANT_AMOUNT.match(par[end:].lstrip())
            if mt:
                code = next((c for c in self.plants if c.lower() == mt.group(1).lower()), mt.group(1).upper())
                found.append((code, amount))
        singles = [a[0] for a in find_amounts(par)]
        rules = []

        def build(rid, text, plant_conds, param):
            return {"id": rid, "clause": clause, "text": text,
                    "when": {"all": plant_conds + [_cond("is_emergency", "eq", True),
                                                   _cond("group_value", "lte", "$" + param), _BOUGHT]},
                    "outcome": {"decision": "PO", "route": "EMERGENCY_PO", "supplier": {"strategy": "preferred_first"}}}

        if found:
            for plant, amount in found:
                pname = f"{plant.lower()}_emergency_max_value"
                self.setp(pname, _json_number(amount), clause, f"Emergency PO limit for {plant}", "INR")
                rules.append(build(f"{clause}-{plant}",
                                   f"Plant {plant}: emergency, value \u2264 {_money(amount)}, and the item was bought from "
                                   "an Active supplier in the last 365 days: PO, route EMERGENCY_PO, 1st preferred supplier "
                                   "(section 6) at its reference price.",
                                   [_cond("plant", "eq", plant)], pname))
            covered = [p for p, _ in found]
            if set(self.plants) - set(covered):    # a plant the document does not name keeps the generic limit
                rules.append(build(clause, f"Emergency at any other plant, value within the generic emergency limit, and "
                                           "the item was bought from an Active supplier in the last 365 days: PO, route "
                                           "EMERGENCY_PO, 1st preferred supplier at its reference price.",
                                   [_cond("plant", "not_in", covered)], "emergency_max_value"))
            return rules
        if not singles:
            return None
        self.setp("emergency_max_value", _json_number(singles[0]), clause, "Emergency PO limit", "INR")
        return [build(clause, f"Emergency, value \u2264 {_money(singles[0])}, and the item was bought from an Active "
                              "supplier in the last 365 days: PO, route EMERGENCY_PO, 1st preferred supplier "
                              "(section 6) at its reference price.", [], "emergency_max_value")]

    # -- whole document --------------------------------------------------------------------
    def run(self, text: str):
        pars = paragraphs(text)
        flat = _WS.sub(" ", text or "")
        handled: set[str] = set()
        # 2.2 / 7.1 windows
        for name, pattern, clause in (
                ("club_created_days", r"created within (\d+)\s+(?:calendar\s+)?days", "2.2"),
                ("club_needby_days", r"need-by date is within (\d+)\s+(?:calendar\s+)?days", "2.2"),
                ("consolidation_hours", r"raised within (\d+)\s+hours", "7.1")):
            n = self._first_int(pattern, flat)
            if n is not None and name in self.doc["parameters"]:
                self.setp(name, n, clause)
                handled.add(clause)
        rows = [(c, p) for p in pars if (c := _clause_of(p)) and c.startswith("5.")]
        svc_param = "rfq_suggestion_count"
        plain_rfq = next((_SUGGEST.search(p) for c, p in rows if re.search(r"\bRFQ\b", p) and not re.search(r"\bservice\b", p, re.I)), None)
        svc_row = next((_SUGGEST.search(p) for c, p in rows if re.search(r"\bservice\b", p, re.I)), None)
        if plain_rfq and svc_row and plain_rfq.group(1) != svc_row.group(1):
            svc_param = "service_rfq_suggestion_count"
        self.rfq_limit = self.rfp_limit = None
        built: list[dict] = []
        row_clauses: set[str] = set()
        for clause, par in rows:
            rules = self.row_rules(clause, par, svc_param)
            if rules is None:
                tok = _ROUTE_TOKEN.search(par) or re.search(r"\b(RFQ|RFP)\b", par)
                if tok is None:        # prose such as "Blocked or Inactive suppliers must never ..." (engine built-in)
                    continue
                route_names = [r_ for r_ in ("CAPEX_SOURCING", "CONTRACT_PO", "EMERGENCY_PO", "SPOT_PO", "RFQ", "RFP")
                               if re.search(r"\b" + r_ + r"\b", par)]
                fb = self.base_rule(route_names[0]) if route_names else None
                if fb is not None:
                    fb["id"] = fb["clause"] = clause
                    built.append(fb)
                    row_clauses.add(clause)
                    self.unrecognised.append(f"{clause}: kept the previous rule for this row; check it. {par}")
                else:
                    self.unrecognised.append(par)
                continue
            built.extend(rules)
            row_clauses.add(clause)
        if self.rfq_limit is not None and self.rfp_limit is not None and self.rfq_limit != self.rfp_limit:
            self.unrecognised.append(f"The RFQ ceiling ({_money(self.rfq_limit)}) and the RFP threshold "
                                     f"({_money(self.rfp_limit)}) differ; the RFP threshold is used for both.")
        kept = [copy.deepcopy(r) for r in self.base.get("rules", [])
                if isinstance(r, dict) and isinstance(r.get("outcome"), dict)
                and r["outcome"].get("route") == "NEW_ITEM_SOURCING"]
        if kept:
            handled.add("1.2")
        if built:
            self.doc["rules"] = kept + built
        self._cleanup(pars)
        # classification of every paragraph
        applied_clauses = handled | row_clauses
        for par in pars:
            clause = _clause_of(par)
            if clause is None:
                self.informational.append(par)            # title, intro, headings, table header, page footers
            elif clause in applied_clauses:
                continue
            elif clause.startswith("5.") and not find_amounts(par) and not _ROUTE_TOKEN.search(par):
                self.informational.append(par)            # e.g. 5.8 blocked suppliers: eligible_supplier_statuses
            elif clause.split(".")[0] in _INFO_SECTIONS and not find_amounts(par):
                self.informational.append(par)
            elif clause in ("2.2", "7.1"):
                self.unrecognised.append(par)
            else:
                self.unrecognised.append(par)
        self.complete = bool(built) and not self.unrecognised
        return self

    def _cleanup(self, pars):
        """Parameters no rule uses any more go (limits of a split or removed rule); clause labels follow the rules."""
        for _ in range(2):
            orphans = [w.path.split(".", 1)[1] for w in validate(self.doc).warnings
                       if w.message == "defined but never referenced" and w.path.startswith("parameters.")]
            for name in orphans:
                self.doc["parameters"].pop(name, None)
                self.doc.get("parameter_meta", {}).pop(name, None)
        meta = self.doc.get("parameter_meta", {})
        for name, entry in meta.items():
            using = [r["clause"] for r in self.doc["rules"] if any(param_name(l.get("value")) == name for l in _leaves(r["when"]))
                     or param_name(r["outcome"].get("supplier", {}).get("count")) == name]
            if name == "bought_history_days":
                using = [r["clause"] for r in self.doc["rules"] if any(l.get("fact") == "bought_from_active_365d" for l in _leaves(r["when"]))]
            if using:
                entry["clause"] = "/".join(dict.fromkeys(using))
        blocked = next((_clause_of(p) for p in pars if _clause_of(p) and re.search(r"\bblocked\b.*\binactive\b", p, re.I)), None)
        if blocked and "eligible_supplier_statuses" in meta:
            meta["eligible_supplier_statuses"]["clause"] = f"4.1/{blocked}"


def _referenced_params(doc: dict) -> set:
    out = set()
    for r in doc.get("rules", []):
        if not isinstance(r, dict):
            continue
        out |= {param_name(l.get("value")) for l in _leaves(r.get("when", {}))}
        sup = (r.get("outcome") or {}).get("supplier") if isinstance(r.get("outcome"), dict) else None
        if isinstance(sup, dict):
            out.add(param_name(sup.get("count")))
    out.discard(None)
    return out


_RULE_ERR = re.compile(r"^rules\[(\d+)\]")


def _drop_invalid_rules(doc: dict) -> list[str]:
    """Drop every rule that fails validation (invented fact, NO_PO outcome...) and duplicate ids; report them."""
    dropped = []
    rules = doc.get("rules")
    if not isinstance(rules, list):
        return dropped
    seen, kept = set(), []
    for r in rules:
        if isinstance(r, dict) and r.get("id") not in seen:
            seen.add(r.get("id"))
            kept.append(r)
    doc["rules"] = kept
    for _ in range(len(kept) + 1):
        bad = sorted({int(m_.group(1)) for e in validate(doc).errors if (m_ := _RULE_ERR.match(e.path or ""))}, reverse=True)
        if not bad:
            break
        for i in bad:
            if i < len(doc["rules"]):
                r = doc["rules"].pop(i)
                dropped.append(r.get("text") or r.get("id") if isinstance(r, dict) else str(r))
    return dropped


def _full_prompt(base: dict) -> str:
    return (_system_prompt(base).split("Return the FULL policy JSON.")[0] +
            "You receive a COMPLETE replacement policy document. Do not return a policy document. Return a patch: "
            "'parameters' = only parameters whose value changed or that are new (plus 'parameter_meta' for new ones: "
            "{clause,label,unit}); 'rules' = the full ordered rule list from the document's decision-rule table "
            "(first match wins), keeping the id and clause numbers of the document. Reference limits and counts as "
            "\"$param\" and define every parameter you reference. Use only the listed facts, ops and strategies; never "
            "invent a fact. Clauses about item matching, clubbing, valuation, contracts, the preferred list, "
            "consolidation, record keeping, transition and blocked/inactive suppliers are built into the engine: do "
            "not make rules for them and do not list them as unsupported. Keep the rule for new items. Put only "
            "decision-table rows you could not express in 'unsupported'. Never invent numbers.")


def _apply_patch(base: dict, out: dict) -> dict:
    doc = copy.deepcopy(base)
    params = out.get("parameters")
    if isinstance(params, dict):
        for k, v in params.items():
            if isinstance(k, str):
                doc["parameters"][k] = v
    meta = out.get("parameter_meta")
    if isinstance(meta, dict):
        doc.setdefault("parameter_meta", {}).update({k: v for k, v in meta.items() if isinstance(v, dict)})
    rules = out.get("rules")
    if isinstance(rules, list) and rules:
        doc["rules"] = [r for r in rules if isinstance(r, dict)]
    return doc


def _remove_orphans(doc: dict, keep: set) -> None:
    for w in validate(doc).warnings:
        if w.message == "defined but never referenced" and w.path.startswith("parameters."):
            name = w.path.split(".", 1)[1]
            if name not in keep:
                doc["parameters"].pop(name, None)
                doc.get("parameter_meta", {}).pop(name, None)


def read_llm_full(text: str, base: dict, label: str, det: "_Full"):
    """LLM patch for a full document, repaired and checked against the deterministic reading.
    Returns (doc, unsupported, repaired) or None when the LLM result cannot be trusted."""
    schema = ('{"parameters": {changed or new parameter values}, "parameter_meta": {new parameter: {clause,label,unit}}, '
              '"rules": [ordered rules], "effective_from": "YYYY-MM-DD" or null, "unsupported": ["row", ...]}')
    system = _full_prompt(base)
    user = f"Current policy JSON:\n{json.dumps(base, ensure_ascii=False)}\n\nNew policy document:\n{text}"
    out = llm.complete_json(system, user, schema, max_tokens=6000, timeout=90)
    unsupported = [str(u) for u in out.get("unsupported") or [] if str(u).strip()]
    doc = _stamp(_apply_patch(base, out), base, label, None)
    dropped = _drop_invalid_rules(doc)
    repaired = False
    for _ in range(2):
        errors = validate(doc).errors
        if not errors:
            break
        repair = (f"{user}\n\nYour previous patch gave a policy with these validation errors:\n"
                  + "\n".join(str(e) for e in errors) + f"\n\nPrevious rules:\n{json.dumps(doc['rules'])}\n"
                  "Return a corrected patch.")
        try:
            out2 = llm.complete_json(system, repair, schema, max_tokens=6000, timeout=90)
        except llm.LLMUnavailable:
            break
        cand = _stamp(_apply_patch(base, out2), base, label, None)
        _drop_invalid_rules(cand)
        if len(validate(cand).errors) < len(errors):
            doc, repaired = cand, True
            unsupported += [str(u) for u in out2.get("unsupported") or [] if str(u).strip()]
    if validate(doc).errors:
        return None
    wanted = _referenced_params(det.doc)
    if not wanted <= _referenced_params(doc):
        return None                       # the reply dropped references to parameters the document uses
    det_routes = {r["outcome"]["route"] for r in det.doc["rules"]}
    if not det_routes <= {r["outcome"]["route"] for r in doc["rules"]}:
        return None
    for name, value in det.extracted.items():    # numbers read straight from the text win over the model's
        if name in doc["parameters"]:
            doc["parameters"][name] = value
    _remove_orphans(doc, wanted)
    if validate(doc).errors:
        return None
    return doc, unsupported + dropped, repaired


def _base_with_parameters(base: dict, extracted: dict) -> dict:
    doc = copy.deepcopy(base)
    for name, value in extracted.items():
        if name in doc["parameters"]:
            doc["parameters"][name] = value
    return doc


def read_full_policy(text: str, base: dict, *, label: str, plants: dict, mode: str = "auto") -> ReaderResult:
    det = _Full(base, plants).run(text)
    stated = effective_date(text)
    eff = stated.isoformat() if stated else None
    doc, rmode, llm_error = det.doc, "deterministic", None
    extra: list[str] = []
    if mode != "fallback" and not det.complete:
        try:
            got = read_llm_full(text, base, label, det)
            if got is not None:
                doc, extra, repaired = got
                rmode = "llm+repair" if repaired else "llm"
        except llm.LLMUnavailable as exc:
            llm_error = str(exc)
    stamped = _stamp(doc, base, label, eff)
    if validate(stamped).errors:     # last resort: previous rules with only the parameter changes read from the text
        stamped = _stamp(_base_with_parameters(base, det.extracted), base, label, eff)
        rmode = "base+parameters"
    informational = list(det.informational)
    known = [_norm(p) for p in informational]
    unrecognised = list(det.unrecognised)
    for u in extra:
        n = _norm(u)
        if n and not any(n in k or k in n for k in known if len(k) > 10):
            unrecognised.append(u)
    res = ReaderResult(stamped, eff, rmode, unrecognised, list(det.applied), llm_error, informational, "full")
    return res
