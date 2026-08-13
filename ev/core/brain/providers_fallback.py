"""Multi-provider chain: Gemini (primary) -> Groq -> OpenRouter -> Ollama."""

import logging

from google.genai import types

from ...providers import llm as providers

log = logging.getLogger("ev.brain")


class ProvidersFallbackMixin:
    # --- primary provider: Gemini ------------------------------------------

    def _gemini(
        self,
        user_id: str,
        conv_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
        image: bytes | None,
        image_mime: str | None,
        system_instruction: str,
    ) -> str:
        """Call Gemini with memory (function calling). Raises on failure (rate
        limit, etc.) so the caller falls through to the fallbacks."""
        tools = list(self._tool_callables(user_id).values())  # data scoped to owner
        contents = self._build_contents(  # history scoped to this conversation
            conv_id, text, audio, audio_mime, image, image_mime
        )

        response = self._client.models.generate_content(
            model=self.current_model(),
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.4,
            ),
        )
        self._last_provider = "gemini"
        # Log what Gemini's automatic function calling actually did (it is otherwise
        # opaque) — invaluable for debugging why a CRUD tool didn't run.
        try:
            for h in (getattr(response, "automatic_function_calling_history", None) or []):
                for part in (getattr(h, "parts", None) or []):
                    fc = getattr(part, "function_call", None)
                    if fc:
                        log.info("[gemini-afc] chamou %s args=%s", fc.name,
                                 dict(fc.args or {}))
                        self._last_steps.append({"tool": fc.name,
                                                 "args": dict(fc.args or {})})
                    fr = getattr(part, "function_response", None)
                    if fr:
                        res = str(getattr(fr, "response", ""))[:200]
                        log.info("[gemini-afc] resultado %s: %s", fr.name, res)
                        for s in reversed(self._last_steps):   # anexa ao passo correspondente
                            if s.get("tool") == fr.name and "result" not in s:
                                s["result"] = res
                                break
        except Exception:
            pass
        return (response.text or "").strip() or "…"

    def _build_contents(
        self,
        conv_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
        image: bytes | None = None,
        image_mime: str | None = None,
    ) -> list[types.Content]:
        contents: list[types.Content] = []

        for msg in self._memory.recent_messages(conv_id, limit=20):
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

        new_parts: list[types.Part] = []
        if audio is not None:
            new_parts.append(
                types.Part.from_bytes(data=audio, mime_type=audio_mime or "audio/ogg")
            )
            new_parts.append(
                types.Part.from_text(
                    text="(mensagem de voz do usuário — responda ao conteúdo dela)"
                )
            )
        if image is not None:
            new_parts.append(
                types.Part.from_bytes(data=image, mime_type=image_mime or "image/jpeg")
            )
            if text is None:
                new_parts.append(
                    types.Part.from_text(
                        text="(imagem enviada pelo usuário — descreva/analise e ajude)"
                    )
                )
        if text is not None:
            new_parts.append(types.Part.from_text(text=text))

        contents.append(types.Content(role="user", parts=new_parts))
        return contents

    # --- fallbacks: Groq -> OpenRouter --------------------------------------

    def _openai_messages(self, conv_id: str, new_text: str) -> list[dict]:
        # Keep history short on the fallback path: Groq's free tier caps tokens
        # per minute (~8k), and a long history + tool schemas blows past it (429).
        msgs: list[dict] = []
        for m in self._memory.recent_messages(conv_id, limit=8):
            role = "assistant" if m["role"] == "model" else "user"
            msgs.append({"role": role, "content": m["content"]})
        msgs.append({"role": "user", "content": new_text})
        return msgs

    def _fallbacks(self, user_id: str, conv_id: str, text: str, system: str,
                   only: str | None = None) -> str | None:
        messages = self._openai_messages(conv_id, text)  # history per conversation
        cfg = self._config

        # 1) Groq — WITH memory/tools (function calling): always-available path.
        if cfg.groq_api_key and only in (None, "groq"):
            try:
                answer = providers.chat_with_tools(
                    base_url=providers.GROQ_BASE_URL,
                    api_key=cfg.groq_api_key,
                    model=cfg.groq_model,
                    system=system,
                    messages=messages,
                    tools=self._openai_tools(),
                    tool_functions=self._tool_callables(user_id),
                    temperature=0.2,  # lower -> more reliable tool-calling
                )
                if answer:
                    log.info("Answered via Groq (%s) with tools.", cfg.groq_model)
                    self._last_provider = "groq"
                    return answer
            except Exception as exc:
                log.warning("Groq fallback failed (%s).", exc)

        # 2) OpenRouter — also WITH tools, so CRUD still works when Groq is rate
        #    limited. Falls back to plain text if the model can't do tool-calling.
        if cfg.openrouter_api_key and only in (None, "openrouter"):
            try:
                answer = providers.chat_with_tools(
                    base_url=providers.OPENROUTER_BASE_URL,
                    api_key=cfg.openrouter_api_key,
                    model=cfg.openrouter_model,
                    system=system,
                    messages=messages,
                    tools=self._openai_tools(),
                    tool_functions=self._tool_callables(user_id),
                    temperature=0.2,
                )
                if answer:
                    log.info("Answered via OpenRouter (%s) with tools.", cfg.openrouter_model)
                    self._last_provider = "openrouter"
                    return answer
            except Exception as exc:
                log.warning("OpenRouter (tools) failed (%s); trying plain text.", exc)
                try:
                    answer = providers.chat_openai_compat(
                        base_url=providers.OPENROUTER_BASE_URL,
                        api_key=cfg.openrouter_api_key,
                        model=cfg.openrouter_model,
                        system=system,
                        messages=messages,
                    )
                    if answer:
                        log.info("Answered via OpenRouter (%s), plain.", cfg.openrouter_model)
                        self._last_provider = "openrouter"
                        return answer
                except Exception as exc2:
                    log.warning("OpenRouter plain failed (%s).", exc2)

        # 3) Ollama — local model, never rate-limited (final safety net).
        if cfg.ollama_enabled and only in (None, "ollama"):
            try:
                answer = providers.chat_openai_compat(
                    base_url=cfg.ollama_base_url,
                    api_key="ollama",  # Ollama ignores the key
                    model=cfg.ollama_model,
                    system=system,
                    messages=messages,
                )
                if answer:
                    log.info("Answered via Ollama (%s, local).", cfg.ollama_model)
                    self._last_provider = "ollama"
                    return answer
            except Exception as exc:
                log.warning("Ollama fallback failed (%s).", exc)

        return None
