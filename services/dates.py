"""IST dates and relative-date phrases. All date arithmetic for chat happens here, never in the LLM."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_WEEKDAY = r"(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(day|nesday|sday|rsday|urday)?"

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_D_MON = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH + r"(?:,?\s+(\d{4}))?", re.I)
_MON_D = re.compile(r"\b" + _MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", re.I)
_IN_N = re.compile(r"\bin\s+(\d{1,3})\s+(day|days|week|weeks)\b", re.I)
_NEXT_WD = re.compile(r"\bnext\s+" + _WEEKDAY + r"\b", re.I)
_WD = re.compile(r"\b(?:by|this|on|before|coming)?\s*" + _WEEKDAY + r"\b", re.I)
_EFFECTIVE = re.compile(r"\beffective\b(?:\s+(?:from|on|as of|date))?\s*[:\-]?\s*(.{0,40})", re.I)


def now_ist() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def today_ist() -> date:
    """Today in IST. APP_TODAY=YYYY-MM-DD overrides it for demos and tests."""
    override = os.environ.get("APP_TODAY", "").strip()
    if override:
        return date.fromisoformat(override)
    return now_ist().date()


def _month(text: str) -> int:
    return MONTHS.index(text[:3].lower()) + 1


def _weekday(text: str) -> int:
    t = text.lower()[:3]
    return [w[:3] for w in WEEKDAYS].index(t)


def _safe(y: int, mth: int, d: int) -> date | None:
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def _year(y: str | None) -> int | None:
    if not y:
        return None
    n = int(y)
    return n + 2000 if n < 100 else n


def absolute_date(text: str, today: date | None = None) -> date | None:
    """An explicit calendar date: ISO, DD/MM/YYYY, '20 Nov [2026]', 'Nov 20 [2026]'."""
    t = text or ""
    if mt := _ISO.search(t):
        return _safe(int(mt.group(1)), int(mt.group(2)), int(mt.group(3)))
    if mt := _DMY.search(t):
        return _safe(_year(mt.group(3)), int(mt.group(2)), int(mt.group(1)))
    for rx, day_g, mon_g, year_g in ((_D_MON, 1, 2, 3), (_MON_D, 2, 1, 3)):
        if mt := rx.search(t):
            day, mon, year = int(mt.group(day_g)), _month(mt.group(mon_g)), _year(mt.group(year_g))
            if year is not None:
                return _safe(year, mon, day)
            today = today or today_ist()
            d = _safe(today.year, mon, day)
            if d is not None and d < today:
                d = _safe(today.year + 1, mon, day)
            return d
    return None


def resolve(text: str, today: date) -> date | None:
    """A need-by phrase relative to today (IST)."""
    t = (text or "").lower()
    found = absolute_date(t, today)
    if found:
        return found
    if re.search(r"\bday after tomorrow\b", t):
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b", t):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b", t):
        return today
    if mt := _IN_N.search(t):
        n = int(mt.group(1))
        return today + timedelta(days=n * (7 if mt.group(2).startswith("week") else 1))
    if mt := _NEXT_WD.search(t):
        next_monday = today + timedelta(days=len(WEEKDAYS) - today.weekday())
        return next_monday + timedelta(days=_weekday(mt.group(1)))
    if mt := _WD.search(t):
        wd = _weekday(mt.group(1))
        return today + timedelta(days=(wd - today.weekday()) % len(WEEKDAYS))
    return None


def effective_date(text: str) -> date | None:
    """'effective from 1 December 2026' / 'effective 2026-12-01' / 'effective on 01/12/2026'."""
    for mt in _EFFECTIVE.finditer(text or ""):
        d = absolute_date(mt.group(1))
        if d:
            return d
    return None


def long_date(d: date | None) -> str:
    return "" if d is None else f"{d.day} {d.strftime('%b %Y')}"


def with_weekday(d: date | None) -> str:
    return "" if d is None else f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"
