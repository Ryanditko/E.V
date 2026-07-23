"""E.V.'s Telegram interface.

Two ways to interact:
  - Natural chat (text or voice) -> goes through the brain (LLM).
  - Slash commands (/lembrete, /tarefa, /email, ...) -> deterministic, no LLM.

It locks access to the owner (EV_OWNER_ID) when configured, and runs the reminder
scheduler as a background task that delivers due reminders to the user's chat.
"""

from __future__ import annotations

import asyncio
import html
import io
import logging
import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..config import Config
from ..core.brain import Brain
from ..core.commands import COMMAND_LIST, Commands
from ..core.memory import Memory
from ..providers import voice as voice_mod

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("ev.telegram")


class TelegramInterface:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._memory = Memory(config.db_path)
        self._brain = Brain(config, self._memory)
        self._commands = Commands(config, self._memory)
        # user_id -> pending input action (e.g. "task", "rem", "link", ...)
        self._pending: dict[str, str] = {}
        self._last_briefing: str | None = None  # date of the last daily briefing
        self._last_checkin: str | None = None    # date of the last proactive check-in
        self._last_weekly: str | None = None     # date of the last weekly review
        self._last_rain: str | None = None       # date of the last rain check
        self._last_recurring: str | None = None  # date recurring expenses were run
        self._last_tg_backup: str | None = None  # date backup was sent to Telegram
        self._last_habit_nudge: str | None = None  # date of the last habit nudge
        self._last_monthly: str | None = None      # month of the last financial report
        # Keep references to background tasks so they aren't garbage-collected
        # (a GC'd task would silently kill the scheduler).
        self._bg_tasks: list = []

    # --- access control -----------------------------------------------------

    def _authorized(self, update: Update) -> bool:
        if self._config.owner_id is None:
            return True  # no owner configured: answer everyone
        user = update.effective_user
        return user is not None and user.id == self._config.owner_id

    @staticmethod
    def _args(ctx: ContextTypes.DEFAULT_TYPE) -> str:
        return " ".join(ctx.args) if ctx.args else ""

    # --- chat handlers (LLM) ------------------------------------------------

    async def on_start(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        uid = user.id if user else "?"
        log.info("/start from user_id=%s", uid)
        if not self._authorized(update):
            await update.message.reply_text(
                f"Não te reconheço. Seu ID é {uid}. "
                "Se você é o dono, coloque-o em EV_OWNER_ID no .env."
            )
            return
        await update.message.reply_text(f"E.V. online, chefe. (seu ID: {uid})")
        await update.message.reply_text(
            self._MAIN_TEXT, reply_markup=self._kb_main(), parse_mode="HTML"
        )

    async def on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)

        # If a menu button asked for input, consume this message as that input
        # (no LLM) instead of treating it as a chat message.
        pending = self._pending.pop(user_id, None)
        if pending:
            result = self._handle_pending(user_id, pending, update.message.text)
            await update.message.reply_text(result, reply_markup=self._kb_main())
            return

        await self._reply(
            update, await self._brain.respond(user_id, text=update.message.text)
        )

    async def on_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)
        voice = update.message.voice
        tg_file = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        await self._reply(
            update,
            await self._brain.respond(
                user_id, audio=audio_bytes, audio_mime=voice.mime_type or "audio/ogg"
            ),
        )

    async def on_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)
        photo = update.message.photo[-1]  # largest resolution
        tg_file = await ctx.bot.get_file(photo.file_id)
        img = bytes(await tg_file.download_as_bytearray())
        await self._reply(
            update,
            await self._brain.respond(
                user_id,
                text=update.message.caption,
                image=img,
                image_mime="image/jpeg",
            ),
        )

    # --- slash commands (no LLM) --------------------------------------------

    async def cmd_ajuda(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.help())

    async def cmd_lembrete(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.lembrete(uid, self._args(c)))

    async def cmd_lembretes(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.lembretes(uid))

    async def cmd_rotina(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.rotina(uid, self._args(c)))

    async def cmd_cancelar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.cancelar(uid, self._args(c)))

    async def cmd_tarefa(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.tarefa(uid, self._args(c)))

    async def cmd_tarefas(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.tarefas(uid, self._args(c)))

    async def cmd_buscar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.buscar(self._args(c)))

    async def cmd_clima(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.clima(self._args(c)))

    async def cmd_noticias(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.noticias(self._args(c)))

    async def cmd_calendario(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.calendario(uid))

    async def cmd_gasto(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.gasto(uid, self._args(c)))

    async def cmd_gastos(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.gastos(uid))

    async def cmd_habito(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.habito(uid, self._args(c)))

    async def cmd_feito(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.feito(uid, self._args(c)))

    async def cmd_habitos(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.habitos(uid))

    async def cmd_diario(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.diario(uid, self._args(c)))

    async def cmd_esquecer(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.esquecer(uid, self._args(c)))

    async def cmd_gastorm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.gastorm(uid, self._args(c)))

    async def cmd_habitorm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.habitorm(uid, self._args(c)))

    async def cmd_diariorm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.diariorm(uid, self._args(c)))

    async def cmd_semana(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.semana(uid))

    async def cmd_vigiar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.vigiar(uid, self._args(c)))

    async def cmd_vigias(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.vigias(uid))

    async def cmd_vigiarm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.vigiarm(uid, self._args(c)))

    async def cmd_assinatura(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.assinatura(uid, self._args(c)))

    async def cmd_assinaturas(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.assinaturas(uid))

    async def cmd_assinaturarm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.assinaturarm(uid, self._args(c)))

    async def cmd_orcamento(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.orcamento(uid, self._args(c)))

    async def cmd_orcamentos(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.orcamentos(uid))

    async def cmd_orcamentorm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.orcamentorm(uid, self._args(c)))

    async def cmd_relatorio(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        uid = str(update.effective_user.id)
        report = self._commands.relatorio(uid)
        insight = await self._brain.ask(
            "Você é a E.V. Comente em 1-2 frases este relatório financeiro "
            "(padrões, dicas gentis). Breve, em português.",
            report,
        )
        await self._cmd_out(update, report + (("\n\n🧠 " + insight) if insight else ""))

    # --- AI-powered: quiz + weekly insights --------------------------------

    @staticmethod
    def _parse_qa(text: str) -> tuple[str, str]:
        m = re.search(r"PERGUNTA:\s*(.+?)\s*RESPOSTA:\s*(.+)", text, re.S | re.I)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return text.strip(), "(confira no material)"

    async def cmd_quiz(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        uid = str(update.effective_user.id)
        chunk = self._memory.random_chunk(uid, self._args(c).strip() or None)
        if not chunk:
            await update.message.reply_text(
                "Sua base de conhecimento está vazia. Envie um PDF ou use /kbweb."
            )
            return
        await update.message.reply_text("📚 Preparando uma pergunta...")
        out = await self._brain.ask(
            "Você é um tutor. Com base no trecho, crie UMA pergunta de estudo objetiva "
            "e a resposta correta. Responda EXATAMENTE assim:\n"
            "PERGUNTA: <pergunta>\nRESPOSTA: <resposta curta>",
            f"Trecho de [{chunk['source']}]:\n{chunk['chunk']}",
        )
        if not out:
            await update.message.reply_text("Não consegui gerar agora, tenta de novo.")
            return
        q, a = self._parse_qa(out)
        text = (
            f"📚 <b>Quiz</b> — <i>{html.escape(chunk['source'])}</i>\n\n"
            f"{html.escape(q)}\n\n"
            f"Resposta: <tg-spoiler>{html.escape(a)}</tg-spoiler>"
        )
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=self._quick_kb()
        )

    def _week_data_blob(self, uid: str) -> str:
        m = self._memory
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        parts = []
        exp = m.expenses_since(uid, since)
        if exp:
            by: dict[str, float] = {}
            for e in exp:
                by[e["category"]] = by.get(e["category"], 0) + e["amount"]
            parts.append("Gastos (7d): " + ", ".join(f"{k} R${v:.0f}" for k, v in by.items()))
        parts.append(f"Tarefas concluídas (7d): {m.tasks_completed_since(uid, since)}")
        habits = m.list_habits(uid)
        if habits:
            today = datetime.now(self._tz()).date()
            parts.append(
                "Hábitos: "
                + ", ".join(f"{h['name']} ({self._commands._streak(h['id'], today)}d)" for h in habits)
            )
        journ = m.recent_journal(uid, 7)
        if journ:
            parts.append("Diário: " + " | ".join(e["text"][:120] for e in journ))
        return "Dados da semana do usuário:\n" + "\n".join(parts)

    async def cmd_insights(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        uid = str(update.effective_user.id)
        await update.message.reply_text("🧠 Analisando sua semana...")
        out = await self._brain.ask(
            "Você é a E.V., assistente pessoal carinhosa. Com base nos dados da semana "
            "do usuário, dê de 2 a 4 insights curtos, úteis e humanos (padrões, elogios, "
            "alertas gentis). Concreta e breve, em português. Sem repetir os números crus.",
            self._week_data_blob(uid),
        )
        await self._cmd_out(
            update, out or "Ainda sem dados suficientes. Usa a E.V. mais uns dias!"
        )

    # --- model status / selection ------------------------------------------

    _PROVIDER_LABELS = {
        "gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter",
        "ollama": "Ollama (local)", "?": "desconhecido",
    }
    # Approximate free daily caps (the real free tier varies — shown as estimates).
    _APPROX_CAPS = {"gemini": 20, "groq": 1000, "openrouter": 1000}

    async def cmd_modelo(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        arg = self._args(c).strip()
        if arg:
            self._memory.set_setting("model", arg)
            await update.message.reply_text(
                f"Modelo principal (Gemini) alterado para: {arg}\n"
                "Vale já. Se for inválido, a E.V. cai nos fallbacks automaticamente."
            )
            return
        cfg = self._config
        usage = self._memory.usage_for_day(datetime.now(timezone.utc).date().isoformat())
        lines = ["🧠 <b>Modelos da E.V.</b>", ""]
        lines.append(f"• Principal: <b>{html.escape(self._brain.current_model())}</b> · Gemini")
        if cfg.groq_api_key:
            lines.append(f"• Fallback 1: {html.escape(cfg.groq_model)} · Groq")
        if cfg.openrouter_api_key:
            lines.append(f"• Fallback 2: {html.escape(cfg.openrouter_model)} · OpenRouter")
        if cfg.ollama_enabled:
            lines.append(f"• Rede local: {html.escape(cfg.ollama_model)} · Ollama")
        last = self._brain._last_provider
        if last:
            lines.append(f"\nÚltima resposta veio de: <b>{self._PROVIDER_LABELS.get(last, last)}</b>")
        lines.append("\n📊 <b>Uso hoje</b> (zera à meia-noite UTC):")
        for prov in ("gemini", "groq", "openrouter", "ollama"):
            used = usage.get(prov, 0)
            cap = self._APPROX_CAPS.get(prov)
            if cap:
                lines.append(
                    f"• {self._PROVIDER_LABELS[prov]}: {used} usados · ~{max(0, cap - used)} restantes (de ~{cap})"
                )
            elif prov == "ollama" and cfg.ollama_enabled:
                lines.append(f"• {self._PROVIDER_LABELS[prov]}: {used} usados · ilimitado")
        lines.append("\n<i>Limites são estimados (o free tier varia). Trocar principal: /modelo &lt;nome&gt;</i>")
        await update.message.reply_text(
            "\n".join(lines), parse_mode="HTML", reply_markup=self._quick_kb()
        )

    async def cmd_concluir(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.concluir(uid, self._args(c)))

    async def cmd_lembrar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.lembrar(uid, self._args(c)))

    async def cmd_memorias(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.memorias(uid))

    async def cmd_link(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.link(uid, self._args(c)))

    async def cmd_links(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.links(uid, self._args(c)))

    async def cmd_linkrm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.linkrm(uid, self._args(c)))

    async def cmd_kb(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.kb(uid))

    async def cmd_kbrm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.kbrm(uid, self._args(c)))

    async def cmd_kbweb(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.kbweb(uid, self._args(c)))

    async def on_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        uid = str(update.effective_user.id)
        doc = update.message.document
        await update.message.reply_text("Recebi o documento, estou indexando...")
        tg_file = await ctx.bot.get_file(doc.file_id)
        data = bytes(await tg_file.download_as_bytearray())
        result = await asyncio.to_thread(
            self._commands.ingest_document, uid, data, doc.file_name or "documento.pdf"
        )
        await self._cmd_out(update, result)

    async def cmd_agenda(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.agenda(self._args(c)))

    async def cmd_evento(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.evento(self._args(c)))

    async def cmd_email(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.email(self._args(c)))

    # --- interactive menu (buttons) ----------------------------------------

    # Sections with a simple "list / add" shape.
    _SECTIONS = {
        "task": {"title": "📋 Tarefas", "prompt": "Escreva a tarefa (use #categoria pra classificar).\nEx: estudar cálculo #faculdade"},
        "rem": {"title": "⏰ Lembretes", "prompt": "Formato: <tempo> <texto>\nEx: 10m tomar água"},
        "link": {"title": "🔗 Links", "prompt": "Formato: categoria | nome | url\nEx: faculdade | tarefas | https://..."},
        "mem": {"title": "🧠 Memória", "prompt": "O que você quer que eu guarde?"},
    }

    def _kb_main(self) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup(
            [
                [b("📋 Tarefas", callback_data="task:menu"), b("⏰ Lembretes", callback_data="rem:menu")],
                [b("🔗 Links", callback_data="link:menu"), b("📄 Conhecimento", callback_data="kb:menu")],
                [b("🧠 Memória", callback_data="mem:menu"), b("📅 Google", callback_data="goog:menu")],
                [b("🔎 Buscar web", callback_data="search:add")],
                [b("❓ Ajuda", callback_data="misc:ajuda")],
            ]
        )

    def _kb_section(self, section: str) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup(
            [
                [b("📄 Ver", callback_data=f"{section}:list"), b("➕ Adicionar", callback_data=f"{section}:add")],
                [b("⬅️ Voltar", callback_data="nav:main")],
            ]
        )

    def _kb_kb(self) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup(
            [
                [b("📄 Ver documentos", callback_data="kb:list")],
                [b("➕ Adicionar (enviar PDF)", callback_data="kb:add")],
                [b("🌐 Indexar página web", callback_data="kb:web")],
                [b("⬅️ Voltar", callback_data="nav:main")],
            ]
        )

    def _kb_goog(self) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup(
            [
                [b("📅 Ver agenda", callback_data="goog:agenda")],
                [b("🗓️ Novo evento", callback_data="goog:evento"), b("✉️ Enviar e-mail", callback_data="goog:email")],
                [b("⬅️ Voltar", callback_data="nav:main")],
            ]
        )

    def _kb_back(self, section: str) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup(
            [[b("⬅️ Voltar", callback_data=f"{section}:menu"), b("🏠 Menu", callback_data="nav:main")]]
        )

    _MAIN_TEXT = (
        "🕷️ <b>E.V.</b>\n"
        "<i>sua assistente pessoal</i>\n"
        "━━━━━━━━━━━━━━━\n"
        "O que vamos fazer? Toque em uma opção abaixo — ou é só me mandar "
        "uma <b>mensagem</b> ou <b>áudio</b> que a gente conversa. 💬"
    )

    async def cmd_menu(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await update.message.reply_text(
                self._MAIN_TEXT, reply_markup=self._kb_main(), parse_mode="HTML"
            )

    async def on_callback(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if self._config.owner_id is not None and (
            not q.from_user or q.from_user.id != self._config.owner_id
        ):
            return
        uid = str(q.from_user.id)
        section, _, action = q.data.partition(":")

        if section == "nav" or (section == "misc" and action == "menu"):
            self._pending.pop(uid, None)
            await q.edit_message_text(
                self._MAIN_TEXT, reply_markup=self._kb_main(), parse_mode="HTML"
            )
            return
        if section == "misc" and action == "ajuda":
            await q.edit_message_text(
                self._commands.help(),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🏠 Menu", callback_data="nav:main")]]
                ),
            )
            return

        if action == "menu":
            titles = {
                "task": "📋 <b>Tarefas</b>\n<i>criar, ver e concluir</i>",
                "rem": "⏰ <b>Lembretes</b>\n<i>pontuais e recorrentes</i>",
                "link": "🔗 <b>Links</b>\n<i>salvos por categoria</i>",
                "mem": "🧠 <b>Memória</b>\n<i>o que eu sei sobre você</i>",
                "kb": "📄 <b>Base de conhecimento</b>\n<i>seus PDFs e páginas</i>",
                "goog": "📅 <b>Google</b>\n<i>agenda e e-mail</i>",
            }
            kb = {
                "kb": self._kb_kb(), "goog": self._kb_goog(),
            }.get(section) or self._kb_section(section)
            await q.edit_message_text(
                titles.get(section, "Menu"), reply_markup=kb, parse_mode="HTML"
            )
            return

        # Actions that produce text (lists / reads)
        text = self._run_menu_action(uid, section, action)
        if text is not None:
            back_section = section if section in ("task", "rem", "link", "mem", "kb", "goog") else "nav"
            markup = self._kb_back(back_section) if back_section != "nav" else self._kb_main()
            await q.edit_message_text(text, reply_markup=markup)
            return

        # Actions that need input -> prompt (and, except KB upload, wait for text)
        prompt = self._menu_prompt(section, action)
        if prompt is not None:
            # KB "add" is a PDF upload (no text). Everything else waits for text.
            if not (section == "kb" and action == "add"):
                self._pending[uid] = f"{section}:{action}"
            await q.edit_message_text(
                prompt,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("✖️ Cancelar", callback_data="nav:main")]]
                ),
            )

    def _run_menu_action(self, uid: str, section: str, action: str) -> str | None:
        if action != "list" and not (section == "goog" and action == "agenda"):
            return None
        if section == "task":
            return self._commands.tarefas(uid)
        if section == "rem":
            return self._commands.lembretes(uid)
        if section == "link":
            return self._commands.links(uid, "")
        if section == "mem":
            return self._commands.memorias(uid)
        if section == "kb":
            return self._commands.kb(uid)
        if section == "goog" and action == "agenda":
            return self._commands.agenda()
        return None

    def _menu_prompt(self, section: str, action: str) -> str | None:
        if action == "add" and section in self._SECTIONS:
            return "➕ " + self._SECTIONS[section]["prompt"]
        if section == "kb" and action == "add":
            return "📄 Envie um arquivo PDF aqui no chat que eu indexo na base."
        if section == "kb" and action == "web":
            return "🌐 Manda a URL da página que eu indexo. Ex: https://..."
        if section == "goog" and action == "evento":
            return "🗓️ Formato: <tempo> <título>\nEx: amanhã 15:00 Dentista"
        if section == "goog" and action == "email":
            return "✉️ Formato: destinatário | assunto | corpo"
        if section == "search" and action == "add":
            return "🔎 O que você quer pesquisar na web?"
        return None

    def _handle_pending(self, uid: str, pending: str, text: str) -> str:
        section, _, action = pending.partition(":")
        if section == "task":
            return self._commands.tarefa(uid, text)
        if section == "rem":
            return self._commands.lembrete(uid, text)
        if section == "link":
            return self._commands.link(uid, text)
        if section == "mem":
            return self._commands.lembrar(uid, text)
        if section == "goog" and action == "evento":
            return self._commands.evento(text)
        if section == "goog" and action == "email":
            return self._commands.email(text)
        if section == "kb" and action == "web":
            return self._commands.kbweb(uid, text)
        if section == "search" and action == "add":
            return self._commands.buscar(text)
        return "Ok."

    # --- reply --------------------------------------------------------------

    @staticmethod
    def _split(text: str, limit: int = 4000) -> list[str]:
        """Split text into <= limit-char parts (Telegram caps messages at 4096)."""
        text = text or "…"
        parts, current = [], ""
        for line in text.split("\n"):
            while len(line) > limit:  # a single very long line
                parts.append(line[:limit])
                line = line[limit:]
            if len(current) + len(line) + 1 > limit:
                parts.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            parts.append(current)
        return parts

    def _quick_kb(self) -> InlineKeyboardMarkup:
        """Compact action bar attached to (almost) every message, so the user can
        always act/navigate with a tap."""
        b = InlineKeyboardButton
        return InlineKeyboardMarkup(
            [
                [
                    b("🏠 Menu", callback_data="nav:main"),
                    b("➕ Tarefa", callback_data="task:add"),
                    b("⏰ Lembrete", callback_data="rem:add"),
                ],
            ]
        )

    async def _send(self, message, text: str, kb: InlineKeyboardMarkup | None) -> None:
        """Send text (chunked if long); the keyboard rides on the last chunk."""
        parts = self._split(text)
        for i, part in enumerate(parts):
            await message.reply_text(
                part, reply_markup=kb if i == len(parts) - 1 else None
            )

    async def _bot_send(self, bot, chat_id: int, text: str, kb) -> None:
        """Bot-initiated send (reminders, briefing): chunked, with action bar."""
        parts = self._split(text)
        for i, part in enumerate(parts):
            await bot.send_message(
                chat_id=chat_id,
                text=part,
                reply_markup=kb if i == len(parts) - 1 else None,
            )

    async def _cmd_out(self, update: Update, text: str) -> None:
        """Send a command result with the quick-action bar."""
        await self._send(update.message, text, self._quick_kb())

    async def _reply(self, update: Update, answer: str) -> None:
        await self._send(update.message, answer, self._quick_kb())
        if not self._config.voice_reply:
            return
        try:
            mp3 = await voice_mod.synthesize(
                answer,
                self._config.voice,
                rate=self._config.voice_rate,
                pitch=self._config.voice_pitch,
                fixes=self._config.voice_fixes,
            )
            buf = io.BytesIO(mp3)
            buf.name = "ev.mp3"
            await update.message.reply_audio(audio=buf, title="E.V.")
        except Exception:  # voice is a bonus — never let it break the reply
            log.exception("Voice synthesis failed (replied with text only)")

    # --- reminder scheduler -------------------------------------------------

    async def _post_init(self, app: Application) -> None:
        # Register the command menu shown when the user types "/".
        await app.bot.set_my_commands(
            [BotCommand(name, desc) for name, desc in COMMAND_LIST]
        )
        self._bg_tasks = [
            asyncio.create_task(self._reminder_loop(app)),
            asyncio.create_task(self._briefing_loop(app)),
            asyncio.create_task(self._backup_loop(app)),
            asyncio.create_task(self._watch_loop(app)),
        ]
        log.info(
            "Schedulers started (reminders every %ss; daily briefing at %sh; daily backup).",
            self._config.reminder_poll_seconds,
            self._config.briefing_hour,
        )

    async def _backup_loop(self, app: Application) -> None:
        while True:
            try:
                path = await asyncio.to_thread(self._do_backup)
                await self._maybe_send_backup_telegram(app, path)
            except Exception:
                log.exception("Backup failed")
            await asyncio.sleep(24 * 3600)

    def _do_backup(self, keep: int = 7):
        # Prune old chat history first (bounds the DB size over time).
        try:
            self._memory.prune_messages(self._config.message_history_keep)
        except Exception:
            log.exception("Prune failed")
        bdir = self._config.db_path.parent / "backups"
        bdir.mkdir(exist_ok=True)
        dest = bdir / f"ev_memory.{datetime.now().strftime('%Y%m%d')}.db"
        self._memory.backup(dest)
        for f in sorted(bdir.glob("ev_memory.*.db"))[:-keep]:
            f.unlink()
        log.info("DB backup saved to %s", dest.name)
        return dest

    async def _maybe_send_backup_telegram(self, app: Application, path) -> None:
        """Send the backup off the VM, into the owner's Telegram chat. Weekly
        (Sundays), plus once right after startup so there's always a fresh copy."""
        cfg = self._config
        if not cfg.telegram_backup or cfg.owner_id is None or path is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        first_time = self._last_tg_backup is None
        if not first_time and (now.weekday() != 6 or self._last_tg_backup == today):
            return
        self._last_tg_backup = today
        try:
            with open(path, "rb") as f:
                await app.bot.send_document(
                    chat_id=cfg.owner_id,
                    document=f,
                    filename=path.name,
                    caption="🗄️ Backup do banco da E.V. Guarde este arquivo — dá pra restaurar tudo com ele.",
                )
            log.info("Backup sent to Telegram (%s).", path.name)
        except Exception:
            log.exception("Failed to send backup to Telegram")

    async def _briefing_loop(self, app: Application) -> None:
        while True:
            try:
                await self._maybe_send_briefing(app)
                await self._maybe_send_checkin(app)
                await self._maybe_send_weekly(app)
                await self._maybe_send_rain(app)
                await self._maybe_run_recurring(app)
                await self._maybe_habit_nudge(app)
                await self._maybe_monthly_report(app)
            except Exception:
                log.exception("Briefing loop error")
            await asyncio.sleep(60)

    async def _maybe_send_weekly(self, app: Application) -> None:
        cfg = self._config
        if cfg.weekly_day < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if (
            now.weekday() == cfg.weekly_day
            and now.hour == cfg.weekly_hour
            and self._last_weekly != today
        ):
            self._last_weekly = today
            text = self._commands.semana(str(cfg.owner_id))
            insights = await self._brain.ask(
                "Você é a E.V. Dê 2-3 insights curtos e humanos sobre a semana do "
                "usuário (padrões, elogios, alertas gentis). Breve, em português.",
                self._week_data_blob(str(cfg.owner_id)),
            )
            if insights:
                text += "\n\n🧠 Insights:\n" + insights
            await self._bot_send(app.bot, cfg.owner_id, text, self._quick_kb())
            log.info("Sent weekly review.")

    async def _maybe_send_rain(self, app: Application) -> None:
        cfg = self._config
        if cfg.rain_hour < 0 or cfg.owner_id is None or not cfg.city:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour == cfg.rain_hour and self._last_rain != today:
            self._last_rain = today
            from ..providers import tools
            msg = await asyncio.to_thread(tools.rain_tomorrow, cfg.city)
            if msg:
                await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
                log.info("Sent rain alert.")

    async def _maybe_run_recurring(self, app: Application) -> None:
        cfg = self._config
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if self._last_recurring == today:
            return
        self._last_recurring = today
        month = now.strftime("%Y-%m")
        for r in self._memory.due_recurring(now.day, month):
            self._memory.add_expense(
                r["user_id"], r["amount"], r["description"], r["category"]
            )
            self._memory.mark_recurring_logged(r["id"], month)
            if str(r["user_id"]).isdigit():
                await self._bot_send(
                    app.bot, int(r["user_id"]),
                    f"🔁 Lancei sua assinatura: R$ {r['amount']:.2f} em {r['description']}.",
                    self._quick_kb(),
                )
            log.info("Logged recurring expense #%s", r["id"])

    async def _maybe_habit_nudge(self, app: Application) -> None:
        cfg = self._config
        if cfg.habit_nudge_hour < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour != cfg.habit_nudge_hour or self._last_habit_nudge == today:
            return
        self._last_habit_nudge = today
        uid = str(cfg.owner_id)
        today_s = now.date().strftime("%Y-%m-%d")
        pend = [
            h["name"] for h in self._memory.list_habits(uid)
            if today_s not in self._memory.habit_days(h["id"])
        ]
        if pend:
            msg = "👀 Ainda falta hoje: " + ", ".join(pend) + ".\nMarque com /feito <nome>."
            await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
            log.info("Sent habit nudge.")

    async def _maybe_monthly_report(self, app: Application) -> None:
        cfg = self._config
        if cfg.monthly_report_day < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        month = now.strftime("%Y-%m")
        if (
            now.day != cfg.monthly_report_day
            or now.hour != cfg.monthly_report_hour
            or self._last_monthly == month
        ):
            return
        self._last_monthly = month
        uid = str(cfg.owner_id)
        report = self._commands.relatorio(uid)
        insight = await self._brain.ask(
            "Você é a E.V. Comente em 1-2 frases este relatório do mês (padrões, "
            "dicas gentis). Breve e humano, em português.",
            report,
        )
        text = report + (("\n\n🧠 " + insight) if insight else "")
        await self._bot_send(app.bot, cfg.owner_id, text, self._quick_kb())
        log.info("Sent monthly report.")

    async def _watch_loop(self, app: Application) -> None:
        import hashlib
        from ..providers import tools

        while True:
            try:
                for w in self._memory.all_watches():
                    if not str(w["user_id"]).isdigit():
                        continue
                    try:
                        text = await asyncio.to_thread(tools.fetch_text, w["url"])
                    except Exception:
                        continue
                    if w["keyword"]:
                        present = w["keyword"].lower() in text.lower()
                        if present and w["state"] != "found":
                            await self._bot_send(
                                app.bot, int(w["user_id"]),
                                f"👁️ '{w['keyword']}' apareceu em {w['url']}",
                                self._quick_kb(),
                            )
                        self._memory.set_watch_state(w["id"], "found" if present else "absent")
                    else:
                        # Normalize away numeric noise (timestamps, view counts,
                        # ad rotations) so only real content changes trigger.
                        norm = re.sub(r"\d+", "", text)
                        norm = re.sub(r"\s+", " ", norm).lower()
                        digest = hashlib.sha256(norm.encode("utf-8", "ignore")).hexdigest()
                        if w["state"] and w["state"] != digest:
                            await self._bot_send(
                                app.bot, int(w["user_id"]),
                                f"👁️ A página mudou: {w['url']}",
                                self._quick_kb(),
                            )
                        self._memory.set_watch_state(w["id"], digest)
            except Exception:
                log.exception("Watch loop error")
            await asyncio.sleep(max(60, self._config.watch_poll_minutes * 60))

    async def _maybe_send_checkin(self, app: Application) -> None:
        cfg = self._config
        if cfg.checkin_hour < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour == cfg.checkin_hour and self._last_checkin != today:
            self._last_checkin = today
            msg = (
                "Oi! Como foi seu dia? Se quiser, registra no diário com "
                "/diario <texto>. E não esquece dos seus hábitos — /habitos."
            )
            await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
            log.info("Sent daily check-in.")

    async def _maybe_send_briefing(self, app: Application) -> None:
        cfg = self._config
        if cfg.briefing_hour < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour == cfg.briefing_hour and self._last_briefing != today:
            self._last_briefing = today
            text = self._commands.daily_briefing(str(cfg.owner_id))
            await self._bot_send(app.bot, cfg.owner_id, text, self._kb_main())
            log.info("Sent daily briefing to owner.")

    async def _reminder_loop(self, app: Application) -> None:
        while True:
            try:
                await self._deliver_due_reminders(app)
            except Exception:
                log.exception("Reminder loop error")
            await asyncio.sleep(self._config.reminder_poll_seconds)

    def _tz(self):
        try:
            return ZoneInfo(self._config.timezone) if ZoneInfo else None
        except Exception:
            return None

    async def _deliver_due_reminders(self, app: Application) -> None:
        tz = self._tz()
        now = datetime.now(tz)
        for r in self._memory.pending_reminders():
            # Telegram chat_id is numeric; skip anything else (e.g. test data).
            if not str(r["user_id"]).isdigit():
                self._memory.mark_reminder_done(r["id"])
                continue
            try:
                due = datetime.fromisoformat(r["when_iso"])
                if due.tzinfo is None and tz is not None:
                    due = due.replace(tzinfo=tz)
            except Exception:
                continue  # unparseable time — skip (leave it pending)
            if due <= now:
                try:
                    await self._bot_send(
                        app.bot, int(r["user_id"]),
                        f"Lembrete: {r['text']}", self._quick_kb(),
                    )
                    self._advance_reminder(r, due, now)
                    log.info("Delivered reminder #%s", r["id"])
                except Exception:
                    log.exception("Failed to deliver reminder #%s", r["id"])

    def _advance_reminder(self, r: dict, due: datetime, now: datetime) -> None:
        """Recurring -> schedule the next future occurrence; one-off -> mark done."""
        delta = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(
            r.get("recur") or ""
        )
        if not delta:
            self._memory.mark_reminder_done(r["id"])
            return
        nxt = due
        while nxt <= now:  # catch up past missed occurrences to the future
            nxt += delta
        self._memory.reschedule_reminder(r["id"], nxt.isoformat())

    # --- error handling -----------------------------------------------------

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.exception("Unhandled handler error", exc_info=context.error)
        if self._config.owner_id is not None:
            try:
                await context.bot.send_message(
                    chat_id=self._config.owner_id,
                    text="Ops, tive um erro interno processando isso. Já registrei nos logs.",
                )
            except Exception:
                pass

    # --- runner -------------------------------------------------------------

    def run(self) -> None:
        app = (
            Application.builder()
            .token(self._config.telegram_token)
            .post_init(self._post_init)
            .build()
        )
        # Chat (LLM)
        app.add_handler(CommandHandler("start", self.on_start))
        app.add_handler(CommandHandler("menu", self.cmd_menu))
        app.add_handler(CallbackQueryHandler(self.on_callback))
        # Deterministic commands (no LLM)
        app.add_handler(CommandHandler("ajuda", self.cmd_ajuda))
        app.add_handler(CommandHandler("help", self.cmd_ajuda))
        app.add_handler(CommandHandler("lembrete", self.cmd_lembrete))
        app.add_handler(CommandHandler("rotina", self.cmd_rotina))
        app.add_handler(CommandHandler("cancelar", self.cmd_cancelar))
        app.add_handler(CommandHandler("lembretes", self.cmd_lembretes))
        app.add_handler(CommandHandler("tarefa", self.cmd_tarefa))
        app.add_handler(CommandHandler("tarefas", self.cmd_tarefas))
        app.add_handler(CommandHandler("concluir", self.cmd_concluir))
        app.add_handler(CommandHandler("buscar", self.cmd_buscar))
        app.add_handler(CommandHandler("clima", self.cmd_clima))
        app.add_handler(CommandHandler("noticias", self.cmd_noticias))
        app.add_handler(CommandHandler("calendario", self.cmd_calendario))
        app.add_handler(CommandHandler("gasto", self.cmd_gasto))
        app.add_handler(CommandHandler("gastos", self.cmd_gastos))
        app.add_handler(CommandHandler("habito", self.cmd_habito))
        app.add_handler(CommandHandler("feito", self.cmd_feito))
        app.add_handler(CommandHandler("habitos", self.cmd_habitos))
        app.add_handler(CommandHandler("diario", self.cmd_diario))
        app.add_handler(CommandHandler("esquecer", self.cmd_esquecer))
        app.add_handler(CommandHandler("gastorm", self.cmd_gastorm))
        app.add_handler(CommandHandler("habitorm", self.cmd_habitorm))
        app.add_handler(CommandHandler("diariorm", self.cmd_diariorm))
        app.add_handler(CommandHandler("semana", self.cmd_semana))
        app.add_handler(CommandHandler("vigiar", self.cmd_vigiar))
        app.add_handler(CommandHandler("vigias", self.cmd_vigias))
        app.add_handler(CommandHandler("vigiarm", self.cmd_vigiarm))
        app.add_handler(CommandHandler("assinatura", self.cmd_assinatura))
        app.add_handler(CommandHandler("assinaturas", self.cmd_assinaturas))
        app.add_handler(CommandHandler("assinaturarm", self.cmd_assinaturarm))
        app.add_handler(CommandHandler("orcamento", self.cmd_orcamento))
        app.add_handler(CommandHandler("orcamentos", self.cmd_orcamentos))
        app.add_handler(CommandHandler("orcamentorm", self.cmd_orcamentorm))
        app.add_handler(CommandHandler("relatorio", self.cmd_relatorio))
        app.add_handler(CommandHandler("quiz", self.cmd_quiz))
        app.add_handler(CommandHandler("insights", self.cmd_insights))
        app.add_handler(CommandHandler("modelo", self.cmd_modelo))
        app.add_handler(CommandHandler("lembrar", self.cmd_lembrar))
        app.add_handler(CommandHandler("memorias", self.cmd_memorias))
        app.add_handler(CommandHandler("link", self.cmd_link))
        app.add_handler(CommandHandler("links", self.cmd_links))
        app.add_handler(CommandHandler("linkrm", self.cmd_linkrm))
        app.add_handler(CommandHandler("kb", self.cmd_kb))
        app.add_handler(CommandHandler("kbweb", self.cmd_kbweb))
        app.add_handler(CommandHandler("kbrm", self.cmd_kbrm))
        app.add_handler(CommandHandler("agenda", self.cmd_agenda))
        app.add_handler(CommandHandler("evento", self.cmd_evento))
        app.add_handler(CommandHandler("email", self.cmd_email))
        # Document upload (PDF) -> knowledge base
        app.add_handler(MessageHandler(filters.Document.ALL, self.on_document))
        # Photo -> multimodal (Gemini vision)
        app.add_handler(MessageHandler(filters.PHOTO, self.on_photo))
        # Voice + free text (must be last)
        app.add_handler(MessageHandler(filters.VOICE, self.on_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        app.add_error_handler(self._on_error)
        log.info("E.V. starting (polling)...")
        app.run_polling()


def run() -> None:
    TelegramInterface(Config.load()).run()
