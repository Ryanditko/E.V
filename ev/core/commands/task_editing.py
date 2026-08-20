"""Task editing/removal by id or name (hands-free voice/chat friendly)."""

from __future__ import annotations

from ..i18n import t as _t


class TaskEditingMixin:
    def _resolve_task(self, user_id: str, arg: str):
        """Find one open task by id or name; returns (task|None, error_msg|None)."""
        lang = self._memory.assistant_lang()
        arg = arg.strip().lstrip("#")
        if arg.isdigit():
            for t in self._memory.open_tasks(user_id):
                if t["id"] == int(arg):
                    return t, None
            return None, _t(lang, "task.not_found_id", arg=arg)
        if not arg:
            return None, _t(lang, "task.need_name")
        low = arg.lower()
        matches = [t for t in self._memory.open_tasks(user_id) if low in t["text"].lower()]
        if not matches:
            return None, _t(lang, "task.not_found_name_edit", arg=arg)
        if len(matches) > 1:
            opts = ", ".join(f"#{t['id']} {t['text']}" for t in matches[:6])
            return None, _t(lang, "task.ambiguous_generic", opts=opts)
        return matches[0], None

    def tarefarm(self, user_id: str, argstr: str) -> str:
        """Delete a task by id or name (for hands-free voice/chat)."""
        t, err = self._resolve_task(user_id, argstr)
        if err:
            return err
        self._memory.delete_task(user_id, t["id"])
        return _t(self._memory.assistant_lang(), "task.deleted", text=t["text"])

    def tarefaeditar(self, user_id: str, argstr: str) -> str:
        """Edit a task by name: '<nome/id> | <novo texto> [#categoria]'."""
        lang = self._memory.assistant_lang()
        alvo, _, novo = argstr.partition("|")
        t, err = self._resolve_task(user_id, alvo)
        if err:
            return err
        novo = novo.strip()
        if not novo:
            return _t(lang, "task.edit_usage")
        cat = None
        toks = novo.split()
        cats = [x[1:] for x in toks if x.startswith("#") and len(x) > 1]
        if cats:
            cat = cats[0]
            novo = " ".join(x for x in toks if not x.startswith("#")).strip()
        self._memory.update_task(user_id, t["id"], text=(novo or None), category=cat)
        return _t(lang, "task.updated", text=(novo or t["text"]),
                  cat=(f" ({cat})" if cat else ""))
