"""O cérebro da E.V. — orquestra LLM + memória + personalidade + ferramentas.

Camada reutilizável: qualquer interface (Telegram hoje, terminal/web depois)
chama `Brain.respond(...)` com texto ou áudio e recebe a resposta em texto.

Estratégia multi-provedor (para maximizar requisições grátis e nunca ficar mudo):
  1. GEMINI (principal) — mais esperto, escuta áudio nativo e salva memória via
     function calling automático do SDK google-genai.
  2. GROQ (fallback) — Llama 3.3 70B, rápido, 30 req/min. Se o Gemini falhar
     (rate limit etc.), a E.V. continua conversando por aqui. Áudio é transcrito
     antes pelo Whisper do Groq.
  3. OPENROUTER (fallback final) — variedade de modelos abertos.

Os fallbacks tratam só TEXTO e NÃO fazem function calling: a memória de longo
prazo continua sendo LIDA (fatos no system prompt), mas o salvamento automático
daquele turno é pulado. Provedores sem chave configurada são ignorados.
"""

from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types

from ..providers import llm as providers
from ..config import Config
from .memory import Memory
from ..personality import SYSTEM_PROMPT

log = logging.getLogger("ev.brain")

# Última cartada: todos os provedores falharam (ou sem chaves de fallback).
_ALL_DOWN_MSG = (
    "Opa, todos os meus cérebros estão no limite agora (plano grátis tem "
    "cota por minuto). Me dá uns segundos e tenta de novo, tá? 🕷️"
)

# Schemas das ferramentas no formato OpenAI (para o caminho Groq/fallback).
# O caminho Gemini usa as próprias funções Python (introspecção do SDK).
_OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "salvar_memoria",
            "description": (
                "Guarda um fato importante e duradouro sobre o usuário para "
                "lembrar no futuro (nome, preferências, pessoas, projetos, rotinas)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fato": {
                        "type": "string",
                        "description": "o fato a memorizar, em uma frase curta",
                    }
                },
                "required": ["fato"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "criar_lembrete",
            "description": "Cria um lembrete para o usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "o que lembrar"},
                    "quando": {
                        "type": "string",
                        "description": "data/hora em ISO 8601, se especificado",
                    },
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_lembretes",
            "description": "Lista os lembretes em aberto do usuário.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


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
    ) -> str:
        """Gera a resposta da E.V. para uma mensagem (texto OU áudio).

        Roda as chamadas bloqueantes numa thread para não travar o event loop.
        """
        return await asyncio.to_thread(
            self._respond_sync, user_id, text, audio, audio_mime
        )

    # -----------------------------------------------------------------------

    def _respond_sync(
        self,
        user_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
    ) -> str:
        system_instruction = self._system_instruction(user_id)
        user_repr = text if text is not None else "[mensagem de voz]"
        answer: str | None = None

        # 1) Gemini — provedor principal (áudio nativo + memória).
        try:
            answer = self._gemini(user_id, text, audio, audio_mime, system_instruction)
        except Exception as exc:
            log.warning("Gemini falhou (%s). Tentando fallbacks...", exc)

            # Fallbacks só tratam texto: áudio precisa ser transcrito antes.
            fb_text = text
            if audio is not None:
                fb_text = self._transcribe(audio, audio_mime)
                if fb_text:
                    user_repr = fb_text

            if fb_text:
                answer = self._fallbacks(user_id, fb_text, system_instruction)

        if not answer:
            return _ALL_DOWN_MSG

        # Persiste o turno na memória de conversa.
        self._memory.add_message(user_id, "user", user_repr)
        self._memory.add_message(user_id, "model", answer)
        return answer

    # --- system prompt ------------------------------------------------------

    def _system_instruction(self, user_id: str) -> str:
        facts = self._memory.all_facts(user_id)
        system = SYSTEM_PROMPT
        if facts:
            system += "\n\n## O que você já sabe sobre o usuário\n"
            system += "\n".join(f"- {f}" for f in facts)
        return system

    # --- provedor principal: Gemini ----------------------------------------

    def _tool_callables(self, user_id: str) -> dict:
        """As três ferramentas ligadas a ESTE usuário. Usadas tanto pelo Gemini
        (funções Python) quanto pelo Groq (dispatch do function calling)."""

        def salvar_memoria(fato: str) -> str:
            """Guarda um fato importante e duradouro sobre o usuário para lembrar
            no futuro (nome, preferências, pessoas, projetos, rotinas).

            Args:
                fato: o fato a memorizar, em uma frase curta.
            """
            self._memory.add_fact(user_id, fato)
            return "ok, memorizado"

        def criar_lembrete(texto: str, quando: str | None = None) -> str:
            """Cria um lembrete para o usuário.

            Args:
                texto: o que lembrar.
                quando: data/hora em ISO 8601, se o usuário especificou (opcional).
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

        return {
            "salvar_memoria": salvar_memoria,
            "criar_lembrete": criar_lembrete,
            "listar_lembretes": listar_lembretes,
        }

    def _gemini(
        self,
        user_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
        system_instruction: str,
    ) -> str:
        """Chama o Gemini com memória (function calling). Levanta exceção em falha
        (rate limit etc.) para o chamador cair nos fallbacks."""
        tools = list(self._tool_callables(user_id).values())
        contents = self._build_contents(user_id, text, audio, audio_mime)

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

        # 1) Groq — COM memória (function calling): provedor sempre disponível.
        if cfg.groq_api_key:
            try:
                answer = providers.chat_with_tools(
                    base_url=providers.GROQ_BASE_URL,
                    api_key=cfg.groq_api_key,
                    model=cfg.groq_model,
                    system=system,
                    messages=messages,
                    tools=_OPENAI_TOOLS,
                    tool_functions=self._tool_callables(user_id),
                )
                if answer:
                    log.info("Respondido via Groq (%s) com memória.", cfg.groq_model)
                    return answer
            except Exception as exc:
                log.warning("Fallback Groq falhou (%s).", exc)

        # 2) OpenRouter — texto puro (backstop final, sem memória).
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
                    log.info("Respondido via OpenRouter (%s).", cfg.openrouter_model)
                    return answer
            except Exception as exc:
                log.warning("Fallback OpenRouter falhou (%s).", exc)

        return None

    def _transcribe(self, audio: bytes, audio_mime: str | None) -> str | None:
        """Transcreve áudio via Whisper do Groq (para o caminho de fallback)."""
        if not self._config.groq_api_key:
            return None
        try:
            return providers.transcribe_groq(
                api_key=self._config.groq_api_key,
                model=self._config.groq_whisper_model,
                audio=audio,
            )
        except Exception as exc:
            log.warning("Transcrição (Groq Whisper) falhou (%s).", exc)
            return None
