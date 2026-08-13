"""People / relationships (with birthdays)."""

from __future__ import annotations


class PeopleMixin:
    def pessoas(self, user_id: str) -> str:
        people = self._memory.list_people(user_id)
        if not people:
            return "Nenhuma pessoa registrada. Use /pessoa <nome> | <sobre> [| <aniversário>]."
        lines = ["👥 Pessoas:"]
        for p in people:
            s = f"#{p['id']} {p['name']}"
            if p.get("notes"):
                s += f" — {p['notes']}"
            if p.get("birthday"):
                s += f" (🎂 {p['birthday']})"
            lines.append(s)
        return "\n".join(lines)

    def pessoa(self, user_id: str, argstr: str) -> str:
        parts = [p.strip() for p in (argstr or "").split("|")]
        nome = parts[0] if parts else ""
        if not nome:
            return "Uso: /pessoa <nome> | <sobre> [| <aniversário>]  (ou só /pessoa <nome> pra ver)"
        if len(parts) == 1:  # view
            p = self._memory.find_person(user_id, nome)
            if not p:
                return f"Não tenho nada sobre {nome}. Adicione: /pessoa {nome} | <sobre> [| <aniversário>]"
            out = [f"👤 {p['name']}"]
            if p.get("notes"):
                out.append(p["notes"])
            if p.get("birthday"):
                out.append(f"🎂 {p['birthday']}")
            return "\n".join(out)
        self._memory.add_person(user_id, nome, parts[1] if len(parts) > 1 else "",
                                parts[2] if len(parts) > 2 else "")
        return f"Anotado sobre {nome}."
