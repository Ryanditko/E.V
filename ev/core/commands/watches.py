"""Web watches (URL/keyword monitors)."""

from __future__ import annotations

from ..i18n import t as _t


class WatchesMixin:
    def vigiar(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        parts = [p.strip() for p in argstr.split("|")]
        url = parts[0].strip()
        keyword = parts[1] if len(parts) > 1 and parts[1] else None
        if not url.lower().startswith("http"):
            return _t(lang, "watch.usage")
        wid = self._memory.add_watch(user_id, url, keyword)
        extra = (
            _t(lang, "watch.extra_kw", keyword=keyword) if keyword
            else _t(lang, "watch.extra_change")
        )
        return _t(lang, "watch.created", wid=wid, extra=extra)

    def vigias(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        items = self._memory.list_watches(user_id)
        if not items:
            return _t(lang, "watch.none")
        lines = [_t(lang, "watch.title")]
        for w in items:
            k = f" [{w['keyword']}]" if w["keyword"] else ""
            lines.append(f"#{w['id']} {w['url']}{k}")
        lines.append(_t(lang, "watch.footer"))
        return "\n".join(lines)

    def vigiarm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        arg = argstr.strip()
        if not arg.isdigit():
            return _t(lang, "watch.rm_usage")
        ok = self._memory.delete_watch(user_id, int(arg))
        return _t(lang, "watch.removed", arg=arg) if ok else _t(lang, "watch.not_found", arg=arg)
