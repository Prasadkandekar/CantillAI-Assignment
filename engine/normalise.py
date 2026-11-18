"""Row validation and normalisation: raw CSV values -> PRLine, or a NOT_PROCESSED reason."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .matching import Matcher
from .models import NEW_ITEM, PRLine
from .money import MoneyError, to_decimal

CREATED_AT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")


@dataclass(frozen=True)
class Rejected:
    row_index: int
    pr_no: str
    pr_line: str
    reason: str
    resolved_item_code: str = ""
    policy_version: str = ""


def _parse_created(text: str) -> datetime | None:
    for fmt in CREATED_AT_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _join_and(items) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _canonical_urgency(text: str, values) -> str | None:
    if not text:
        return values[0] if values else None
    for v in values:
        if v.lower() == text.lower():
            return v
    return None


def normalise(raw_lines, master, policies, pin=None, as_of=None, matcher: Matcher | None = None):
    """Return (valid PRLines, rejected rows) in input order."""
    matcher = matcher or Matcher(master.items)
    valid, rejected = [], []
    seen = set()
    for raw in raw_lines:
        v = raw.values
        pr_no = v.get("pr_no", "").strip()
        pr_line_text = v.get("pr_line", "").strip()

        def reject(reason, code="", version=""):
            rejected.append(Rejected(raw.row_index, pr_no, pr_line_text, reason, code, version))

        if not pr_no:
            reject("Missing PR number")
            continue
        try:
            pr_line = int(pr_line_text)
        except ValueError:
            pr_line = 0
        if pr_line <= 0:
            reject("PR line must be a positive whole number")
            continue
        key = (pr_no, pr_line)
        if key in seen:
            reject("Duplicate of PR line already in this batch")
            continue
        seen.add(key)
        created = _parse_created(v.get("created_at", "").strip())
        if created is None:
            reject(f"Unparseable created_at '{v.get('created_at', '')}'")
            continue
        need_by = _parse_date(v.get("need_by_date", "").strip())
        if need_by is None:
            reject(f"Unparseable need_by_date '{v.get('need_by_date', '')}'")
            continue
        if need_by < created.date():
            reject("Need-by date is before creation date")
            continue
        policy = policies.select(created.date(), pin=pin, as_of=as_of)
        if policy is None:
            reject(f"No policy version effective on {(as_of or created.date()).isoformat()}")
            continue
        params = policy.params
        version = policy.version
        plant = v.get("plant", "").strip()
        if plant not in master.plants:
            reject(f"Unknown plant {plant or '(blank)'}; policy covers {_join_and(master.plants)}", version=version)
            continue
        try:
            qty = to_decimal(v.get("quantity", ""))
        except MoneyError:
            reject(f"Quantity '{v.get('quantity', '')}' is not a number", version=version)
            continue
        if qty <= 0:
            reject("Quantity must be greater than zero", version=version)
            continue
        urgency = _canonical_urgency(v.get("urgency", "").strip(), params["urgency_values"])
        if urgency is None:
            reject(f"Unknown urgency '{v.get('urgency', '')}'", version=version)
            continue
        est_text = v.get("estimated_unit_price", "").strip()
        estimate = None
        if est_text:
            try:
                estimate = to_decimal(est_text)
            except MoneyError:
                estimate = None
            if estimate is None or estimate < 0:
                reject("estimated_unit_price is not a valid amount", version=version)
                continue
        code = v.get("item_code", "").strip()
        description = v.get("description", "").strip()
        if code and code not in master.items:
            reject(f"Unknown item code '{code}'", version=version)
            continue
        if not code and not description:
            reject("No item code or description", version=version)
            continue
        match = matcher.match(code, description)
        resolved = match.code or NEW_ITEM
        uom = v.get("uom", "").strip()
        if resolved != NEW_ITEM:
            master_uom = master.items[resolved].uom
            if uom.upper() != master_uom.upper():
                reject(f"UoM {uom or '(blank)'} differs from item master UoM {master_uom}", resolved, version)
                continue
            uom = master_uom
        flags = []
        if "urgent_in_text" in match.flags and urgency not in params["emergency_urgency_values"]:
            flags.append("urgent_in_text")
        if "as_per_sample" in match.flags:
            flags.append("as_per_sample")
        if resolved == NEW_ITEM and match.candidates:
            flags.append("low_confidence")
        valid.append(PRLine(
            row_index=raw.row_index, pr_no=pr_no, pr_line=pr_line, created_at=created,
            requester=v.get("requester", "").strip() or None, department=v.get("department", "").strip() or None,
            plant=plant, item_code_raw=code or None, description=description, quantity=qty, uom=uom,
            estimated_unit_price=estimate, need_by=need_by, urgency=urgency, policy_version=version,
            resolved_item_code=resolved, match=match, flags=tuple(flags)))
    return valid, rejected
