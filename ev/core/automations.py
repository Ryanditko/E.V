"""Deterministic automations engine — "quando X, faça Y".

Pure trigger predicates (no I/O, no LLM) so they're cheap and unit-testable.
The scheduler (telegram_bot) resolves data + performs the side effects; this
module only decides *whether* a trigger fires and describes automations.
"""
from __future__ import annotations

TRIGGERS = ("time", "expense_over", "task_overdue")
ACTIONS = ("notify", "command", "reschedule", "play")

_WD_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


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


def describe(auto: dict) -> str:
    """Human-readable one-liner for listings."""
    t, c = auto.get("trig"), auto.get("trig_cfg") or {}
    a, ac = auto.get("act"), auto.get("act_cfg") or {}
    if t == "time":
        wd = c.get("weekday", -1)
        when = "todo dia" if wd == -1 else f"toda {_WD_PT[wd]}"
        quando = f"{when} às {int(c.get('hour', 0)):02d}:{int(c.get('minute', 0)):02d}"
    elif t == "expense_over":
        cat = c.get("category")
        quando = f"quando gastar mais de R$ {float(c.get('amount', 0)):.0f}" + (
            f" em '{cat}'" if cat else "")
    elif t == "task_overdue":
        quando = "quando uma tarefa vencer"
    else:
        quando = t or "?"
    if a == "notify":
        faca = f"me avisar: \"{ac.get('message', '')}\""
    elif a == "command":
        faca = f"rodar /{ac.get('command', '')}"
    elif a == "reschedule":
        faca = "remarcar pro dia seguinte"
    elif a == "play":
        faca = f"tocar '{ac.get('playlist') or ac.get('query') or '?'}' no Spotify"
    else:
        faca = a or "?"
    status = "" if auto.get("enabled", True) else " (pausada)"
    return f"#{auto.get('id', '?')} — {quando} → {faca}{status}"
