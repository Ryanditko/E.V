"""Live provider health checks (/status)."""

import asyncio
import logging

from google.genai import types

from ...providers import llm as providers, tools as tools_mod

log = logging.getLogger("ev.brain")


class ProviderHealthMixin:
    async def health_check(self) -> list[dict]:
        """Live-ping each configured provider. Returns [{name, ok, note}]."""
        return await asyncio.to_thread(self._health_check_sync)

    def _health_check_sync(self) -> list[dict]:
        cfg = self._config
        out: list[dict] = []
        if cfg.gemini_api_key:
            out.append(self._ping_gemini())
        if cfg.groq_api_key:
            out.append(self._ping_openai(
                "Groq", providers.GROQ_BASE_URL, cfg.groq_api_key, cfg.groq_model))
        if cfg.openrouter_api_key:
            out.append(self._ping_openai(
                "OpenRouter", providers.OPENROUTER_BASE_URL,
                cfg.openrouter_api_key, cfg.openrouter_model))
        if cfg.ollama_enabled:
            out.append(self._ping_openai(
                "Ollama", cfg.ollama_base_url, "ollama", cfg.ollama_model))
        if cfg.tavily_api_key:
            out.append(self._ping_tavily())
        return out

    @staticmethod
    def _res(name, ok, note=""):
        return {"name": name, "ok": bool(ok), "note": note}

    def _ping_gemini(self) -> dict:
        try:
            self._client.models.generate_content(
                model=self.current_model(), contents="ping",
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return self._res("Gemini", True, "respondeu")
        except Exception as exc:
            msg = str(exc)
            rate = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            # Rate-limit is expected on the free tier — not a real failure.
            return self._res("Gemini", rate, "cota do dia (normal)" if rate else msg[:70])

    def _ping_openai(self, name, base, key, model) -> dict:
        try:
            ans = providers.chat_openai_compat(
                base_url=base, api_key=key, model=model,
                system="", messages=[{"role": "user", "content": "ping"}],
            )
            return self._res(name, bool(ans), "respondeu" if ans else "sem resposta")
        except Exception as exc:
            return self._res(name, False, str(exc)[:70])

    def _ping_tavily(self) -> dict:
        try:
            txt = tools_mod.tavily_search("teste", self._config.tavily_api_key, max_results=1)
            return self._res("Tavily", bool(txt), "respondeu" if txt else "sem resposta")
        except Exception as exc:
            return self._res("Tavily", False, str(exc)[:70])
