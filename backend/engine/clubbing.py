"""Clubbing PR lines into requirements. Each line is compared with a requirement's first line."""
from __future__ import annotations

from .models import NEW_ITEM, Requirement

CLUB_KEY_FIELDS = ("item_code", "plant", "uom", "department", "requester")
GROUP_ID_FORMAT = "REQ-{:04d}"


def line_sort_key(line):
    return (line.created_at, line.pr_no, line.pr_line)


def _key_value(line, field: str):
    if field == "item_code":
        return line.resolved_item_code
    return getattr(line, field)


def _fits(line, first, params: dict) -> bool:
    if any(_key_value(line, k) != _key_value(first, k) for k in params["club_keys"]):
        return False
    created_gap = (line.created_at.date() - first.created_at.date()).days
    if not (0 <= created_gap <= params["club_created_days"]):
        return False
    return abs((line.need_by - first.need_by).days) <= params["club_needby_days"]


def club(lines, params_for_version: dict) -> list[Requirement]:
    """lines: valid PRLines; params_for_version: version label -> resolved parameters."""
    groups: list[list] = []
    for line in sorted(lines, key=line_sort_key):
        params = params_for_version[line.policy_version]
        is_new = line.resolved_item_code == NEW_ITEM
        target = None
        if not (is_new and not params["club_new_items"]):
            for g in groups:
                first = g[0]
                if first.policy_version != line.policy_version:
                    continue
                if first.resolved_item_code == NEW_ITEM and not params_for_version[first.policy_version]["club_new_items"]:
                    continue
                if _fits(line, first, params_for_version[first.policy_version]):
                    target = g
                    break
        if target is None:
            groups.append([line])
        else:
            target.append(line)
    reqs = []
    for n, g in enumerate(groups, start=1):
        first = g[0]
        reqs.append(Requirement(
            group_id=GROUP_ID_FORMAT.format(n),
            lines=tuple(g),
            item_code=first.resolved_item_code,
            plant=first.plant,
            uom=first.uom,
            requirement_date=first.created_at.date(),
            first_created_at=first.created_at,
            earliest_need_by=min(l.need_by for l in g),
            total_qty=sum((l.quantity for l in g), start=type(first.quantity)(0)),
            policy_version=first.policy_version,
        ))
    return reqs
