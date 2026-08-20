"""Long-term memory (facts): remember/list/forget."""

from __future__ import annotations

from ...providers import embeddings
from ..i18n import t as _t


class LongTermMemoryMixin:
    def lembrar(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        fact = argstr.strip()
        if not fact:
            return _t(lang, "ltm.usage")
        vec = embeddings.embed(fact, self._config)
        self._memory.add_fact(user_id, fact, embedding=vec)
        return _t(lang, "ltm.saved", fact=fact)

    def memorias(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        facts = self._memory.list_facts(user_id)
        if not facts:
            return _t(lang, "ltm.none")
        lines = [_t(lang, "ltm.title")]
        lines += [f"#{f['id']} {f['fact']}" for f in facts]
        lines.append(_t(lang, "ltm.footer"))
        return "\n".join(lines)

    def esquecer(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        it, err = self._pick(self._memory.list_facts(user_id), argstr, "fact",
                             _t(lang, "ltm.pick"))
        if err:
            return err
        self._memory.delete_fact(user_id, it["id"])
        return _t(lang, "ltm.forgot", fact=it["fact"])
