"""Automations ("quando X, faça Y")."""

from __future__ import annotations


class AutomationsMixin:
    def automacoes(self, user_id: str) -> str:
        from ..automations import describe
        items = self._memory.list_automations(user_id)
        if not items:
            return ("Nenhuma automação ainda. Me diga algo como 'quando eu gastar "
                    "mais de 200, me avisa' ou 'toda sexta 18h, me manda o resumo'.")
        return ("🤖 Suas automações:\n" + "\n".join(describe(a) for a in items)
                + "\n\nApagar: /automacaorm <id>")

    def automacao_rm(self, user_id: str, arg: str) -> str:
        try:
            aid = int(str(arg).strip())
        except (ValueError, TypeError):
            return "Uso: /automacaorm <id> (veja os ids em /automacoes)."
        if self._memory.delete_automation(user_id, aid):
            return f"Automação #{aid} removida."
        return "Não achei essa automação."

    def create_automation(self, user_id: str, trigger: str, action: str, *,
                          hour=None, minute=0, weekday=-1, amount=None,
                          category=None, message=None, command=None,
                          playlist=None, musica=None):
        """Deterministic constructor used by the AI tool + web form. Validates,
        seeds trigger state (e.g. current max expense id, so it never fires on
        past data). Returns (id_or_None, human_message)."""
        from ..automations import TRIGGERS, ACTIONS, describe
        if trigger not in TRIGGERS:
            return None, f"gatilho inválido ({trigger})"
        if action not in ACTIONS:
            return None, f"ação inválida ({action})"
        trig_cfg, state = {}, {}
        if trigger == "time":
            if hour is None:
                return None, "faltou a hora do gatilho"
            trig_cfg = {"hour": int(hour), "minute": int(minute or 0),
                        "weekday": int(weekday if weekday is not None else -1)}
        elif trigger == "expense_over":
            if amount is None:
                return None, "faltou o valor do gatilho"
            trig_cfg = {"amount": float(amount)}
            if category:
                trig_cfg["category"] = category
            state = {"last_id": self._memory.max_expense_id(user_id)}
        act_cfg = {}
        if action == "notify":
            act_cfg = {"message": message or "lembrete da automação"}
        elif action == "command":
            if not command:
                return None, "faltou o comando a rodar"
            act_cfg = {"command": command.lstrip("/")}
        elif action == "reschedule":
            if trigger != "task_overdue":
                return None, "‘remarcar’ só funciona com o gatilho de tarefa vencida"
        elif action == "play":
            if playlist:
                act_cfg = {"playlist": playlist}
            elif musica:
                act_cfg = {"query": musica}
            else:
                return None, "diga a playlist ou a música pra tocar"
        name = (message or ("tocar " + (playlist or musica) if action == "play" and (playlist or musica)
                            else (f"/{command}" if command else action)))[:80]
        aid = self._memory.add_automation(
            user_id, name, trigger, trig_cfg, action, act_cfg, state)
        a = {"id": aid, "trig": trigger, "trig_cfg": trig_cfg, "act": action,
             "act_cfg": act_cfg, "enabled": True}
        return aid, describe(a)
