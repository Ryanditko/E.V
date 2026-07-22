"""E.V.'s Telegram interface.

Two ways to interact:
  - Natural chat (text or voice) -> goes through the brain (LLM).
  - Slash commands (/lembrete, /tarefa, /email, ...) -> deterministic, no LLM.

It locks access to the owner (EV_OWNER_ID) when configured, and runs the reminder
scheduler as a background task that delivers due reminders to the user's chat.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
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
        await update.message.reply_text(
            f"E.V. online. Manda texto ou áudio pra conversar, ou use /ajuda "
            f"pra ver os comandos rápidos. (seu ID: {uid})"
        )

    async def on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)
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

    # --- slash commands (no LLM) --------------------------------------------

    async def cmd_ajuda(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await update.message.reply_text(self._commands.help())

    async def cmd_lembrete(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.lembrete(uid, self._args(c)))

    async def cmd_lembretes(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.lembretes(uid))

    async def cmd_tarefa(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.tarefa(uid, self._args(c)))

    async def cmd_tarefas(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.tarefas(uid))

    async def cmd_concluir(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.concluir(uid, self._args(c)))

    async def cmd_lembrar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.lembrar(uid, self._args(c)))

    async def cmd_memorias(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.memorias(uid))

    async def cmd_link(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.link(uid, self._args(c)))

    async def cmd_links(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.links(uid, self._args(c)))

    async def cmd_linkrm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.linkrm(uid, self._args(c)))

    async def cmd_kb(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.kb(uid))

    async def cmd_kbrm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await update.message.reply_text(self._commands.kbrm(uid, self._args(c)))

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
        await update.message.reply_text(result)

    async def cmd_agenda(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await update.message.reply_text(self._commands.agenda())

    async def cmd_evento(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await update.message.reply_text(self._commands.evento(self._args(c)))

    async def cmd_email(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await update.message.reply_text(self._commands.email(self._args(c)))

    # --- reply --------------------------------------------------------------

    async def _reply(self, update: Update, answer: str) -> None:
        await update.message.reply_text(answer)
        if not self._config.voice_reply:
            return
        try:
            mp3 = await voice_mod.synthesize(
                answer,
                self._config.voice,
                rate=self._config.voice_rate,
                pitch=self._config.voice_pitch,
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
        asyncio.create_task(self._reminder_loop(app))
        log.info(
            "Reminder scheduler started (every %ss).",
            self._config.reminder_poll_seconds,
        )

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
                    await app.bot.send_message(
                        chat_id=int(r["user_id"]), text=f"Lembrete: {r['text']}"
                    )
                    self._memory.mark_reminder_done(r["id"])
                    log.info("Delivered reminder #%s", r["id"])
                except Exception:
                    log.exception("Failed to deliver reminder #%s", r["id"])

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
        # Deterministic commands (no LLM)
        app.add_handler(CommandHandler("ajuda", self.cmd_ajuda))
        app.add_handler(CommandHandler("help", self.cmd_ajuda))
        app.add_handler(CommandHandler("lembrete", self.cmd_lembrete))
        app.add_handler(CommandHandler("lembretes", self.cmd_lembretes))
        app.add_handler(CommandHandler("tarefa", self.cmd_tarefa))
        app.add_handler(CommandHandler("tarefas", self.cmd_tarefas))
        app.add_handler(CommandHandler("concluir", self.cmd_concluir))
        app.add_handler(CommandHandler("lembrar", self.cmd_lembrar))
        app.add_handler(CommandHandler("memorias", self.cmd_memorias))
        app.add_handler(CommandHandler("link", self.cmd_link))
        app.add_handler(CommandHandler("links", self.cmd_links))
        app.add_handler(CommandHandler("linkrm", self.cmd_linkrm))
        app.add_handler(CommandHandler("kb", self.cmd_kb))
        app.add_handler(CommandHandler("kbrm", self.cmd_kbrm))
        app.add_handler(CommandHandler("agenda", self.cmd_agenda))
        app.add_handler(CommandHandler("evento", self.cmd_evento))
        app.add_handler(CommandHandler("email", self.cmd_email))
        # Document upload (PDF) -> knowledge base
        app.add_handler(MessageHandler(filters.Document.ALL, self.on_document))
        # Voice + free text (must be last)
        app.add_handler(MessageHandler(filters.VOICE, self.on_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        log.info("E.V. starting (polling)...")
        app.run_polling()


def run() -> None:
    TelegramInterface(Config.load()).run()
