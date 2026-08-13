"""Web watches (URL/keyword monitors)."""

from __future__ import annotations


class WatchesMixin:
    def vigiar(self, user_id: str, argstr: str) -> str:
        parts = [p.strip() for p in argstr.split("|")]
        url = parts[0].strip()
        keyword = parts[1] if len(parts) > 1 and parts[1] else None
        if not url.lower().startswith("http"):
            return "Uso: /vigiar <url> [| palavra-chave]\nEx: /vigiar https://... | inscrições abertas"
        wid = self._memory.add_watch(user_id, url, keyword)
        extra = (
            f" (te aviso quando aparecer '{keyword}')" if keyword
            else " (te aviso quando a página mudar)"
        )
        return f"👁️ Monitor #{wid} criado{extra}."

    def vigias(self, user_id: str) -> str:
        items = self._memory.list_watches(user_id)
        if not items:
            return "Você não tem monitores. Crie com /vigiar <url> [| palavra]."
        lines = ["👁️ Monitores web:"]
        for w in items:
            k = f" [{w['keyword']}]" if w["keyword"] else ""
            lines.append(f"#{w['id']} {w['url']}{k}")
        lines.append("\nApagar: /vigiarm <id>")
        return "\n".join(lines)

    def vigiarm(self, user_id: str, argstr: str) -> str:
        arg = argstr.strip()
        if not arg.isdigit():
            return "Uso: /vigiarm <id>. Veja em /vigias."
        ok = self._memory.delete_watch(user_id, int(arg))
        return f"Monitor #{arg} removido." if ok else f"Não achei o monitor #{arg}."
