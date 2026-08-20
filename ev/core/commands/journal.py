"""Journal entries."""

from __future__ import annotations

from datetime import datetime

from ..i18n import t as _t


class JournalMixin:
    def diario(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        text = argstr.strip()
        if not text:
            entries = self._memory.recent_journal(user_id, 5)
            if not entries:
                return _t(lang, "jour.empty")
            lines = [_t(lang, "jour.list_title")]
            for e in entries:
                day = ""
                try:
                    day = datetime.fromisoformat(e["created"]).strftime("%d/%m")
                except Exception:
                    pass
                lines.append(f"#{e['id']} [{day}] {e['text']}")
            lines.append(_t(lang, "jour.list_footer"))
            return "\n".join(lines)
        self._memory.add_journal(user_id, text)
        return _t(lang, "jour.saved")

    def diariorm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        arg = argstr.strip()
        if not arg.isdigit():
            return _t(lang, "jour.rm_usage")
        ok = self._memory.delete_journal(user_id, int(arg))
        return _t(lang, "jour.removed", arg=arg) if ok else _t(lang, "jour.not_found", arg=arg)
