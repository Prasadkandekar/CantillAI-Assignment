"""First-match rule walk in list order with strategy fall-through.

Rule ids and clauses are only copied into the trace and reason; they never steer the walk.
"""
from __future__ import annotations

from .conditions import evaluate, jsonable
from .strategies import STRATEGIES

ALWAYS_SHOWN_FACTS = ("group_value", "total_quantity", "line_count", "requirement_date",
                      "is_emergency", "contract_usable")


def walk_rules(policy, ctx):
    """Return (rule, StrategyResult, trace) for the first fulfilled rule, or (None, None, trace)."""
    checked = []
    fired = None
    result = None
    for rule in policy.rules:
        matched, cond_trace = evaluate(rule.when, ctx.fact)
        entry = {"id": rule.id, "clause": rule.clause, "matched": matched, "conditions": cond_trace}
        if matched:
            strategy = rule.outcome["supplier"]["strategy"]
            res = STRATEGIES[strategy].fn(ctx, rule.count)
            entry["strategy"] = strategy
            entry["fulfilled"] = res.fulfilled
            if not res.fulfilled:
                entry["note"] = f"matched but strategy could not be fulfilled: {res.reason}"
                checked.append(entry)
                continue
            checked.append(entry)
            fired, result = rule, res
            break
        checked.append(entry)
    for name in ALWAYS_SHOWN_FACTS:
        ctx.fact(name)
    trace = {
        "policy_version": policy.version,
        "fired": fired.summary if fired else None,
        "rules_checked": checked,
        "facts": {k: jsonable(v) for k, v in ctx.cache.items()},
    }
    return fired, result, trace
