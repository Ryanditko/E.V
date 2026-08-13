"""One-off LLM calls (no memory/tools) and agentic day-planning synthesis."""

import asyncio
import logging

from google.genai import types

from ...providers import llm as providers, tools as tools_mod

log = logging.getLogger("ev.brain")


class AskMixin:
    async def ask(self, system: str, prompt: str) -> str | None:
        """One-off LLM call (no memory/tools) through the provider chain.
        Used by features like quizzes and weekly insights."""
        return await asyncio.to_thread(self._ask_sync, system, prompt)

    async def plan_day(self, user_id: str) -> str:
        """Agentic synthesis: an actionable plan from tasks + agenda + weather + loc."""
        return await asyncio.to_thread(self._plan_day_sync, user_id)

    def _plan_day_sync(self, user_id: str) -> str:
        cfg = self._config
        parts = []
        tasks = self._memory.open_tasks(user_id)
        if tasks:
            parts.append("Tarefas abertas:\n" + "\n".join(
                f"- {t['text']} ({t.get('category', 'geral')})" for t in tasks[:20]))
        rems = self._memory.open_reminders(user_id)
        if rems:
            parts.append("Lembretes:\n" + "\n".join(
                f"- {r['text']}" + (f" — {r['when_iso'][:16].replace('T', ' ')}"
                                    if r.get("when_iso") else "") for r in rems[:15]))
        if cfg.google_authorized():
            try:
                parts.append("Agenda:\n" + tools_mod.calendar_upcoming(
                    cfg, cfg.default_account, 8))
            except Exception:
                pass
        if getattr(cfg, "city", ""):
            try:
                parts.append("Clima:\n" + tools_mod.weather(cfg.city))
            except Exception:
                pass
        addr = self._memory.get_setting("loc_addr")
        if addr:
            parts.append("Localização atual: " + addr)
        context = f"(agora: {self._now_str()})\n\n" + (
            "\n\n".join(parts) or "Sem dados no momento.")
        system = (
            "Você é a E.V., assistente pessoal do Ryan. Com base nos dados, monte um "
            "PLANO curto e acionável para o dia dele, em português do Brasil: priorize "
            "as tarefas, encaixe-as nos espaços entre os compromissos, avise sobre "
            "conflitos de horário, clima ou trânsito, e termine com UMA sugestão do que "
            "fazer AGORA. Use bullets curtos, direto ao ponto. Chame ele de Ryan.")
        return self._ask_sync(system, context) or "Não consegui montar o plano agora."

    def _ask_sync(self, system: str, prompt: str) -> str | None:
        try:
            resp = self._client.models.generate_content(
                model=self.current_model(),
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=0.5
                ),
            )
            if (resp.text or "").strip():
                return resp.text.strip()
        except Exception as exc:
            log.warning("ask_once Gemini failed (%s)", exc)

        cfg = self._config
        messages = [{"role": "user", "content": prompt}]
        chain = []
        if cfg.groq_api_key:
            chain.append((providers.GROQ_BASE_URL, cfg.groq_api_key, cfg.groq_model))
        if cfg.openrouter_api_key:
            chain.append(
                (providers.OPENROUTER_BASE_URL, cfg.openrouter_api_key, cfg.openrouter_model)
            )
        if cfg.ollama_enabled:
            chain.append((cfg.ollama_base_url, "ollama", cfg.ollama_model))
        for base, key, model in chain:
            try:
                ans = providers.chat_openai_compat(
                    base_url=base, api_key=key, model=model,
                    system=system, messages=messages,
                )
                if ans:
                    return ans
            except Exception as exc:
                log.warning("ask_once fallback failed (%s)", exc)
        return None
