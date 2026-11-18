"""Indian rupee amounts in free text: "₹3 lakh", "Rs 7,50,000", "2.5L", "1 crore", "INR 20,00,000"."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

UNITS = {"lakh": Decimal(10) ** 5, "lakhs": Decimal(10) ** 5, "lac": Decimal(10) ** 5, "lacs": Decimal(10) ** 5,
         "l": Decimal(10) ** 5, "crore": Decimal(10) ** 7, "crores": Decimal(10) ** 7, "cr": Decimal(10) ** 7,
         "k": Decimal(10) ** 3}

_AMOUNT = re.compile(
    r"(?P<cur>₹|\brs\.?|\binr)?\s*(?<![\w.,])(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<unit>lakhs?|lacs?|crores?|cr|l|k)?\b",
    re.I)


def _to_decimal(num: str) -> Decimal | None:
    try:
        return Decimal(num.replace(",", ""))
    except InvalidOperation:
        return None


def find_amounts(text: str, *, require_marker: bool = True) -> list[tuple[Decimal, int, int]]:
    """Every money amount in the text as (value, start, end). Without a currency sign, a lakh/crore unit
    or Indian digit grouping, a bare number is only an amount when require_marker is False."""
    out = []
    for mt in _AMOUNT.finditer(text or ""):
        num, cur, unit = mt.group("num"), mt.group("cur"), (mt.group("unit") or "").lower()
        value = _to_decimal(num)
        if value is None:
            continue
        marked = bool(cur) or bool(unit) or ("," in num)
        if require_marker and not marked:
            continue
        if unit:
            value = value * UNITS[unit]
        out.append((value, mt.start(), mt.end()))
    return out


def parse_inr(text: str) -> Decimal | None:
    """The single amount in a short text such as '₹3 lakh' or '750000'."""
    found = find_amounts(text, require_marker=False)
    return found[-1][0] if found else None
