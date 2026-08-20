"""Automations ("quando X, faça Y")."""

from __future__ import annotations

from ..i18n import t as _t


class AutomationsMixin:
    def automacoes(self, user_id: str) -> str:
        from ..automations import describe
        lang = self._memory.assistant_lang()
        items = self._memory.list_automations(user_id)
        if not items:
            return _t(lang, "auto.none")
        return (_t(lang, "auto.title") + "\n"
                + "\n".join(describe(a, lang) for a in items)
                + _t(lang, "auto.footer"))

    def automacao_rm(self, user_id: str, arg: str) -> str:
        lang = self._memory.assistant_lang()
        try:
            aid = int(str(arg).strip())
        except (ValueError, TypeError):
            return _t(lang, "auto.rm_usage")
        if self._memory.delete_automation(user_id, aid):
            return _t(lang, "auto.removed", aid=aid)
        return _t(lang, "auto.rm_not_found")

    def create_automation(self, user_id: str, trigger: str, action: str, *,
                          hour=None, minute=0, weekday=-1, amount=None,
                          category=None, message=None, command=None,
                          playlist=None, musica=None):
        """Deterministic constructor used by the AI tool + web form. Validates,
        seeds trigger state (e.g. current max expense id, so it never fires on
        past data). Returns (id_or_None, human_message)."""
        from ..automations import TRIGGERS, ACTIONS, describe
        lang = self._memory.assistant_lang()
        if trigger not in TRIGGERS:
            return None, _t(lang, "auto.bad_trigger", trigger=trigger)
        if action not in ACTIONS:
            return None, _t(lang, "auto.bad_action", action=action)
        trig_cfg, state = {}, {}
        if trigger == "time":
            if hour is None:
                return None, _t(lang, "auto.missing_hour")
            trig_cfg = {"hour": int(hour), "minute": int(minute or 0),
                        "weekday": int(weekday if weekday is not None else -1)}
        elif trigger == "expense_over":
            if amount is None:
                return None, _t(lang, "auto.missing_amount")
            trig_cfg = {"amount": float(amount)}
            if category:
                trig_cfg["category"] = category
            state = {"last_id": self._memory.max_expense_id(user_id)}
        act_cfg = {}
        if action == "notify":
            act_cfg = {"message": message or _t(lang, "auto.notify_default")}
        elif action == "command":
            if not command:
                return None, _t(lang, "auto.missing_command")
            act_cfg = {"command": command.lstrip("/")}
        elif action == "reschedule":
            if trigger != "task_overdue":
                return None, _t(lang, "auto.reschedule_only")
        elif action == "play":
            if playlist:
                act_cfg = {"playlist": playlist}
            elif musica:
                act_cfg = {"query": musica}
            else:
                return None, _t(lang, "auto.play_target")
        name = (message or ("tocar " + (playlist or musica) if action == "play" and (playlist or musica)
                            else (f"/{command}" if command else action)))[:80]
        aid = self._memory.add_automation(
            user_id, name, trigger, trig_cfg, action, act_cfg, state)
        a = {"id": aid, "trig": trigger, "trig_cfg": trig_cfg, "act": action,
             "act_cfg": act_cfg, "enabled": True}
        return aid, describe(a, lang)
