"""Hand-written policy validator. Every unknown key, fact, op, strategy or parameter is reported."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .conditions import GROUP_KEYS, LEAF_KEYS, LIST_OPS, OP_FACT_TYPES, OPS, param_name, unescape
from .facts import FACTS
from .parameters import (PARAM_RULES, REQUIRED_PARAMETERS, SUGGESTION_COUNT_RULE, describe, is_int,
                         is_number)
from .strategies import STRATEGIES

SCHEMA_VERSION = 1
TOP_LEVEL_REQUIRED = ("schema_version", "version", "effective_from", "parameters", "rules")
TOP_LEVEL_OPTIONAL = ("title", "source", "parameter_meta")
RULE_KEYS = ("id", "clause", "text", "when", "outcome")
OUTCOME_REQUIRED = ("decision", "route", "supplier")
OUTCOME_OPTIONAL = ("note",)
SUPPLIER_REQUIRED = ("strategy",)
SUPPLIER_OPTIONAL = ("count",)
PARAMETER_META_KEYS = ("clause", "label", "unit")
KNOWN_DECISIONS = ("PO", "SOURCING_REQUEST")
MAX_VERSION_LEN = 20
MAX_LABEL_LEN = 64
WEIGHT_PARAMS = ("ranking_weights", "topup_weights")

TYPE_EXPECT = {
    "decimal": "a number",
    "int": "an integer",
    "date": "a YYYY-MM-DD date string",
    "bool": "true or false",
    "string": "a string",
}


@dataclass(frozen=True)
class Issue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message

    def as_dict(self) -> dict:
        return {"path": self.path, "message": self.message}


@dataclass
class ValidationResult:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"errors": [e.as_dict() for e in self.errors], "warnings": [w.as_dict() for w in self.warnings]}


class PolicyValidationError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("Policy is invalid:\n" + "\n".join(f"- {e}" for e in self.errors))


def _type_ok(value, fact_type: str) -> bool:
    if fact_type == "decimal":
        return is_number(value)
    if fact_type == "int":
        return is_int(value) or (is_number(value) and Decimal(str(value)) == Decimal(str(value)).to_integral_value())
    if fact_type == "bool":
        return isinstance(value, bool)
    if fact_type == "string":
        return isinstance(value, str)
    if fact_type == "date":
        if not isinstance(value, str):
            return False
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return len(value) == len("YYYY-MM-DD")
    return False


def _is_scalar(v) -> bool:
    return v is None or isinstance(v, (str, bool, int, float, Decimal))


class _Validator:
    def __init__(self, doc, base):
        self.doc = doc
        self.base = base
        self.result = ValidationResult()
        self.params: dict = {}
        self.referenced_params: set = set()
        self.referenced_facts: dict = {}     # fact -> first rule index

    def err(self, path, msg):
        self.result.errors.append(Issue(path, msg))

    def warn(self, path, msg):
        self.result.warnings.append(Issue(path, msg))

    # -- top level ---------------------------------------------------------------
    def run(self) -> ValidationResult:
        doc = self.doc
        if not isinstance(doc, dict):
            self.err("", "policy must be a JSON object")
            return self.result
        for k in doc:
            if k not in TOP_LEVEL_REQUIRED and k not in TOP_LEVEL_OPTIONAL:
                self.err(k, f"unknown top-level key '{k}'")
        sv = doc.get("schema_version")
        if "schema_version" not in doc:
            self.err("schema_version", "required")
        elif not is_int(sv) or sv != SCHEMA_VERSION:
            self.err("schema_version", f"must be {SCHEMA_VERSION}; got {describe(sv)}")
        if "version" not in doc:
            self.err("version", "required")
        else:
            v = doc["version"]
            if not isinstance(v, str) or not v.strip() or len(v) > MAX_VERSION_LEN:
                self.err("version", f"must be a non-empty string of at most {MAX_VERSION_LEN} characters; got {describe(v)}")
        if "effective_from" not in doc:
            self.err("effective_from", "required (use null for a draft without a date)")
        elif doc["effective_from"] is None:
            self.warn("effective_from", "not set; an effective date is needed before approval")
        elif not _type_ok(doc["effective_from"], "date"):
            self.err("effective_from", "must be YYYY-MM-DD")
        if "title" in doc and not isinstance(doc["title"], str):
            self.err("title", "must be a string")
        if "source" in doc and not isinstance(doc["source"], dict):
            self.err("source", "must be an object")

        params = doc.get("parameters")
        if not isinstance(params, dict):
            self.err("parameters", "required object missing")
            params = {}
        self.params = params
        self.check_parameter_values()
        self.check_required_parameters()
        self.check_parameter_meta()

        rules = doc.get("rules")
        if not isinstance(rules, list) or not rules:
            self.err("rules", "must be a non-empty list")
            rules = []
        self.check_rules(rules)
        self.check_fact_dependencies()
        self.check_warnings(rules)
        return self.result

    # -- parameters -----------------------------------------------------------
    def check_parameter_values(self):
        for name, v in self.params.items():
            path = f"parameters.{name}"
            if _is_scalar(v):
                continue
            if isinstance(v, list) and all(_is_scalar(x) and x is not None for x in v):
                continue
            if isinstance(v, dict) and all(is_number(x) for x in v.values()):
                continue
            self.err(path, "must be a scalar, a list of scalars or an object of numbers")

    def check_required_parameters(self):
        for name in sorted(REQUIRED_PARAMETERS):
            rule = PARAM_RULES[name]
            path = f"parameters.{name}"
            if name not in self.params:
                self.err(path, f"required, must be {rule.expect}")
                continue
            problem = rule.problem(self.params[name], self.params)
            if problem:
                self.err(path, f"required, {problem}")

    def check_parameter_meta(self):
        meta = self.doc.get("parameter_meta")
        if meta is None:
            return
        if not isinstance(meta, dict):
            self.err("parameter_meta", "must be an object")
            return
        for name, entry in meta.items():
            path = f"parameter_meta.{name}"
            if name not in self.params:
                self.warn(path, "no such parameter")
            if not isinstance(entry, dict):
                self.err(path, "must be an object with optional keys " + ", ".join(PARAMETER_META_KEYS))
                continue
            for k, v in entry.items():
                if k not in PARAMETER_META_KEYS:
                    self.err(path, f"unknown key '{k}'; allowed: " + ", ".join(PARAMETER_META_KEYS))
                elif not isinstance(v, str):
                    self.err(f"{path}.{k}", "must be a string")

    # -- rules ----------------------------------------------------------------
    def check_rules(self, rules):
        seen_ids = {}
        consolidate = self.params.get("consolidate_decisions")
        consolidate = consolidate if isinstance(consolidate, list) else []
        for i, rule in enumerate(rules):
            path = f"rules[{i}]"
            if not isinstance(rule, dict):
                self.err(path, "a rule must be an object with keys " + ", ".join(RULE_KEYS))
                continue
            for k in rule:
                if k not in RULE_KEYS:
                    self.err(path, f"unknown key '{k}'; a rule has exactly " + ", ".join(RULE_KEYS))
            for k in ("id", "clause", "text"):
                if k not in rule:
                    self.err(f"{path}.{k}", "required")
                elif not isinstance(rule[k], str) or not rule[k].strip():
                    self.err(f"{path}.{k}", f"must be a non-empty string; got {describe(rule[k])}")
            rid = rule.get("id")
            if isinstance(rid, str) and rid.strip():
                if rid in seen_ids:
                    self.err(f"{path}.id", f"duplicate rule id '{rid}' (also rules[{seen_ids[rid]}])")
                else:
                    seen_ids[rid] = i
            if "when" not in rule:
                self.err(f"{path}.when", "required")
            else:
                self.check_node(rule["when"], f"{path}.when", i)
            if "outcome" not in rule:
                self.err(f"{path}.outcome", "required")
            else:
                self.check_outcome(rule["outcome"], f"{path}.outcome", consolidate)

    def check_node(self, node, path, rule_idx):
        if not isinstance(node, dict):
            self.err(path, "a condition must be an object with exactly one of 'all', 'any' or 'fact'")
            return
        groups = [k for k in GROUP_KEYS if k in node]
        if groups:
            if len(node) != 1:
                extra = [k for k in node if k != groups[0]]
                self.err(path, "a condition must have exactly one of 'all', 'any' or 'fact'; "
                               "unexpected " + ", ".join(f"'{k}'" for k in extra))
            kind = groups[0]
            children = node[kind]
            if not isinstance(children, list) or not children:
                self.err(f"{path}.{kind}", "must be a non-empty list")
                return
            for j, child in enumerate(children):
                self.check_node(child, f"{path}.{kind}[{j}]", rule_idx)
            return
        if "fact" not in node:
            self.err(path, "a condition must have exactly one of 'all', 'any' or 'fact'")
            return
        self.check_leaf(node, path, rule_idx)

    def check_leaf(self, node, path, rule_idx):
        for k in node:
            if k not in LEAF_KEYS:
                self.err(path, f"unknown key '{k}'; a condition leaf has exactly fact, op, value")
        fact_name = node.get("fact")
        fdef = None
        if not isinstance(fact_name, str) or fact_name not in FACTS:
            self.err(f"{path}.fact", f"unknown fact {describe(fact_name) if not isinstance(fact_name, str) else repr(fact_name)}. "
                                     f"Known facts: {', '.join(sorted(FACTS))}")
        else:
            fdef = FACTS[fact_name]
            self.referenced_facts.setdefault(fact_name, rule_idx)
        op = node.get("op")
        op_ok = False
        if "op" not in node:
            self.err(f"{path}.op", "required")
        elif not isinstance(op, str) or op not in OPS:
            self.err(f"{path}.op", f"unknown op {repr(op) if isinstance(op, str) else describe(op)}. "
                                   f"Allowed: {', '.join(OPS)}")
        else:
            op_ok = True
            if fdef is not None and fdef.type not in OP_FACT_TYPES[op]:
                self.err(path, f"op '{op}' is not valid for {fdef.type} fact '{fact_name}'")
                op_ok = False
        if "value" not in node:
            self.err(f"{path}.value", "required")
            return
        raw = node["value"]
        pname = param_name(raw)
        if pname is not None:
            self.referenced_params.add(pname)
            if pname not in self.params:
                self.err(f"{path}.value", f"parameter '{raw}' is not defined in parameters")
                return
        if fdef is None or not op_ok:
            return
        value = self.params[pname] if pname is not None else unescape(raw)
        self.check_value(value, fdef.type, fact_name, op, f"{path}.value", pname)

    def check_value(self, value, ftype, fact_name, op, path, pname):
        prefix = f"parameter '{pname}' must be" if pname else None
        if op in LIST_OPS:
            if not isinstance(value, list):
                if pname:
                    self.err(path, f"{prefix} a list for op '{op}'; got {describe(value)}")
                else:
                    self.err(path, f"op '{op}' needs a list; got {describe(value)}")
                return
            for k, el in enumerate(value):
                if el is None or not _type_ok(el, ftype):
                    where = f"parameter '{pname}' item {k}" if pname else f"item {k}"
                    self.err(path, f"{where} must be {TYPE_EXPECT[ftype]} for {ftype} fact '{fact_name}'; got {describe(el)}")
            return
        if value is None:
            if op in ("eq", "ne"):
                return
            if pname:
                self.err(path, f"{prefix} {TYPE_EXPECT[ftype]} for {ftype} fact '{fact_name}'; got null")
            else:
                self.err(path, f"fact '{fact_name}' is {ftype}; got null (only eq/ne accept null)")
            return
        if not _type_ok(value, ftype):
            if pname:
                self.err(path, f"{prefix} {TYPE_EXPECT[ftype]} for {ftype} fact '{fact_name}'; got {describe(value)}")
            else:
                self.err(path, f"fact '{fact_name}' is {ftype}; got {describe(value)}")

    def check_outcome(self, outcome, path, consolidate):
        if not isinstance(outcome, dict):
            self.err(path, "must be an object with keys " + ", ".join(OUTCOME_REQUIRED))
            return
        for k in outcome:
            if k not in OUTCOME_REQUIRED and k not in OUTCOME_OPTIONAL:
                self.err(path, f"unknown key '{k}'; an outcome has decision, route, supplier and optional note")
        for k in ("decision", "route"):
            v = outcome.get(k)
            if k not in outcome:
                self.err(f"{path}.{k}", "required")
            elif not isinstance(v, str) or not v.strip() or len(v) > MAX_LABEL_LEN:
                self.err(f"{path}.{k}", f"must be a non-empty string of at most {MAX_LABEL_LEN} characters; got {describe(v)}")
        if "note" in outcome and not isinstance(outcome["note"], str):
            self.err(f"{path}.note", "must be a string")
        decision = outcome.get("decision")
        if isinstance(decision, str) and decision.strip() and decision not in KNOWN_DECISIONS:
            self.warn(f"{path}.decision", f"decision '{decision}' is not one of {', '.join(KNOWN_DECISIONS)}")
        sup = outcome.get("supplier")
        spath = f"{path}.supplier"
        if "supplier" not in outcome:
            self.err(spath, "required")
            return
        if not isinstance(sup, dict):
            self.err(spath, "must be an object with keys strategy and optional count")
            return
        for k in sup:
            if k not in SUPPLIER_REQUIRED and k not in SUPPLIER_OPTIONAL:
                self.err(spath, f"unknown key '{k}'; supplier has strategy and optional count")
        strategy = sup.get("strategy")
        if "strategy" not in sup:
            self.err(f"{spath}.strategy", "required")
            return
        if not isinstance(strategy, str) or strategy not in STRATEGIES:
            self.err(f"{spath}.strategy", f"unknown strategy {repr(strategy) if isinstance(strategy, str) else describe(strategy)}. "
                                          f"Allowed: {', '.join(STRATEGIES)}")
            return
        sdef = STRATEGIES[strategy]
        if sdef.count == "required":
            if "count" not in sup:
                self.err(f"{spath}.count", f"strategy '{strategy}' needs a count")
            else:
                self.check_count(sup["count"], f"{spath}.count")
        elif "count" in sup:
            self.err(f"{spath}.count", f"strategy '{strategy}' does not take a count")
        if isinstance(decision, str) and decision in consolidate and not sdef.gives_supplier:
            self.err(path, f"decision '{decision}' is in consolidate_decisions and needs a supplier; "
                           f"strategy '{strategy}' gives none")

    def check_count(self, count, path):
        pname = param_name(count)
        if pname is not None:
            self.referenced_params.add(pname)
            if pname not in self.params:
                self.err(path, f"parameter '{count}' is not defined in parameters")
                return
            problem = SUGGESTION_COUNT_RULE.problem(self.params[pname], self.params)
            if problem:
                self.err(path, f"parameter '{pname}' {problem}")
            return
        problem = SUGGESTION_COUNT_RULE.problem(count, self.params)
        if problem:
            self.err(path, problem)

    # -- facts and warnings ------------------------------------------------------
    def check_fact_dependencies(self):
        for fact_name, idx in self.referenced_facts.items():
            for pname in FACTS[fact_name].params:
                rule = PARAM_RULES.get(pname)
                if pname in REQUIRED_PARAMETERS:
                    continue     # already checked as a required parameter
                expect = rule.expect if rule else "defined"
                if pname not in self.params:
                    self.err(f"rules[{idx}]", f"fact '{fact_name}' needs parameter '{pname}' ({expect})")
                elif rule is not None:
                    problem = rule.problem(self.params[pname], self.params)
                    if problem:
                        self.err(f"rules[{idx}]", f"fact '{fact_name}' needs parameter '{pname}' ({expect}); "
                                                  f"got {describe(self.params[pname])}")

    def check_warnings(self, rules):
        needed = set(REQUIRED_PARAMETERS) | self.referenced_params
        for f in self.referenced_facts:
            needed |= set(FACTS[f].params)
        for name in self.params:
            if name not in needed:
                self.warn(f"parameters.{name}", "defined but never referenced")
        for name in WEIGHT_PARAMS:
            w = self.params.get(name)
            if isinstance(w, dict) and w and all(is_number(x) for x in w.values()):
                total = sum(Decimal(str(x)) for x in w.values())
                if total != Decimal(1):
                    self.warn(f"parameters.{name}", f"weights sum to {total}, not 1")
        tb = self.params.get("ranking_tie_break")
        if isinstance(tb, list) and "supplier_id" not in tb:
            self.warn("parameters.ranking_tie_break", "supplier_id is not listed; it is applied last so the order stays total")
        cd = self.params.get("consolidate_decisions")
        if isinstance(cd, list) and not cd:
            self.warn("parameters.consolidate_decisions", "empty: no decision receives a PO number")
        seen_when = {}
        for i, r in enumerate(rules):
            if not isinstance(r, dict) or "when" not in r:
                continue
            key = json.dumps(r["when"], sort_keys=True, default=str)
            if key in seen_when:
                self.warn(f"rules[{i}].when", f"identical to rules[{seen_when[key]}].when; this rule can only fire "
                                              "when the earlier rule's strategy is not fulfilled")
            else:
                seen_when[key] = i
        if isinstance(self.base, dict):
            base_routes = {r.get("outcome", {}).get("route") for r in self.base.get("rules", []) if isinstance(r, dict)}
            for i, r in enumerate(rules):
                route = r.get("outcome", {}).get("route") if isinstance(r, dict) and isinstance(r.get("outcome"), dict) else None
                if isinstance(route, str) and route not in base_routes:
                    self.warn(f"rules[{i}].outcome.route", f"new route '{route}' not used in the previous version")


def validate(doc, base: dict | None = None) -> ValidationResult:
    return _Validator(doc, base).run()


def validate_or_raise(doc, base: dict | None = None) -> ValidationResult:
    result = validate(doc, base)
    if result.errors:
        raise PolicyValidationError(result.errors)
    return result
