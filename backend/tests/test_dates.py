"""Relative dates in IST with a fixed 'today' (a Wednesday)."""
from datetime import date

import pytest

from services import dates

TODAY = date(2026, 11, 18)   # Wednesday


@pytest.mark.parametrize("text,expected", [
    ("today", date(2026, 11, 18)),
    ("tomorrow", date(2026, 11, 19)),
    ("day after tomorrow", date(2026, 11, 20)),
    ("in 5 days", date(2026, 11, 23)),
    ("in 2 weeks", date(2026, 12, 2)),
    ("by Friday", date(2026, 11, 20)),
    ("this friday", date(2026, 11, 20)),
    ("wednesday", date(2026, 11, 18)),
    ("next Friday", date(2026, 11, 27)),
    ("next monday", date(2026, 11, 23)),
    ("20 Nov", date(2026, 11, 20)),
    ("5 Jan", date(2027, 1, 5)),
    ("Dec 3", date(2026, 12, 3)),
    ("20/11/2026", date(2026, 11, 20)),
    ("2026-12-01", date(2026, 12, 1)),
    ("need it by 1st December 2026", date(2026, 12, 1)),
])
def test_resolve(text, expected):
    assert dates.resolve(text, TODAY) == expected


def test_unreadable():
    assert dates.resolve("soonish", TODAY) is None


def test_effective_date_and_display():
    assert dates.effective_date("This amendment is effective from 1 December 2026.") == date(2026, 12, 1)
    assert dates.effective_date("Effective 2026-12-15") == date(2026, 12, 15)
    assert dates.effective_date("effective on 01/12/2026") == date(2026, 12, 1)
    assert dates.effective_date("no date here") is None
    assert dates.long_date(date(2026, 12, 1)) == "1 Dec 2026"
    assert dates.with_weekday(date(2026, 11, 20)) == "Fri 20 Nov 2026"


def test_app_today_override(monkeypatch):
    monkeypatch.setenv("APP_TODAY", "2026-11-16")
    assert dates.today_ist() == date(2026, 11, 16)
