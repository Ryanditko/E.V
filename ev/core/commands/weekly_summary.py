"""Weekly review summary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class WeeklySummaryMixin:
    def semana(self, user_id: str) -> str:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        done = self._memory.tasks_completed_since(user_id, since)
        exp = self._memory.expenses_since(user_id, since)
        total = sum(e["amount"] for e in exp)
        parts = [
            "📊 Sua semana:",
            f"✅ Tarefas concluídas: {done}",
            f"📋 Tarefas em aberto: {len(self._memory.open_tasks(user_id))}",
            f"💰 Gastos (7 dias): R$ {total:.2f} ({len(exp)} lançamentos)",
        ]
        habits = self._memory.list_habits(user_id)
        if habits:
            today = self._now().date()
            parts.append("🔥 Hábitos (sequência):")
            for h in habits:
                parts.append(f"  • {h['name']}: {self._streak(h['id'], today)} dia(s)")
        return "\n".join(parts)
