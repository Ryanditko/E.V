"""Long-term memory (facts): remember/list/forget."""

from __future__ import annotations

from ...providers import embeddings


class LongTermMemoryMixin:
    def lembrar(self, user_id: str, argstr: str) -> str:
        fact = argstr.strip()
        if not fact:
            return "Uso: /lembrar <fato>. Ex: /lembrar meu carro é um Civic preto"
        vec = embeddings.embed(fact, self._config)
        self._memory.add_fact(user_id, fact, embedding=vec)
        return f"Anotado na memória: {fact}"

    def memorias(self, user_id: str) -> str:
        facts = self._memory.list_facts(user_id)
        if not facts:
            return "Ainda não sei nada sobre você. Use /lembrar pra me contar algo."
        lines = ["🧠 O que eu sei sobre você:"]
        lines += [f"#{f['id']} {f['fact']}" for f in facts]
        lines.append("\nApagar: /esquecer <id>")
        return "\n".join(lines)

    def esquecer(self, user_id: str, argstr: str) -> str:
        it, err = self._pick(self._memory.list_facts(user_id), argstr, "fact", "a memória")
        if err:
            return err
        self._memory.delete_fact(user_id, it["id"])
        return f"Esqueci: \"{it['fact']}\"."
