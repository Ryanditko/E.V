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
    "transcrever", "menu", "provedor",
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
            emails (ler/resumir e-mails recentes; aceita busca do Gmail como
            argumento, ex: 'is:unread' ou 'faturas'),
            foco, silenciar, exportar, status, resumir, limparchat, dados, limpar,
            quiz, insights, modelo, documento, transcrever, ajuda, menu.

            Args:
                comando: o nome do comando (ex: 'gasto', 'tarefa', 'foco', 'status').
                argumentos: os argumentos no mesmo formato do comando
                    (ex: '50 mercado #casa' para gasto; 'estudar #faculdade' para tarefa).
            """
            key = (comando or "").strip().lower().lstrip("/")
            if key in self._commands.runnable():
                return self._commands.run(user_id, key, argumentos)  # runs now (text)
            if key in _INTERFACE_COMMANDS:
                # Needs the chat context — queue it for the interface to run.
                self._last_actions.append({"command": key, "args": argumentos or ""})
                return f"ok, executando '{key}' agora"
            return self._commands.run(user_id, key, argumentos)  # -> "não conheço"

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
            titulo: str | None = None,
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

        callables: dict = {
            "executar_comando": executar_comando,
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
        msgs: list[dict] = []
        for m in self._memory.recent_messages(conv_id, limit=20):
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

        # 2) OpenRouter — plain text (final backstop, no memory).
        if cfg.openrouter_api_key and only in (None, "openrouter"):
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
                    self._last_provider = "openrouter"
                    return answer
            except Exception as exc:
                log.warning("OpenRouter fallback failed (%s).", exc)

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
