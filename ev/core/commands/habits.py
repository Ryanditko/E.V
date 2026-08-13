"""Habits: streaks, create/mark/list/delete."""

from __future__ import annotations

from datetime import timedelta


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
        name = argstr.strip()
        if not name:
            return "Uso: /habito <nome>. Ex: /habito treino"
        if self._memory.find_habit(user_id, name):
            return f"O hábito '{name}' já existe."
        self._memory.add_habit(user_id, name)
        return f"Hábito '{name}' criado. Marque como feito com /feito {name}"

    def feito(self, user_id: str, argstr: str) -> str:
        name = argstr.strip()
        if not name:
            return "Uso: /feito <nome do hábito>. Ex: /feito treino"
        h = self._memory.find_habit(user_id, name)
        if not h:
            return f"Não achei o hábito '{name}'. Crie com /habito {name}"
        today = self._now().date()
        ok = self._memory.log_habit(h["id"], today.strftime("%Y-%m-%d"))
        streak = self._streak(h["id"], today)
        if not ok:
            return f"'{h['name']}' já estava marcado hoje. Sequência: {streak} dia(s)."
        return f"Boa! '{h['name']}' feito hoje. Sequência: {streak} dia(s)."

    def habitos(self, user_id: str) -> str:
        habits = self._memory.list_habits(user_id)
        if not habits:
            return "Você não tem hábitos. Crie com /habito <nome>."
        today = self._now().date()
        today_s = today.strftime("%Y-%m-%d")
        lines = ["✅ Seus hábitos (hoje):"]
        for h in habits:
            done = "[x]" if today_s in self._memory.habit_days(h["id"]) else "[ ]"
            lines.append(f"{done} {h['name']} — sequência: {self._streak(h['id'], today)} dia(s)")
        lines.append("\nMarcar: /feito <nome> · Apagar: /habitorm <nome>")
        return "\n".join(lines)

    def habitorm(self, user_id: str, argstr: str) -> str:
        name = argstr.strip()
        if not name:
            return "Uso: /habitorm <nome>. Ex: /habitorm treino"
        h = self._memory.find_habit(user_id, name)
        if not h:
            return f"Não achei o hábito '{name}'."
        self._memory.delete_habit(user_id, h["id"])
        return f"Hábito '{h['name']}' removido."
