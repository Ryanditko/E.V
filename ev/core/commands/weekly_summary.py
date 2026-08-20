"""Weekly review summary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..i18n import plural as _plural
from ..i18n import t as _t


class WeeklySummaryMixin:
    def semana(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        done = self._memory.tasks_completed_since(user_id, since)
        exp = self._memory.expenses_since(user_id, since)
        total = sum(e["amount"] for e in exp)
        parts = [
            _t(lang, "week.title"),
            _t(lang, "week.done", done=done),
            _t(lang, "week.open", n=len(self._memory.open_tasks(user_id))),
            _t(lang, "week.spent", total=f"{total:.2f}",
               count=_plural(lang, "count.entries", len(exp))),
        ]
        habits = self._memory.list_habits(user_id)
        if habits:
            today = self._now().date()
            parts.append(_t(lang, "week.habits"))
            for h in habits:
                parts.append(_t(lang, "week.habit_line", name=h["name"],
                                streak=_plural(lang, "count.days", self._streak(h["id"], today))))
        return "\n".join(parts)
