"""Deterministic automations engine — "quando X, faça Y".

Pure trigger predicates (no I/O, no LLM) so they're cheap and unit-testable.
The scheduler (telegram_bot) resolves data + performs the side effects; this
module only decides *whether* a trigger fires and describes automations.
"""
from __future__ import annotations

from .i18n import DEFAULT_LANG
from .i18n import t as _t

TRIGGERS = ("time", "expense_over", "task_overdue")
ACTIONS = ("notify", "command", "reschedule", "play")


def time_due(cfg: dict, now, last_fired: str | None) -> bool:
    """True when a time trigger should fire: right weekday (or daily), at/after
    the target HH:MM, and not already fired today. Robust to a coarse (per-minute)
    scheduler — fires on the first tick at or after the target time."""
    wd = cfg.get("weekday", -1)
    if wd not in (-1, now.weekday()):
        return False
    tgt = (int(cfg.get("hour", 0)), int(cfg.get("minute", 0)))
    if (now.hour, now.minute) < tgt:
        return False
    return last_fired != now.date().isoformat()


def expense_matches(cfg: dict, expense: dict) -> bool:
    """True when an expense meets/exceeds the threshold (and category, if set)."""
    if float(expense.get("amount") or 0) < float(cfg.get("amount", 0)):
        return False
    cat = (cfg.get("category") or "").strip().lower()
    if cat and (expense.get("category") or "").strip().lower() != cat:
        return False
    return True


def describe(auto: dict, lang: str | None = DEFAULT_LANG) -> str:
    """Human-readable one-liner for listings, localized to ``lang``."""
    t, c = auto.get("trig"), auto.get("trig_cfg") or {}
    a, ac = auto.get("act"), auto.get("act_cfg") or {}
    if t == "time":
        wd = c.get("weekday", -1)
        when = (_t(lang, "auto.when_everyday") if wd == -1
                else _t(lang, "auto.when_weekday", wd=_t(lang, f"wd.{wd}")))
        hm = f"{int(c.get('hour', 0)):02d}:{int(c.get('minute', 0)):02d}"
        quando = _t(lang, "auto.time_when", when=when, hm=hm)
    elif t == "expense_over":
        cat = c.get("category")
        quando = _t(lang, "auto.expense_when", amount=f"{float(c.get('amount', 0)):.0f}") + (
            _t(lang, "auto.expense_cat", cat=cat) if cat else "")
    elif t == "task_overdue":
        quando = _t(lang, "auto.task_overdue")
    else:
        quando = t or "?"
    if a == "notify":
        faca = _t(lang, "auto.do_notify", message=ac.get("message", ""))
    elif a == "command":
        faca = _t(lang, "auto.do_command", command=ac.get("command", ""))
    elif a == "reschedule":
        faca = _t(lang, "auto.do_reschedule")
    elif a == "play":
        faca = _t(lang, "auto.do_play", what=ac.get("playlist") or ac.get("query") or "?")
    else:
        faca = a or "?"
    status = "" if auto.get("enabled", True) else _t(lang, "auto.paused")
    return _t(lang, "auto.line", id=auto.get("id", "?"), quando=quando, faca=faca, status=status)
