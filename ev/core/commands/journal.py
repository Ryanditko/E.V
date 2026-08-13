"""Journal entries."""

from __future__ import annotations

from datetime import datetime


class JournalMixin:
    def diario(self, user_id: str, argstr: str) -> str:
        text = argstr.strip()
        if not text:
            entries = self._memory.recent_journal(user_id, 5)
            if not entries:
                return "Diário vazio. Escreva com /diario <texto>."
            lines = ["📔 Últimas entradas do diário:"]
            for e in entries:
                day = ""
                try:
                    day = datetime.fromisoformat(e["created"]).strftime("%d/%m")
                except Exception:
                    pass
                lines.append(f"#{e['id']} [{day}] {e['text']}")
            lines.append("\nApagar: /diariorm <id>")
            return "\n".join(lines)
        self._memory.add_journal(user_id, text)
        return "Anotado no diário."

    def diariorm(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /diariorm <id>. Veja os ids em /diario."
        ok = self._memory.delete_journal(user_id, int(arg))
        return f"Entrada #{arg} apagada." if ok else f"Não achei a entrada #{arg}."
