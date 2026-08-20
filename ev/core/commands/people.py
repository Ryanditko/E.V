"""People / relationships (with birthdays)."""

from __future__ import annotations

from ..i18n import t as _t


class PeopleMixin:
    def pessoas(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        people = self._memory.list_people(user_id)
        if not people:
            return _t(lang, "ppl.none")
        lines = [_t(lang, "ppl.title")]
        for p in people:
            s = f"#{p['id']} {p['name']}"
            if p.get("notes"):
                s += f" — {p['notes']}"
            if p.get("birthday"):
                s += f" (🎂 {p['birthday']})"
            lines.append(s)
        return "\n".join(lines)

    def pessoa(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        parts = [p.strip() for p in (argstr or "").split("|")]
        nome = parts[0] if parts else ""
        if not nome:
            return _t(lang, "ppl.usage")
        if len(parts) == 1:  # view
            p = self._memory.find_person(user_id, nome)
            if not p:
                return _t(lang, "ppl.not_found", name=nome)
            out = [f"👤 {p['name']}"]
            if p.get("notes"):
                out.append(p["notes"])
            if p.get("birthday"):
                out.append(f"🎂 {p['birthday']}")
            return "\n".join(out)
        self._memory.add_person(user_id, nome, parts[1] if len(parts) > 1 else "",
                                parts[2] if len(parts) > 2 else "")
        return _t(lang, "ppl.saved", name=nome)
