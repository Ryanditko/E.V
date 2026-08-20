"""Habits: streaks, create/mark/list/delete."""

from __future__ import annotations

from datetime import timedelta

from ..i18n import plural as _plural
from ..i18n import t as _t


class HabitsMixin:
    def _streak(self, habit_id: int, today) -> int:
        days = self._memory.habit_days(habit_id)
        streak, d = 0, today
        if d.strftime("%Y-%m-%d") not in days:
            d = d - timedelta(days=1)  # today not done yet: count up to yesterday
        while d.strftime("%Y-%m-%d") in days:
            streak += 1
            d = d - timedelta(days=1)
        return streak

    def habito(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        name = argstr.strip()
        if not name:
            return _t(lang, "hab.create_usage")
        if self._memory.find_habit(user_id, name):
            return _t(lang, "hab.exists", name=name)
        self._memory.add_habit(user_id, name)
        return _t(lang, "hab.created", name=name)

    def feito(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        name = argstr.strip()
        if not name:
            return _t(lang, "hab.done_usage")
        h = self._memory.find_habit(user_id, name)
        if not h:
            return _t(lang, "hab.not_found_create", name=name)
        today = self._now().date()
        ok = self._memory.log_habit(h["id"], today.strftime("%Y-%m-%d"))
        streak = _plural(lang, "count.days", self._streak(h["id"], today))
        if not ok:
            return _t(lang, "hab.already", name=h["name"], streak=streak)
        return _t(lang, "hab.done", name=h["name"], streak=streak)

    def habitos(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        habits = self._memory.list_habits(user_id)
        if not habits:
            return _t(lang, "hab.none")
        today = self._now().date()
        today_s = today.strftime("%Y-%m-%d")
        lines = [_t(lang, "hab.list_title")]
        for h in habits:
            done = "[x]" if today_s in self._memory.habit_days(h["id"]) else "[ ]"
            streak = _plural(lang, "count.days", self._streak(h["id"], today))
            lines.append(_t(lang, "hab.list_line", done=done, name=h["name"], streak=streak))
        lines.append(_t(lang, "hab.list_footer"))
        return "\n".join(lines)

    def habitorm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        name = argstr.strip()
        if not name:
            return _t(lang, "hab.rm_usage")
        h = self._memory.find_habit(user_id, name)
        if not h:
            return _t(lang, "hab.not_found", name=name)
        self._memory.delete_habit(user_id, h["id"])
        return _t(lang, "hab.removed", name=h["name"])
