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
from google.genai import types

from ..config import Config
from ..personality import SYSTEM_PROMPT
from ..providers import documents as documents_mod, embeddings, llm as providers, tools as tools_mod
from . import knowledge
from .commands import Commands
from .memory import Memory

log = logging.getLogger("ev.brain")

# Last resort: every provider failed (or no fallback keys configured).
_ALL_DOWN_MSG = (
    "Opa, todos os meus cérebros estão no limite agora (o plano grátis tem cota "
    "por minuto). Me dá uns segundos e tenta de novo, tá?"
)

# Commands that can't run in the pure logic layer (they send files, drive the
# Telegram UI, or run a live timer). The LLM's executar_comando queues these and
# the interface executes them with the chat context.
_INTERFACE_COMMANDS = frozenset({
    "foco", "silenciar", "exportar", "status", "resumir", "limparchat",
    "dados", "limpar", "quiz", "insights", "modelo", "ajuda", "documento",
    "transcrever", "menu", "provedor", "padroes",
})


class Brain:
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

    async def ask(self, system: str, prompt: str) -> str | None:
        """One-off LLM call (no memory/tools) through the provider chain.
        Used by features like quizzes and weekly insights."""
        return await asyncio.to_thread(self._ask_sync, system, prompt)

    async def transcribe(self, audio: bytes, mime: str | None) -> str | None:
        """Transcribe an audio file to text (Groq Whisper). For /transcrever."""
        return await asyncio.to_thread(self._transcribe, audio, mime)

    async def ocr_image(self, image: bytes, mime: str | None) -> str | None:
        """Extract text from an image via Gemini vision (OCR)."""
        return await asyncio.to_thread(self._ocr_sync, image, mime)

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

    async def describe_image(self, image: bytes, mime: str | None, prompt: str) -> str:
        """One-off vision description (for live camera / 'what is this'). NOT
        persisted to any conversation. Returns '' on failure."""
        return await asyncio.to_thread(self._describe_sync, image, mime, prompt)

    def _describe_sync(self, image: bytes, mime: str | None, prompt: str) -> str:
        try:
            resp = self._client.models.generate_content(
                model=self.current_model(),
                contents=[
                    types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"),
                    types.Part.from_text(text=prompt),
                ],
                config=types.GenerateContentConfig(temperature=0.2),
            )
            return (resp.text or "").strip()
        except Exception as exc:
            log.warning("describe_image failed (%s)", exc)
            return ""

    async def extract_receipt(self, image: bytes, mime: str | None) -> dict | None:
        """Read a receipt/invoice image -> {amount, description, category} or None."""
        return await asyncio.to_thread(self._extract_receipt_sync, image, mime)

    @staticmethod
    def _parse_receipt_json(raw: str) -> dict | None:
        """Parse the vision model's JSON reply into a validated expense dict."""
        import json
        import re
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
        try:
            amount = round(float(str(d.get("valor", 0)).replace(",", ".").strip()), 2)
        except (ValueError, TypeError):
            return None
        if amount <= 0:
            return None
        desc = (str(d.get("descricao") or "").strip() or "compra")[:80]
        cat = re.sub(r"[^a-zà-ú0-9]", "",
                     str(d.get("categoria") or "geral").strip().lower()) or "geral"
        return {"amount": amount, "description": desc, "category": cat}

    def _extract_receipt_sync(self, image: bytes, mime: str | None) -> dict | None:
        prompt = (
            "Esta imagem é um comprovante, nota fiscal ou recibo. Extraia o gasto e "
            "responda APENAS um JSON, sem texto ao redor, com as chaves: "
            "\"valor\" (número — o TOTAL pago), "
            "\"descricao\" (estabelecimento ou o que foi comprado, curto), "
            "\"categoria\" (UMA palavra: mercado, comida, transporte, saude, lazer, "
            "casa, assinatura, etc). "
            "Se não for um comprovante ou não achar o total, responda {\"valor\": 0}."
        )
        try:
            resp = self._client.models.generate_content(
                model=self.current_model(),
                contents=[
                    types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"),
                    types.Part.from_text(text=prompt),
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return self._parse_receipt_json(resp.text or "")
        except Exception as exc:
            log.warning("receipt extraction (Gemini vision) failed (%s)", exc)
            return None

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

    def _ocr_sync(self, image: bytes, mime: str | None) -> str | None:
        try:
            resp = self._client.models.generate_content(
                model=self.current_model(),
                contents=[
                    types.Part.from_bytes(data=image, mime_type=mime or "image/jpeg"),
                    types.Part.from_text(
                        text="Extraia TODO o texto visível nesta imagem, exatamente "
                        "como está, preservando as quebras de linha. Não comente nem "
                        "resuma. Se não houver texto, responda apenas: (sem texto)"
                    ),
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return (resp.text or "").strip() or None
        except Exception as exc:
            log.warning("OCR (Gemini vision) failed (%s)", exc)
            return None

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

        def criar_lembrete(texto: str, quando: str = "") -> str:
            """Cria um lembrete para o usuário.

            Args:
                texto: o que lembrar.
                quando: data/hora em ISO 8601 (ex: 2026-07-22T09:00:00-03:00).
            """
            rid = self._memory.add_reminder(user_id, texto, quando or None)
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

        def listar_memorias() -> str:
            """Lista as memórias/fatos salvos sobre o usuário, com seus IDs.
            Use ANTES de apagar, para descobrir o ID certo."""
            items = self._memory.list_facts(user_id)
            if not items:
                return "não há memórias salvas"
            return "; ".join(f"#{f['id']}: {f['fact']}" for f in items)

        def apagar_memoria(id: int) -> str:
            """Apaga UMA memória/fato do usuário pelo ID. Se o usuário descrever
            a memória em vez do número, chame listar_memorias primeiro para achar o ID.

            Args:
                id: o número (ID) da memória a apagar.
            """
            facts = {f["id"]: f["fact"] for f in self._memory.list_facts(user_id)}
            if int(id) not in facts:
                return f"não encontrei a memória #{id}"
            self._memory.delete_fact(user_id, int(id))
            return f"apaguei a memória #{id}: {facts[int(id)]}"

        def apagar_lembrete(id: int) -> str:
            """Cancela/apaga um lembrete do usuário pelo ID (veja em listar_lembretes).

            Args:
                id: o número (ID) do lembrete a apagar.
            """
            ok = self._memory.cancel_reminder(user_id, int(id))
            return f"apaguei o lembrete #{id}" if ok else f"não encontrei o lembrete #{id}"

        def executar_comando(comando: str, argumentos: str = "") -> str:
            """Executa QUALQUER comando da E.V. em nome do usuário — use para fazer
            hands-free (por voz ou texto) o que ele normalmente faria manualmente:
            criar/listar/concluir tarefas, gastos, orçamentos, hábitos, diário,
            links, assinaturas, monitores web, agenda/eventos/e-mail, buscar, etc.
            Também apaga itens (ex: comando 'esquecer', 'gastorm', 'cancelar').

            Comandos disponíveis: tarefa, tarefas, concluir, lembrete, lembretes,
            rotina, cancelar, calendario, lembrar, memorias, esquecer, gasto, gastos,
            gastorm, orcamento, orcamentos, orcamentorm, relatorio, habito, feito,
            habitos, habitorm, diario, diariorm, link, links, linkrm, procurar,
            buscar, noticias, clima, kb, kbrm, kbweb, semana, vigiar, vigias,
            vigiarm, assinatura, assinaturas, assinaturarm, agenda, evento, email,
            emails (ler/resumir e-mails recentes da caixa; sem argumento traz os
            não lidos; com um termo faz busca simples, ex: 'faturas'),
            foco, silenciar, exportar, status, resumir, limparchat, dados, limpar,
            quiz, insights, modelo, documento, transcrever, ajuda, menu.

            Args:
                comando: o nome do comando (ex: 'gasto', 'tarefa', 'foco', 'status').
                argumentos: os argumentos no mesmo formato do comando
                    (ex: '50 mercado #casa' para gasto; 'estudar #faculdade' para tarefa).
            """
            # The model sometimes stuffs the args into `comando`
            # (e.g. comando="tarefa comprar pão", argumentos=""). Split so the
            # command name is just the first token and the rest becomes args.
            raw = (comando or "").strip().lstrip("/")
            tokens = raw.split(None, 1)
            key = (tokens[0] if tokens else "").lower()
            argumentos = (argumentos or "").strip()
            if len(tokens) > 1 and not argumentos:
                argumentos = tokens[1]
            log.info("[executar_comando] comando=%r -> key=%r args=%r",
                     comando, key, argumentos)
            if key in self._commands.runnable():
                out = self._commands.run(user_id, key, argumentos)  # runs now (text)
                log.info("[executar_comando] %s -> %s", key, str(out)[:160])
                return out
            if key in _INTERFACE_COMMANDS:
                # Needs the chat context — queue it for the interface to run.
                self._last_actions.append({"command": key, "args": argumentos})
                return f"ok, executando '{key}' agora"
            out = self._commands.run(user_id, key, argumentos)  # -> "não conheço"
            log.info("[executar_comando] unknown %r -> %s", key, str(out)[:120])
            return out

        def consultar_clima(cidade: str) -> str:
            """Consulta a previsão do tempo real (hoje e próximos dias) de uma cidade.

            Args:
                cidade: nome da cidade (ex: São Paulo).
            """
            return tools_mod.weather_forecast(cidade or cfg.city or "São Paulo")

        def consultar_noticias(assunto: str) -> str:
            """Busca as notícias mais recentes (últimos dias) sobre um assunto.
            Use isto sempre que perguntarem sobre notícias/atualidades.

            Args:
                assunto: tema das notícias (ex: tecnologia, Brasil, futebol).
            """
            return tools_mod.news(assunto or cfg.news_topic or "Brasil", tavily_key=cfg.tavily_api_key)

        def criar_documento(
            conteudo: str,
            titulo: str = "",
            formato: str = "pdf",
            salvar_kb: bool = False,
        ) -> str:
            """Cria um arquivo (txt, md, pdf ou docx/word) com o conteúdo e o
            ENVIA para o usuário no chat. Use quando pedirem algo "em pdf",
            "em word", "num arquivo", "um documento", ou para exportar um texto.

            Args:
                conteudo: o texto completo do documento (já escrito por você).
                titulo: título/nome do documento (ex: "Lista de compras").
                formato: txt, md, pdf ou docx (padrão pdf; "word" vira docx).
                salvar_kb: se True, também guarda o conteúdo na base de conhecimento.
            """
            title = (titulo or "Documento").strip()
            try:
                data, filename = documents_mod.build(formato, title, conteudo)
            except ValueError as exc:
                return str(exc)
            saved_kb = False
            if salvar_kb and (conteudo or "").strip():
                try:
                    knowledge.ingest_text(conteudo, title, cfg, self._memory, user_id)
                    saved_kb = True
                except Exception as exc:  # KB is a bonus — never fail the doc
                    log.warning("criar_documento KB ingest failed (%s)", exc)
            self._last_documents.append({
                "bytes": data, "filename": filename,
                "title": title, "content": conteudo, "saved_kb": saved_kb,
            })
            extra = " e guardei na base de conhecimento" if saved_kb else ""
            return f"documento '{filename}' criado{extra}; será enviado ao usuário agora"

        def anotar_pessoa(nome: str, sobre: str = "", aniversario: str = "") -> str:
            """Registra/atualiza uma pessoa importante do usuário (família, amigo,
            colega): quem é, contexto e aniversário. Use quando ele falar de alguém
            que vale lembrar.

            Args:
                nome: nome da pessoa.
                sobre: nota curta (relação, contexto, preferências).
                aniversario: data de aniversário, ex '12/03' ou '1998-03-12'.
            """
            self._memory.add_person(user_id, nome, sobre, aniversario)
            return f"anotado sobre {nome}"

        def sobre_pessoa(nome: str) -> str:
            """Recupera o que o usuário já registrou sobre uma pessoa, pelo nome.

            Args:
                nome: nome (ou parte) da pessoa.
            """
            p = self._memory.find_person(user_id, nome)
            if not p:
                return f"não tenho nada registrado sobre {nome} ainda"
            parts = [p["name"]]
            if p.get("notes"):
                parts.append(p["notes"])
            if p.get("birthday"):
                parts.append("aniversário: " + p["birthday"])
            return " — ".join(parts)

        def minha_localizacao() -> str:
            """Retorna a última localização conhecida do usuário (do dispositivo, via
            o app web). Use quando ele perguntar 'onde eu estou' ou precisar do
            contexto de local."""
            lat = self._memory.get_setting("loc_lat")
            lng = self._memory.get_setting("loc_lng")
            if not (lat and lng):
                return ("ainda não sei sua localização. Abra a aba Mapa na E.V. e "
                        "toque em 'Onde estou' pra eu passar a saber.")
            addr = self._memory.get_setting("loc_addr") or ""
            link = f"https://www.google.com/maps/@{lat},{lng},16z"
            head = f"você está em {addr} " if addr else ""
            return f"{head}({lat}, {lng}). Ver no mapa: {link}"

        def locais_proximos(tipo: str) -> str:
            """Lista lugares reais de um tipo perto da localização atual do usuário
            (nome + distância), buscando no OpenStreetMap.

            Args:
                tipo: o que procurar, ex 'farmácia', 'mercado', 'restaurante'.
            """
            lat = self._memory.get_setting("loc_lat")
            lng = self._memory.get_setting("loc_lng")
            if not (lat and lng):
                return ("não sei sua localização ainda. Abra a aba Mapa e toque em "
                        "'Onde estou'.")
            flat, flng = float(lat), float(lng)
            places = tools_mod.nearby_places(flat, flng, tipo, limit=6)
            if not places:
                return f"não achei '{tipo}' por perto agora."
            # A map photo of the area with every result pinned, plus a route link
            # per place so the user can navigate straight there.
            img = tools_mod.static_map_url(
                flat, flng, markers=[(p["lat"], p["lng"]) for p in places], zoom=15)
            lines = [f"{tipo.capitalize()} perto de você:", f"![mapa]({img})"]
            for i, p in enumerate(places, 1):
                dl = tools_mod.directions_link(flat, flng, p["lat"], p["lng"])
                lines.append(f"{i}. {p['name']} (~{int(p['dist'])} m) — 🧭 Ir: {dl}")
            return "\n".join(lines)

        def meus_locais() -> str:
            """Lista os pontos de interesse que o usuário salvou no mapa da E.V."""
            places = self._memory.list_places(user_id)
            if not places:
                return "você ainda não salvou nenhum ponto no mapa."
            return "Seus pontos salvos: " + ", ".join(p["name"] for p in places)

        def salvar_local(nome: str, endereco: str = "") -> str:
            """Salva um ponto de interesse no mapa do usuário (ex: Faculdade, Casa).
            Se um endereço for dado, geocodifica; senão usa a localização atual.

            Args:
                nome: apelido do ponto (ex: 'Faculdade').
                endereco: endereço/local a geocodificar (opcional).
            """
            if endereco.strip():
                g = tools_mod.geocode(endereco)
                if not g:
                    return f"não achei o endereço '{endereco}'. Pode detalhar mais?"
                lat, lng = g["lat"], g["lng"]
            else:
                slat = self._memory.get_setting("loc_lat")
                slng = self._memory.get_setting("loc_lng")
                if not (slat and slng):
                    return ("me diz o endereço, ou abra o Mapa e toque em 'Onde estou' "
                            "pra eu salvar na sua posição atual.")
                lat, lng = float(slat), float(slng)
            self._memory.add_place(user_id, nome, lat, lng)
            return f"ponto '{nome}' salvo no seu mapa."

        def criar_automacao(gatilho: str, acao: str, hora: int = -1, minuto: int = 0,
                            dia_semana: int = -1, valor: float = 0.0, categoria: str = "",
                            mensagem: str = "", comando: str = "") -> str:
            """Cria uma automação 'quando X, faça Y' que roda sozinha depois.

            Args:
                gatilho: 'time' (horário recorrente), 'expense_over' (gasto acima de
                    um valor) ou 'task_overdue' (quando uma tarefa vencer).
                acao: 'notify' (avisar com uma mensagem), 'command' (rodar um comando
                    da E.V.) ou 'reschedule' (remarcar tarefas vencidas; só com task_overdue).
                hora: para 'time', hora 0-23.
                minuto: para 'time', minuto 0-59.
                dia_semana: para 'time', 0=segunda..6=domingo, ou -1 para todo dia.
                valor: para 'expense_over', o limite em reais.
                categoria: para 'expense_over', categoria opcional (ex 'comida').
                mensagem: para 'notify', o texto do aviso.
                comando: para 'command', o comando a rodar (ex 'semana', 'relatorio').

            Ex: 'toda sexta 18h me manda o resumo' -> gatilho='time', hora=18,
            dia_semana=4, acao='command', comando='semana'. 'quando eu gastar mais de
            200 me avisa' -> gatilho='expense_over', valor=200, acao='notify',
            mensagem='Gasto acima de 200!'.
            """
            aid, msg = self._commands.create_automation(
                user_id, gatilho, acao,
                hour=(None if hora < 0 else hora), minute=minuto, weekday=dia_semana,
                amount=(None if valor <= 0 else valor), category=(categoria or None),
                message=(mensagem or None), command=(comando or None))
            return ("automação criada: " + msg) if aid else ("não consegui criar: " + msg)

        def criar_pagina(nome: str, tarefas_categoria: str = "", nota: str = "",
                        conector: str = "", grafico: bool = False, comando: str = "") -> str:
            """Cria uma página/painel personalizado na interface do usuário, montada
            com widgets seguros. Use para 'cria uma página X com ...'.

            Args:
                nome: nome da página (ex 'Faculdade').
                tarefas_categoria: mostra tarefas dessa categoria ('todas' pra todas).
                nota: um texto/nota fixa no painel.
                conector: nome de um conector pra mostrar o valor.
                grafico: True mostra um gráfico de gastos por categoria.
                comando: um comando da E.V. pra virar botão (ex 'semana').
            """
            widgets = []
            if nota.strip():
                widgets.append({"type": "note", "text": nota.strip()})
            if tarefas_categoria.strip():
                cat = tarefas_categoria.strip()
                widgets.append({"type": "tasks",
                                "category": "" if cat.lower() in ("todas", "all", "*") else cat})
            if grafico:
                widgets.append({"type": "chart"})
            if conector.strip():
                widgets.append({"type": "connector", "name": conector.strip()})
            if comando.strip():
                widgets.append({"type": "command", "cmd": comando.strip(), "label": comando.strip()})
            if not widgets:
                return "me diga o que colocar na página (tarefas, nota, gráfico ou um conector)."
            self._memory.add_page(user_id, nome.strip()[:60] or "Página", widgets)
            return (f"pronto — criei a página '{nome.strip()}' com {len(widgets)} "
                    f"widget(s). Ela aparece em 'Páginas' no painel.")

        def consultar_conector(nome: str) -> str:
            """Consulta um conector de API que o usuário criou (pelo nome) e retorna
            o valor atual. Use quando ele perguntar algo que um conector dele cobre
            (ex 'qual a cotação do dólar?' se ele tiver um conector de cotação).

            Args:
                nome: o nome do conector configurado.
            """
            import os as _os
            import re as _re
            import json as _json
            from ..providers import connectors as _cn
            c = self._memory.get_connector(user_id, nome)
            if not c:
                av = [x["name"] for x in self._memory.list_connectors(user_id)]
                return (f"não achei o conector '{nome}'."
                        + (f" Você tem: {', '.join(av)}." if av else
                           " Você ainda não criou conectores (aba Conectores)."))
            def sub(s):
                return _re.sub(r"\{\{\s*([A-Z][A-Z0-9_]{1,39})\s*\}\}",
                               lambda m: _os.environ.get(m.group(1), ""), s or "")
            val, err = _cn.fetch(sub(c["url"]),
                                 {k: sub(v) for k, v in (c["headers"] or {}).items()},
                                 c["path"])
            if err:
                return f"não consegui consultar '{c['name']}': {err}"
            if isinstance(val, (dict, list)):
                val = _json.dumps(val, ensure_ascii=False)[:600]
            return f"{c['name']}: {str(val)[:600]}"

        def planejar_dia() -> str:
            """Monta um plano acionável para o dia do usuário, juntando as tarefas
            abertas, os lembretes, a agenda, o clima e a localização atual, e
            priorizando tudo. Use quando ele pedir 'resolve minha manhã', 'plano do
            dia', 'organiza meu dia', 'o que eu faço hoje'."""
            return self._plan_day_sync(user_id)

        callables: dict = {
            "executar_comando": executar_comando,
            "planejar_dia": planejar_dia,
            "criar_automacao": criar_automacao,
            "consultar_conector": consultar_conector,
            "criar_pagina": criar_pagina,
            "anotar_pessoa": anotar_pessoa,
            "sobre_pessoa": sobre_pessoa,
            "minha_localizacao": minha_localizacao,
            "locais_proximos": locais_proximos,
            "meus_locais": meus_locais,
            "salvar_local": salvar_local,
            "salvar_memoria": salvar_memoria,
            "listar_memorias": listar_memorias,
            "apagar_memoria": apagar_memoria,
            "criar_lembrete": criar_lembrete,
            "listar_lembretes": listar_lembretes,
            "apagar_lembrete": apagar_lembrete,
            "consultar_clima": consultar_clima,
            "consultar_noticias": consultar_noticias,
            "criar_documento": criar_documento,
        }

        if cfg.websearch_enabled:
            def buscar_web(consulta: str) -> str:
                """Busca informação atual na internet.

                Args:
                    consulta: o que pesquisar.
                """
                return tools_mod.web_search(
                    consulta,
                    brave_key=self._config.brave_api_key,
                    tavily_key=self._config.tavily_api_key,
                )

            callables["buscar_web"] = buscar_web

        if cfg.google_oauth_client:
            def ver_agenda() -> str:
                """Lista os próximos eventos da agenda do Google do usuário."""
                return tools_mod.calendar_upcoming(cfg, cfg.default_account)

            def criar_evento(titulo: str, inicio: str, fim: str) -> str:
                """Cria um evento na agenda do Google.

                Args:
                    titulo: título do evento.
                    inicio: início em ISO 8601.
                    fim: fim em ISO 8601.
                """
                return tools_mod.calendar_create(
                    cfg, cfg.default_account, titulo, inicio, fim)

            def enviar_email(para: str, assunto: str, corpo: str) -> str:
                """Envia um e-mail pela conta Gmail do usuário.

                Args:
                    para: endereço de e-mail do destinatário.
                    assunto: assunto do e-mail.
                    corpo: corpo do e-mail.
                """
                return tools_mod.send_email(
                    cfg, cfg.default_account, para, assunto, corpo)

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
                "planejar_dia",
                "Monta um plano acionável do dia do usuário juntando tarefas, "
                "lembretes, agenda, clima e localização. Use para 'resolve minha "
                "manhã', 'plano do dia', 'organiza meu dia', 'o que faço hoje'.",
            ),
            fn(
                "criar_pagina",
                "Cria uma página/painel personalizado na interface, com widgets "
                "seguros (tarefas, nota, gráfico de gastos, conector, botão). Use "
                "para 'cria uma página X com minhas tarefas de Y e um gráfico'.",
                {
                    "nome": {"type": s, "description": "nome da página"},
                    "tarefas_categoria": {"type": s, "description": "categoria de tarefas ('todas' p/ todas)"},
                    "nota": {"type": s, "description": "texto fixo no painel"},
                    "conector": {"type": s, "description": "nome de um conector"},
                    "grafico": {"type": "boolean", "description": "mostrar gráfico de gastos"},
                    "comando": {"type": s, "description": "comando pra virar botão"},
                },
                ["nome"],
            ),
            fn(
                "consultar_conector",
                "Consulta um conector de API que o usuário criou (pelo nome) e "
                "retorna o valor atual. Use quando a pergunta dele bate com um "
                "conector configurado.",
                {"nome": {"type": s, "description": "nome do conector"}},
                ["nome"],
            ),
            fn(
                "criar_automacao",
                "Cria uma automação 'quando X, faça Y' que roda sozinha. gatilho: "
                "'time'|'expense_over'|'task_overdue'. acao: 'notify'|'command'|"
                "'reschedule'. Use para 'toda sexta 18h me manda o resumo', 'quando "
                "eu gastar mais de 200 me avisa', 'se uma tarefa vencer, remarca'.",
                {
                    "gatilho": {"type": s, "description": "time|expense_over|task_overdue"},
                    "acao": {"type": s, "description": "notify|command|reschedule"},
                    "hora": {"type": "integer", "description": "para time: 0-23"},
                    "minuto": {"type": "integer", "description": "para time: 0-59"},
                    "dia_semana": {"type": "integer", "description": "0=seg..6=dom, -1=todo dia"},
                    "valor": {"type": "number", "description": "para expense_over: limite em R$"},
                    "categoria": {"type": s, "description": "para expense_over: categoria opcional"},
                    "mensagem": {"type": s, "description": "para notify: texto do aviso"},
                    "comando": {"type": s, "description": "para command: ex 'semana'"},
                },
                ["gatilho", "acao"],
            ),
            fn(
                "executar_comando",
                "Executa QUALQUER comando da E.V. em nome do usuário (hands-free por "
                "voz/texto). CRIAR/EDITAR/APAGAR/CONCLUIR sempre passa por aqui — nunca "
                "afirme que fez sem chamar esta ferramenta. Tarefas: 'tarefa' (criar, ex "
                "args 'comprar leite #mercado'), 'tarefas' (listar), 'concluir' (por id "
                "OU nome, ex 'comprar leite'), 'tarefarm' (apagar por id/nome), "
                "'tarefaeditar' (args '<nome/id> | <novo texto> [#cat]'). Também: lembrete, "
                "lembretes, rotina, cancelar, calendario, lembrar, memorias, esquecer, "
                "gasto, gastos, gastorm (apaga gasto por id OU descrição), gastoeditar "
                "(edita gasto por nome: '<nome/id> | <valor> [descrição] [#cat]'), orcamento, "
                "orcamentos, orcamentorm, relatorio, habito, feito (por nome), habitos, "
                "habitorm (por nome), diario, diariorm, link, links, linkrm (por id OU nome), "
                "cancelar (lembrete por id OU texto), lembreteeditar (edita lembrete por nome: "
                "'<nome/id> | <novo texto> [| <novo tempo>]'), esquecer (memória por id OU conteúdo), "
                "procurar, buscar, noticias, clima, kb, kbrm, kbweb, semana, vigiar, vigias, "
                "vigiarm, assinatura, assinaturas, assinaturarm, agenda, evento, email.",
                {
                    "comando": {"type": s, "description": "nome do comando, ex: 'gasto'"},
                    "argumentos": {"type": s, "description": "argumentos no formato do comando"},
                },
                ["comando"],
            ),
            fn(
                "salvar_memoria",
                "Guarda um fato duradouro sobre o usuário.",
                {"fato": {"type": s, "description": "o fato, em uma frase curta"}},
                ["fato"],
            ),
            fn(
                "anotar_pessoa",
                "Registra/atualiza uma pessoa importante (família, amigo, colega): "
                "quem é, contexto e aniversário.",
                {
                    "nome": {"type": s, "description": "nome da pessoa"},
                    "sobre": {"type": s, "description": "nota curta (relação/contexto)"},
                    "aniversario": {"type": s, "description": "ex '12/03' ou '1998-03-12'"},
                },
                ["nome"],
            ),
            fn(
                "sobre_pessoa",
                "Recupera o que o usuário registrou sobre uma pessoa, pelo nome.",
                {"nome": {"type": s, "description": "nome (ou parte) da pessoa"}},
                ["nome"],
            ),
            fn(
                "minha_localizacao",
                "Última localização conhecida do usuário (do dispositivo). Use para "
                "'onde estou' ou contexto de local.",
            ),
            fn(
                "locais_proximos",
                "Lista lugares reais (nome + distância) de um tipo perto do usuário.",
                {"tipo": {"type": s, "description": "ex: farmácia, mercado, restaurante"}},
                ["tipo"],
            ),
            fn("meus_locais", "Lista os pontos de interesse que o usuário salvou no mapa."),
            fn(
                "salvar_local",
                "Salva um ponto no mapa do usuário (ex: Faculdade). Com endereço, "
                "geocodifica; sem, usa a localização atual.",
                {"nome": {"type": s, "description": "apelido, ex 'Faculdade'"},
                 "endereco": {"type": s, "description": "endereço a geocodificar (opcional)"}},
                ["nome"],
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
            fn(
                "listar_memorias",
                "Lista as memórias/fatos salvos sobre o usuário, com IDs. "
                "Use antes de apagar para achar o ID certo.",
            ),
            fn(
                "apagar_memoria",
                "Apaga UMA memória/fato do usuário pelo ID.",
                {"id": {"type": "integer", "description": "ID da memória (de listar_memorias)"}},
                ["id"],
            ),
            fn("listar_lembretes", "Lista os lembretes em aberto do usuário."),
            fn(
                "apagar_lembrete",
                "Cancela/apaga um lembrete do usuário pelo ID.",
                {"id": {"type": "integer", "description": "ID do lembrete (de listar_lembretes)"}},
                ["id"],
            ),
            fn(
                "consultar_clima",
                "Consulta a previsão do tempo real (hoje/próximos dias) de uma cidade.",
                {"cidade": {"type": s, "description": "nome da cidade"}},
                ["cidade"],
            ),
            fn(
                "consultar_noticias",
                "Busca notícias recentes (últimos dias) sobre um assunto.",
                {"assunto": {"type": s, "description": "tema das notícias"}},
                ["assunto"],
            ),
            fn(
                "criar_documento",
                "Cria um arquivo (txt, md, pdf ou docx/word) com o conteúdo e o "
                "envia ao usuário. Use quando pedirem algo 'em pdf', 'em word', "
                "'num arquivo' ou 'um documento'.",
                {
                    "conteudo": {"type": s, "description": "o texto completo do documento"},
                    "titulo": {"type": s, "description": "título/nome do documento"},
                    "formato": {"type": s, "description": "txt, md, pdf ou docx (padrão pdf)"},
                    "salvar_kb": {"type": "boolean", "description": "também guardar na base de conhecimento"},
                },
                ["conteudo"],
            ),
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
                    fr = getattr(part, "function_response", None)
                    if fr:
                        log.info("[gemini-afc] resultado %s: %s", fr.name,
                                 str(getattr(fr, "response", ""))[:160])
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

    def _transcribe(self, audio: bytes, audio_mime: str | None) -> str | None:
        """Transcribe audio via Groq Whisper (for the fallback path)."""
        if not self._config.groq_api_key:
            return None
        # Whisper detects the format from the filename extension — derive it from
        # the MIME so browser recordings (webm/mp4) and Telegram voice (ogg) work.
        ext = {
            "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4",
            "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav",
            "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/aac": "m4a",
        }.get((audio_mime or "").split(";")[0].strip(), "ogg")
        try:
            return providers.transcribe_groq(
                api_key=self._config.groq_api_key,
                model=self._config.groq_whisper_model,
                audio=audio,
                filename=f"audio.{ext}",
            )
        except Exception as exc:
            log.warning("Transcription (Groq Whisper) failed (%s).", exc)
            return None
