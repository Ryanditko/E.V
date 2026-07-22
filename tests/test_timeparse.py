"""Tests for the deterministic time parser used by slash commands."""

from datetime import datetime
from zoneinfo import ZoneInfo

from ev.core.timeparse import parse_when

NOW = datetime(2026, 7, 22, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def test_relative_minutes():
    dt, rest = parse_when("10m tomar água", NOW)
    assert rest == "tomar água"
    assert (dt - NOW).total_seconds() == 600


def test_relative_hours():
    dt, rest = parse_when("2h reunião", NOW)
    assert (dt - NOW).total_seconds() == 7200
    assert rest == "reunião"


def test_amanha():
    dt, rest = parse_when("amanhã 09:00 reunião", NOW)
    assert dt.day == 23 and dt.hour == 9 and dt.minute == 0
    assert rest == "reunião"


def test_explicit_date():
    dt, rest = parse_when("25/12 14:30 natal", NOW)
    assert dt.month == 12 and dt.day == 25 and dt.hour == 14 and dt.minute == 30
    assert rest == "natal"


def test_unparseable():
    dt, rest = parse_when("xyz sem tempo", NOW)
    assert dt is None
    assert rest == "xyz sem tempo"
