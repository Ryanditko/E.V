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

# NOTE: intentionally NO `from __future__ import annotations` here. Gemini's
# automatic function calling introspects the tool functions' annotations at
# runtime; PEP 563 stringized annotations make it do isinstance(value, "str")
# -> "isinstance() arg 2 must be a type..." and every tool call fails.

import asyncio
import logging
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from google import genai

from ...config import Config
from ...personality import build_system_prompt
from ...providers import embeddings
from ..commands import Commands
from ..memory import Memory
from .ask import AskMixin
from .provider_health import ProviderHealthMixin
from .providers_fallback import ProvidersFallbackMixin
from .tools import ToolsMixin
from .transcription import TranscriptionMixin

log = logging.getLogger("ev.brain")

# Last resort: every provider failed (or no fallback keys configured).
_ALL_DOWN_MSG = (
    "Opa, todos os meus cérebros estão no limite agora (o plano grátis tem cota "
    "por minuto). Me dá uns segundos e tenta de novo, tá?"
)


class Brain(
    TranscriptionMixin,
    ProviderHealthMixin,
    ToolsMixin,
    AskMixin,
    ProvidersFallbackMixin,
):
    def __init__(self, config: Config, memory: Memory) -> None:
        self._config = config
        self._client = genai.Client(api_key=config.gemini_api_key)
        self._model = config.model
        self._memory = memory
        self._commands = Commands(config, memory)  # for the hands-free command tool
        self._last_provider: str | None = None  # which provider answered last
        # Documents the LLM asked to create during the current turn. The interface
        # drains this after respond() and sends each file to the user.
        self._last_documents: list[dict] = []
        # Interface-level commands the LLM requested (foco, exportar, status...).
        # The interface drains these after respond() and runs them with chat context.
        self._last_actions: list[dict] = []
        # Tool calls made during the last turn (for the live "terminal" view).
        self._last_steps: list[dict] = []

    def pop_steps(self) -> list[dict]:
        """Return and clear the tool-call steps of the last turn (para o terminal).
        Cada item: {tool, args, result}."""
        st, self._last_steps = self._last_steps, []
        return st

    def pop_documents(self) -> list[dict]:
        """Return and clear the documents generated during the last turn.

        Each item: {bytes, filename, title, content, saved_kb}."""
        docs, self._last_documents = self._last_documents, []
        return docs

    def pop_actions(self) -> list[dict]:
        """Return and clear interface-command intents from the last turn.
        Each item: {command, args}."""
        acts, self._last_actions = self._last_actions, []
        return acts

    def current_model(self) -> str:
        """Primary Gemini model — a runtime override (via /modelo) wins over .env."""
        return self._memory.get_setting("model") or self._model

    async def respond(
        self,
        user_id: str,
        *,
        conv_id: str | None = None,
        text: str | None = None,
        audio: bytes | None = None,
        audio_mime: str | None = None,
        image: bytes | None = None,
        image_mime: str | None = None,
    ) -> str:
        """Produce E.V.'s answer to a message (text, audio, and/or image).

        `user_id` scopes durable data (facts, tasks, tools) — always the owner.
        `conv_id` scopes the CONVERSATION thread (defaults to user_id); pass the
        Telegram chat id so each group/chat keeps its own separate context.

        Runs the blocking SDK calls in a thread so the async event loop is free.
        """
        return await asyncio.to_thread(
            self._respond_sync, user_id, conv_id or user_id,
            text, audio, audio_mime, image, image_mime,
        )

    # -----------------------------------------------------------------------

    def _respond_sync(
        self,
        user_id: str,
        conv_id: str,
        text: str | None,
        audio: bytes | None,
        audio_mime: str | None,
        image: bytes | None = None,
        image_mime: str | None = None,
    ) -> str:
        self._last_documents = []  # fresh per turn; interface drains after respond()
        self._last_actions = []
        self._last_steps = []
        # Semantic recall uses the text query; audio/image-through-Gemini has none yet.
        system_instruction = self._system_instruction(user_id, text)
        if text is not None:
            user_repr = text
        elif image is not None:
            user_repr = "[imagem]"
        else:
            user_repr = "[mensagem de voz]"
        answer: str | None = None
        force = (self._memory.get_setting("force_provider") or "").strip().lower()

        if force == "gemini":
            # Forced Gemini only — no fallback (so you can actually test it).
            try:
                answer = self._gemini(
                    user_id, conv_id, text, audio, audio_mime, image, image_mime,
                    system_instruction,
                )
            except Exception as exc:
                log.warning("Forced Gemini failed (%s)", exc)
        elif force in ("groq", "openrouter", "ollama"):
            # Forced fallback provider only. Audio -> transcribe; image unsupported.
            fb_text = text
            if audio is not None:
                fb_text = self._transcribe(audio, audio_mime)
                if fb_text:
                    user_repr = fb_text
                    system_instruction = self._system_instruction(user_id, fb_text)
            if image is not None and not fb_text:
                return f"O provedor forçado ({force}) não enxerga imagens. Use /provedor gemini ou /provedor auto."
            if fb_text:
                answer = self._fallbacks(
                    user_id, conv_id, fb_text, system_instruction, only=force
                )
        else:
            # Automatic chain: Gemini -> Groq -> OpenRouter -> Ollama.
            try:
                answer = self._gemini(
                    user_id, conv_id, text, audio, audio_mime, image, image_mime,
                    system_instruction,
                )
            except Exception as exc:
                log.warning("Gemini failed (%s). Trying fallbacks...", exc)
                fb_text = text
                if audio is not None:
                    fb_text = self._transcribe(audio, audio_mime)
                    if fb_text:
                        user_repr = fb_text
                        system_instruction = self._system_instruction(user_id, fb_text)
                if image is not None and not fb_text:
                    return "Consegui receber a imagem, mas meu cérebro de visão está no limite agora. Tenta de novo em uns segundos?"
                if fb_text:
                    answer = self._fallbacks(user_id, conv_id, fb_text, system_instruction)

        if not answer:
            if force:
                return (f"O provedor forçado ({force}) não respondeu agora (pode estar "
                        "sem cota ou fora do ar). Volta pro automático com /provedor auto.")
            return _ALL_DOWN_MSG

        # Track which provider answered (for /modelo usage stats).
        try:
            self._memory.bump_usage(
                self._last_provider or "?",
                datetime.now(timezone.utc).date().isoformat(),
            )
        except Exception:
            pass

        # Persist the turn in this conversation's history (scoped by conv_id).
        self._memory.add_message(conv_id, "user", user_repr)
        self._memory.add_message(conv_id, "model", answer)
        return answer

    # --- system prompt ------------------------------------------------------

    def _system_instruction(self, user_id: str, query: str | None) -> str:
        system = build_system_prompt(self._memory.assistant_lang())

        # MODO FOCO — muda o tom das respostas enquanto ativo.
        if self._memory.get_setting("serious_mode") == "1":
            system += (
                "\n\n## MODO FOCO ATIVO\n"
                "O usuário ativou o modo foco. Responda de forma direta, "
                "concisa e tática — sem piadas, sem floreio, sem emojis. Vá "
                "direto ao ponto, tom de operação/missão, frases curtas. "
                "Continue prestativa e precisa, só que séria e focada."
            )

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
