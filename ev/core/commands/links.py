"""Named, categorized links."""

from __future__ import annotations

from ..i18n import t as _t


class LinksMixin:
    def link(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        parts = [p.strip() for p in argstr.split("|")]
        if len(parts) != 3 or not all(parts):
            return _t(lang, "link.usage")
        category, name, url = parts
        lid = self._memory.add_link(user_id, category, name, url)
        return _t(lang, "link.saved", lid=lid, category=category, name=name)

    def links(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        category = argstr.strip() or None
        items = self._memory.list_links(user_id, category)
        if not items:
            return (
                _t(lang, "link.none_cat", category=category) if category
                else _t(lang, "link.none")
            )
        suffix = _t(lang, "link.in", cat=category) if category else ""
        lines = [_t(lang, "link.title", suffix=suffix)]
        current = None
        for it in items:
            if not category and it["category"] != current:
                current = it["category"]
                lines.append(f"[{current}]")
            lines.append(f"#{it['id']} {it['name']} — {it['url']}")
        return "\n".join(lines)

    def linkrm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        it, err = self._pick(self._memory.list_links(user_id), argstr, "name",
                             _t(lang, "link.pick"))
        if err:
            return err
        self._memory.delete_link(user_id, it["id"])
        return _t(lang, "link.removed", name=it["name"])
