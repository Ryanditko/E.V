"""Tasks: create, list, complete."""

from __future__ import annotations

from ..i18n import t as _t


class TasksMixin:
    def tarefa(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        text = argstr.strip()
        if not text:
            return _t(lang, "task.usage")
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
            return _t(lang, "task.missing_text")
        tid = self._memory.add_task(user_id, text, category)
        return _t(lang, "task.added", tid=tid, category=category, text=text)

    def tarefas(self, user_id: str, argstr: str = "") -> str:
        lang = self._memory.assistant_lang()
        category = argstr.strip().lstrip("#").lower() or None
        items = self._memory.open_tasks(user_id, category)
        if not items:
            return (
                _t(lang, "task.none_in_cat", category=category) if category
                else _t(lang, "task.list_empty")
            )
        suffix = _t(lang, "task.list_in", cat=category) if category else ""
        lines = [_t(lang, "task.list_title", suffix=suffix)]
        current = None
        for t in items:
            if not category and t["category"] != current:
                current = t["category"]
                lines.append(f"[{current}]")
            lines.append(f"#{t['id']} {t['text']}")
        lines.append(_t(lang, "task.list_footer"))
        return "\n".join(lines)

    def concluir(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        arg = argstr.strip().lstrip("#")
        if arg.isdigit():
            tid = int(arg)
            ok = self._memory.complete_task(user_id, tid)
            return (_t(lang, "task.completed_id", arg=arg) if ok
                    else _t(lang, "task.not_found_id", arg=arg))
        if not arg:
            return _t(lang, "task.complete_usage")
        # Resolve by name (substring, case-insensitive) so voice/chat can complete
        # a task without knowing its id.
        low = arg.lower()
        matches = [t for t in self._memory.open_tasks(user_id) if low in t["text"].lower()]
        if not matches:
            return _t(lang, "task.not_found_name", arg=arg)
        if len(matches) > 1:
            opts = ", ".join(f"#{t['id']} {t['text']}" for t in matches[:6])
            return _t(lang, "task.ambiguous", opts=opts)
        t = matches[0]
        self._memory.complete_task(user_id, t["id"])
        return _t(lang, "task.completed_name", text=t["text"])
