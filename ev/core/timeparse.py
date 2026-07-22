"""Deterministic time parsing for slash commands (no LLM involved).

Parses a leading time expression from a string and returns the absolute time
plus the remaining text. Supported forms:

    10m / 10min / 2h / 2horas / 1d / 3dias     (relative to now)
    hoje 18:00 / hoje 18h                        (today at time)
    amanhã 09:00 / amanha 9h                     (tomorrow at time)
    25/12 14:30 / 25/12/2026 14:30 / 25/12       (dated; time defaults to 09:00)

Returns (datetime | None, remaining_text). None means no time was recognized.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_REL = re.compile(
    r"^(\d+)(m|min|mins|minuto|minutos|h|hr|hora|horas|d|dia|dias)$", re.I
)
_TIME = re.compile(r"^(\d{1,2})(?::(\d{2})|h)?$")
_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")


def _parse_time_token(tok: str) -> tuple[int, int] | None:
    m = _TIME.match(tok)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def parse_when(text: str, now: datetime) -> tuple[datetime | None, str]:
    tokens = text.strip().split()
    if not tokens:
        return None, text
    first = tokens[0].lower()

    # Relative: 10m, 2h, 3d
    m = _REL.match(first)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("m"):
            delta = timedelta(minutes=n)
        elif unit.startswith("h"):
            delta = timedelta(hours=n)
        else:
            delta = timedelta(days=n)
        return now + delta, " ".join(tokens[1:])

    # hoje / amanhã + time
    if first in ("hoje", "amanha", "amanhã") and len(tokens) >= 2:
        t = _parse_time_token(tokens[1])
        if t:
            base = now if first == "hoje" else now + timedelta(days=1)
            dt = base.replace(hour=t[0], minute=t[1], second=0, microsecond=0)
            return dt, " ".join(tokens[2:])

    # DD/MM [HH:MM]  (optionally /YYYY)
    md = _DATE.match(first)
    if md:
        day, mon = int(md.group(1)), int(md.group(2))
        year = int(md.group(3)) if md.group(3) else now.year
        if year < 100:
            year += 2000
        hour, minute, rest_start = 9, 0, 1
        if len(tokens) >= 2:
            t = _parse_time_token(tokens[1])
            if t:
                hour, minute, rest_start = t[0], t[1], 2
        try:
            dt = now.replace(
                year=year, month=mon, day=day,
                hour=hour, minute=minute, second=0, microsecond=0,
            )
        except ValueError:
            return None, text
        return dt, " ".join(tokens[rest_start:])

    return None, text
