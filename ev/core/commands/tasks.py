"""Tasks: create, list, complete."""

from __future__ import annotations


class TasksMixin:
    def tarefa(self, user_id: str, argstr: str) -> str:
        text = argstr.strip()
        if not text:
            return "Uso: /tarefa <texto> [#categoria]\nEx: /tarefa estudar cálculo #faculdade"
        # Extract a #category tag (default 'geral').
        category = "geral"
        tokens = text.split()
        tags = [t for t in tokens if t.startswith("#") and len(t) > 1]
        if tags:
            category = tags[0][1:].lower()
            text = " ".join(
                t for t in tokens if not (t.startswith("#") and len(t) > 1)
            ).strip()
        if not text:
            return "Faltou o texto da tarefa."
        tid = self._memory.add_task(user_id, text, category)
        return f"Tarefa #{tid} adicionada em '{category}': {text}"

    def tarefas(self, user_id: str, argstr: str = "") -> str:
        category = argstr.strip().lstrip("#").lower() or None
        items = self._memory.open_tasks(user_id, category)
        if not items:
            return (
                f"Nenhuma tarefa em '{category}'." if category
                else "Sua lista de tarefas está vazia."
            )
        lines = [f"📋 Suas tarefas{' em ' + category if category else ''}:"]
        current = None
        for t in items:
            if not category and t["category"] != current:
                current = t["category"]
                lines.append(f"[{current}]")
            lines.append(f"#{t['id']} {t['text']}")
        lines.append("\nConcluir: /concluir <id>")
        return "\n".join(lines)

    def concluir(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip().lstrip("#")
        if arg.isdigit():
            tid = int(arg)
            ok = self._memory.complete_task(user_id, tid)
            return f"Tarefa #{arg} concluída!" if ok else f"Não achei a tarefa #{arg} em aberto."
        if not arg:
            return "Uso: /concluir <id ou nome>. Veja em /tarefas."
        # Resolve by name (substring, case-insensitive) so voice/chat can complete
        # a task without knowing its id.
        low = arg.lower()
        matches = [t for t in self._memory.open_tasks(user_id) if low in t["text"].lower()]
        if not matches:
            return f"Não achei uma tarefa com \"{arg}\" em aberto. Veja /tarefas."
        if len(matches) > 1:
            opts = ", ".join(f"#{t['id']} {t['text']}" for t in matches[:6])
            return f"Achei mais de uma tarefa parecida: {opts}. Qual? (me diz o número)"
        t = matches[0]
        self._memory.complete_task(user_id, t["id"])
        return f"Tarefa \"{t['text']}\" concluída!"
