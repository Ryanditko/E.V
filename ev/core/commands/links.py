"""Named, categorized links."""

from __future__ import annotations


class LinksMixin:
    def link(self, user_id: str, argstr: str) -> str:
        parts = [p.strip() for p in argstr.split("|")]
        if len(parts) != 3 or not all(parts):
            return "Uso: /link <categoria> | <nome> | <url>\nEx: /link faculdade | lista de tarefas | https://..."
        category, name, url = parts
        lid = self._memory.add_link(user_id, category, name, url)
        return f"Link #{lid} salvo em '{category}': {name}"

    def links(self, user_id: str, argstr: str) -> str:
        category = argstr.strip() or None
        items = self._memory.list_links(user_id, category)
        if not items:
            return (
                f"Nenhum link em '{category}'." if category
                else "Você ainda não guardou links. Use /link."
            )
        lines = [f"🔗 Links{' em ' + category if category else ''}:"]
        current = None
        for it in items:
            if not category and it["category"] != current:
                current = it["category"]
                lines.append(f"[{current}]")
            lines.append(f"#{it['id']} {it['name']} — {it['url']}")
        return "\n".join(lines)

    def linkrm(self, user_id: str, argstr: str) -> str:
        it, err = self._pick(self._memory.list_links(user_id), argstr, "name", "o link")
        if err:
            return err
        self._memory.delete_link(user_id, it["id"])
        return f"Link \"{it['name']}\" removido."
