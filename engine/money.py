"""Money helpers. Every amount is a Decimal; floats never touch money."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PAISE = Decimal("0.01")
RUPEE_SIGN = "\u20b9"


class MoneyError(ValueError):
    pass


def to_decimal(value) -> Decimal:
    """Parse text or a number into a Decimal. Raises MoneyError on bad input."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise MoneyError(f"not an amount: {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    if not text:
        raise MoneyError("empty amount")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise MoneyError(f"not an amount: {value!r}") from exc
    if not result.is_finite():
        raise MoneyError(f"not an amount: {value!r}")
    return result


def quantize(value: Decimal) -> Decimal:
    """Round to paise, half up."""
    return to_decimal(value).quantize(PAISE, rounding=ROUND_HALF_UP)


def fmt_plain(value: Decimal | None) -> str:
    """Plain 2-dp string for CSV output; blank for None."""
    if value is None:
        return ""
    return f"{quantize(value)}"


def fmt_inr(value: Decimal | None) -> str:
    """Indian grouping with the rupee sign, e.g. 1234567.5 -> \u20b912,34,567.50."""
    if value is None:
        return ""
    q = quantize(value)
    sign = "-" if q < 0 else ""
    whole, frac = f"{abs(q):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join(groups + [tail]) if groups else tail
    return f"{sign}{RUPEE_SIGN}{grouped}.{frac}"
