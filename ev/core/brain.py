"""E.V.'s brain — orchestrates LLM + memory + personality + tools.

Reusable layer: any interface (Telegram, terminal, web) calls
`Brain.respond(...)` with text or audio and gets back the answer as text.

Multi-provider strategy (maximize free requests, never go silent):
  1. GEMINI (primary) — smartest, hears audio natively, saves memory via the
     google-genai SDK's automatic function calling.
  2. GROQ (fallback) — Llama 3.3 70B, fast, 30 req/min. When Gemini fails
     (rate limit, etc.), E.V. keeps talking here, WITH memory (OpenAI-style
     function calling). Audio is transcribed first via Groq Whisper.
  3. OPENROUTER (fallback) — plain text, no memory.
  4. OLLAMA (final safety net) — local model, never rate-limited ("never runs out").

Providers without a configured key are skipped. The brain also does RAG: it
injects the user's most relevant knowledge-base chunks into the system prompt.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from google import genai
from google.genai import types

from ..config import Config
from ..personality import SYSTEM_PROMPT
from ..providers import embeddings, llm as providers, tools as tools_mod
from .memory import Memory

log = logging.getLogger("ev.brain")

# Last resort: every provider failed (or no fallback keys configured).
_ALL_DOWN_MSG = (
    "Opa, todos os meus cérebros estão no limite agora (o plano grátis tem cota "
    "por minuto). Me dá uns segundos e tenta de novo, tá?"
)


class Brain:
    def __init__(self, config: Config, memory: Memory) -> None:
        self._config = config
        self._client = genai.Client(api_key=config.gemini_api_key)
        self._model = config.model
        self._memory = memory

    async def respond(
        self,
        user_id: str,
        *,
        text: str | None = None,
        audio: bytes | None = None,
        audio_mime: str | None = None,
        image: bytes | None = None,
        image_mime: str | None = None,
    ) -> str:
        """Produce E.V.'s answer to a message (text, audio, and/or image).

        Runs the blocking SDK calls in a thread so the async event loop is free.
        """
        return await asyncio.to_thread(
            self._respond_sync, user_id, text, audio, audio_mime, image, image_mime
        )

    # -----------------------------------------------------------------------

    def _respond_sync(
        self,
        user_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
        image: bytes | None = None,
        image_mime: str | None = None,
    ) -> str:
        # Semantic recall uses the text query; audio/image-through-Gemini has none yet.
        system_instruction = self._system_instruction(user_id, text)
        if text is not None:
            user_repr = text
        elif image is not None:
            user_repr = "[imagem]"
        else:
            user_repr = "[mensagem de voz]"
        answer: str | None = None

        # 1) Gemini — primary (native audio + image + memory).
        try:
            answer = self._gemini(
                user_id, text, audio, audio_mime, image, image_mime, system_instruction
            )
        except Exception as exc:
            log.warning("Gemini failed (%s). Trying fallbacks...", exc)

            # Fallbacks handle text only. Audio -> transcribe; image can't be seen.
            fb_text = text
            if audio is not None:
                fb_text = self._transcribe(audio, audio_mime)
                if fb_text:
                    user_repr = fb_text
                    system_instruction = self._system_instruction(user_id, fb_text)
            if image is not None and not fb_text:
                return "Consegui receber a imagem, mas meu cérebro de visão está no limite agora. Tenta de novo em uns segundos?"

            if fb_text:
                answer = self._fallbacks(user_id, fb_text, system_instruction)

        if not answer:
            return _ALL_DOWN_MSG

        # Persist the turn in conversation memory.
        self._memory.add_message(user_id, "user", user_repr)
        self._memory.add_message(user_id, "model", answer)
        return answer

    # --- system prompt ------------------------------------------------------

    def _system_instruction(self, user_id: str, query: str | None) -> str:
        system = SYSTEM_PROMPT

        # Current date/time so the model can resolve "tomorrow at 9am" to ISO.
        system += "\n\n## Data e hora atual\n" + self._now_str()

        # Relevant facts (semantic recall when we have a text query + embeddings).
        query_vec = self._embed(query) if query else None
        facts = self._memory.relevant_facts(user_id, query_vec, k=8)
        if facts:
            system += "\n\n## O que você já sabe sobre o usuário\n"
            system += "\n".join(f"- {f}" for f in facts)

        # Knowledge base (RAG): inject the most relevant document chunks.
        chunks = self._memory.search_knowledge(user_id, query_vec, k=4)
        if chunks:
            system += (
                "\n\n## Trechos relevantes dos documentos do usuário\n"
                "Use isto para embasar a resposta quando fizer sentido.\n"
            )
            for c in chunks:
                system += f"\n[{c['source']}]\n{c['chunk']}\n"
        return system

    def _now_str(self) -> str:
        try:
            tz = ZoneInfo(self._config.timezone) if ZoneInfo else None
            now = datetime.now(tz)
            return (
                f"Agora é {now.isoformat(timespec='minutes')} "
                f"(fuso {self._config.timezone}). "
                "Ao criar lembretes ou eventos, converta para ISO 8601."
            )
        except Exception:
            return "Ao criar lembretes ou eventos, use ISO 8601."

    def _embed(self, text: str) -> list[float] | None:
        return embeddings.embed(text, self._config)

    # --- tools (shared by Gemini and Groq) ---------------------------------

    def _tool_callables(self, user_id: str) -> dict:
        """Tools bound to THIS user. Used by Gemini (Python funcs) and Groq
        (function-calling dispatch)."""
        cfg = self._config

        def salvar_memoria(fato: str) -> str:
            """Guarda um fato duradouro sobre o usuário (nome, preferências,
            pessoas, projetos, rotinas).

            Args:
                fato: o fato a memorizar, em uma frase curta.
            """
            self._memory.add_fact(user_id, fato, embedding=self._embed(fato))
            return "ok, memorizado"

        def criar_lembrete(texto: str, quando: str | None = None) -> str:
            """Cria um lembrete para o usuário.

            Args:
                texto: o que lembrar.
                quando: data/hora em ISO 8601 (ex: 2026-07-22T09:00:00-03:00).
            """
            rid = self._memory.add_reminder(user_id, texto, quando)
            return f"lembrete #{rid} criado"

        def listar_lembretes() -> str:
            """Lista os lembretes em aberto do usuário."""
            items = self._memory.open_reminders(user_id)
            if not items:
                return "nenhum lembrete em aberto"
            return "; ".join(
                f"#{r['id']} {r['text']}"
                + (f" ({r['when_iso']})" if r["when_iso"] else "")
                for r in items
            )

        callables: dict = {
            "salvar_memoria": salvar_memoria,
            "criar_lembrete": criar_lembrete,
            "listar_lembretes": listar_lembretes,
        }

        if cfg.websearch_enabled:
            def buscar_web(consulta: str) -> str:
                """Busca informação atual na internet.

                Args:
                    consulta: o que pesquisar.
                """
                return tools_mod.web_search(consulta)

            callables["buscar_web"] = buscar_web

        if cfg.google_oauth_client:
            def ver_agenda() -> str:
                """Lista os próximos eventos da agenda do Google do usuário."""
                return tools_mod.calendar_upcoming(cfg)

            def criar_evento(titulo: str, inicio: str, fim: str) -> str:
                """Cria um evento na agenda do Google.

                Args:
                    titulo: título do evento.
                    inicio: início em ISO 8601.
                    fim: fim em ISO 8601.
                """
                return tools_mod.calendar_create(cfg, titulo, inicio, fim)

            def enviar_email(para: str, assunto: str, corpo: str) -> str:
                """Envia um e-mail pela conta Gmail do usuário.

                Args:
                    para: endereço de e-mail do destinatário.
                    assunto: assunto do e-mail.
                    corpo: corpo do e-mail.
                """
                return tools_mod.send_email(cfg, para, assunto, corpo)

            callables["ver_agenda"] = ver_agenda
            callables["criar_evento"] = criar_evento
            callables["enviar_email"] = enviar_email

        return callables

    def _openai_tools(self) -> list[dict]:
        """OpenAI-format schemas mirroring the enabled tools (for Groq)."""
        cfg = self._config

        def fn(name, desc, props=None, required=None):
            return {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": props or {},
                        "required": required or [],
                    },
                },
            }

        s = "string"
        schemas = [
            fn(
                "salvar_memoria",
                "Guarda um fato duradouro sobre o usuário.",
                {"fato": {"type": s, "description": "o fato, em uma frase curta"}},
                ["fato"],
            ),
            fn(
                "criar_lembrete",
                "Cria um lembrete para o usuário.",
                {
                    "texto": {"type": s, "description": "o que lembrar"},
                    "quando": {"type": s, "description": "data/hora em ISO 8601"},
                },
                ["texto"],
            ),
            fn("listar_lembretes", "Lista os lembretes em aberto do usuário."),
        ]
        if cfg.websearch_enabled:
            schemas.append(
                fn(
                    "buscar_web",
                    "Busca informação atual na internet.",
                    {"consulta": {"type": s, "description": "o que pesquisar"}},
                    ["consulta"],
                )
            )
        if cfg.google_oauth_client:
            schemas += [
                fn("ver_agenda", "Lista os próximos eventos da agenda do Google."),
                fn(
                    "criar_evento",
                    "Cria um evento na agenda do Google.",
                    {
                        "titulo": {"type": s},
                        "inicio": {"type": s, "description": "início em ISO 8601"},
                        "fim": {"type": s, "description": "fim em ISO 8601"},
                    },
                    ["titulo", "inicio", "fim"],
                ),
                fn(
                    "enviar_email",
                    "Envia um e-mail pela conta Gmail do usuário.",
                    {
                        "para": {"type": s},
                        "assunto": {"type": s},
                        "corpo": {"type": s},
                    },
                    ["para", "assunto", "corpo"],
                ),
            ]
        return schemas

    # --- primary provider: Gemini ------------------------------------------

    def _gemini(
        self,
        user_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
        image: bytes | None,
        image_mime: str | None,
        system_instruction: str,
    ) -> str:
        """Call Gemini with memory (function calling). Raises on failure (rate
        limit, etc.) so the caller falls through to the fallbacks."""
        tools = list(self._tool_callables(user_id).values())
        contents = self._build_contents(
            user_id, text, audio, audio_mime, image, image_mime
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.4,
            ),
        )
        return (response.text or "").strip() or "…"

    def _build_contents(
        self,
        user_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
        image: bytes | None = None,
        image_mime: str | None = None,
    ) -> list[types.Content]:
        contents: list[types.Content] = []

        for msg in self._memory.recent_messages(user_id, limit=20):
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

    def _openai_messages(self, user_id: str, new_text: str) -> list[dict]:
        msgs: list[dict] = []
        for m in self._memory.recent_messages(user_id, limit=20):
            role = "assistant" if m["role"] == "model" else "user"
            msgs.append({"role": role, "content": m["content"]})
        msgs.append({"role": "user", "content": new_text})
        return msgs

    def _fallbacks(self, user_id: str, text: str, system: str) -> str | None:
        messages = self._openai_messages(user_id, text)
        cfg = self._config

        # 1) Groq — WITH memory/tools (function calling): always-available path.
        if cfg.groq_api_key:
            try:
                answer = providers.chat_with_tools(
                    base_url=providers.GROQ_BASE_URL,
                    api_key=cfg.groq_api_key,
                    model=cfg.groq_model,
                    system=system,
                    messages=messages,
                    tools=self._openai_tools(),
                    tool_functions=self._tool_callables(user_id),
                )
                if answer:
                    log.info("Answered via Groq (%s) with tools.", cfg.groq_model)
                    return answer
            except Exception as exc:
                log.warning("Groq fallback failed (%s).", exc)

        # 2) OpenRouter — plain text (final backstop, no memory).
        if cfg.openrouter_api_key:
            try:
                answer = providers.chat_openai_compat(
                    base_url=providers.OPENROUTER_BASE_URL,
                    api_key=cfg.openrouter_api_key,
                    model=cfg.openrouter_model,
                    system=system,
                    messages=messages,
                )
                if answer:
                    log.info("Answered via OpenRouter (%s).", cfg.openrouter_model)
                    return answer
            except Exception as exc:
                log.warning("OpenRouter fallback failed (%s).", exc)

        # 3) Ollama — local model, never rate-limited (final safety net).
        if cfg.ollama_enabled:
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
                    return answer
            except Exception as exc:
                log.warning("Ollama fallback failed (%s).", exc)

        return None

    def _transcribe(self, audio: bytes, audio_mime: str | None) -> str | None:
        """Transcribe audio via Groq Whisper (for the fallback path)."""
        if not self._config.groq_api_key:
            return None
        try:
            return providers.transcribe_groq(
                api_key=self._config.groq_api_key,
                model=self._config.groq_whisper_model,
                audio=audio,
            )
        except Exception as exc:
            log.warning("Transcription (Groq Whisper) failed (%s).", exc)
            return None
