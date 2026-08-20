"""E.V.'s Telegram interface — core: construction, startup, handler wiring.

Two ways to interact:
  - Natural chat (text or voice) -> goes through the brain (LLM).
  - Slash commands (/lembrete, /tarefa, /email, ...) -> deterministic, no LLM.

It locks access to the owner (EV_OWNER_ID) when configured, and runs the reminder
scheduler as a background task that delivers due reminders to the user's chat.

This module keeps `__init__`, `_post_init` (where `_bg_tasks` is populated),
`_on_error` and `run()` (handler registration) centralized — `run()` is the one
place that "sees" the fully composed class via `self`, and the MessageHandler
registration order (Document -> Photo -> Audio -> Voice -> Text) is sensitive
and must not change.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import BotCommand
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ...config import Config
from ...core.brain import Brain
from ...core.commands import Commands, command_list
from ...core.memory import Memory
from .background_loops import BackgroundLoopsMixin
from .callbacks import CallbacksMixin
from .commands_wrappers import CommandsWrappersMixin
from .keyboards import KeyboardsMixin
from .media import MediaMixin
from .pomodoro import PomodoroMixin
from .routing import RoutingMixin
from .voice import VoiceMixin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("ev.telegram")


class TelegramInterface(
    RoutingMixin,
    VoiceMixin,
    MediaMixin,
    PomodoroMixin,
    KeyboardsMixin,
    CallbacksMixin,
    CommandsWrappersMixin,
    BackgroundLoopsMixin,
):
    def __init__(self, config: Config) -> None:
        self._config = config
        self._memory = Memory(config.db_path)
        self._brain = Brain(config, self._memory)
        self._commands = Commands(config, self._memory)
        # user_id -> pending input action (e.g. "task", "rem", "link", ...)
        self._pending: dict[str, str] = {}
        # short id -> (title, content) for the "save to knowledge base" button
        self._pending_docs: dict[str, tuple[str, str]] = {}
        # short id -> (filename, extracted_text) for received-file actions
        self._pending_files: dict[str, tuple[str, str]] = {}
        # short id -> (image_bytes, mime) for photo OCR
        self._pending_images: dict[str, tuple[bytes, str]] = {}
        # short id -> parsed expense dict, for the receipt "confirmar gasto" button
        self._pending_expense: dict[str, dict] = {}
        # calendar event ids already alerted (pre-event heads-up), to avoid repeats
        self._alerted_events: set[str] = set()
        # short id -> reminder text, for the snooze/done buttons on a fired reminder
        self._pending_rem: dict[str, str] = {}
        self._doc_seq = 0
        self._started_at = datetime.now(timezone.utc)  # for /status uptime
        self._pomodoro_task = None  # the current live focus timer task (if any)
        self._pomo = None           # shared mutable state of the running timer
        self._bot_username = ""     # cached in _post_init (for @mention detection)
        self._last_briefing: str | None = None  # date of the last daily briefing
        self._last_checkin: str | None = None    # date of the last proactive check-in
        self._last_weekly: str | None = None     # date of the last weekly review
        self._last_rain: str | None = None       # date of the last rain check
        self._last_recurring: str | None = None  # date recurring expenses were run
        self._last_tg_backup: str | None = None  # date backup was sent to Telegram
        self._last_habit_nudge: str | None = None  # date of the last habit nudge
        self._last_monthly: str | None = None      # month of the last financial report
        self._last_nudge: str | None = None        # date of the last open-loops nudge
        self._last_insight: str | None = None       # date of the last learned-pattern share
        self._last_subdue: str | None = None        # date of the last subscription-due heads-up
        self._alerted_budgets: set[str] = set()      # month:category:level already alerted
        # Keep references to background tasks so they aren't garbage-collected
        # (a GC'd task would silently kill the scheduler).
        self._bg_tasks: list = []

    async def _post_init(self, app: Application) -> None:
        # Cache the bot's @username so we can detect mentions in groups.
        try:
            me = await app.bot.get_me()
            self._bot_username = (me.username or "").lower()
        except Exception:
            log.exception("Could not fetch bot username")
        # Register the command menu shown when the user types "/".
        await app.bot.set_my_commands(
            [BotCommand(name, desc)
             for name, desc in command_list(self._memory.assistant_lang())]
        )
        self._bg_tasks = [
            asyncio.create_task(self._reminder_loop(app)),
            asyncio.create_task(self._briefing_loop(app)),
            asyncio.create_task(self._backup_loop(app)),
            asyncio.create_task(self._watch_loop(app)),
            asyncio.create_task(self._loctask_loop(app)),
            asyncio.create_task(self._locconfirm_loop(app)),
        ]
        log.info(
            "Schedulers started (reminders every %ss; daily briefing at %sh; daily backup).",
            self._config.reminder_poll_seconds,
            self._config.briefing_hour,
        )

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
        app.add_handler(CommandHandler("ev", self.cmd_ev))
        app.add_handler(CommandHandler("plano", self.cmd_plano))
        app.add_handler(CommandHandler("pendencias", self.cmd_pendencias))
        app.add_handler(CommandHandler("backup", self.cmd_backup))
        app.add_handler(CommandHandler("padroes", self.cmd_padroes))
        app.add_handler(CommandHandler("automacoes", self.cmd_automacoes))
        app.add_handler(CommandHandler("automacaorm", self.cmd_automacaorm))
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
        app.add_handler(CommandHandler("procurar", self.cmd_procurar))
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
        app.add_handler(CommandHandler("provedor", self.cmd_provedor))
        app.add_handler(CommandHandler(["idioma", "language"], self.cmd_idioma))
        app.add_handler(CommandHandler("lembrar", self.cmd_lembrar))
        app.add_handler(CommandHandler("memorias", self.cmd_memorias))
        app.add_handler(CommandHandler("link", self.cmd_link))
        app.add_handler(CommandHandler("links", self.cmd_links))
        app.add_handler(CommandHandler("linkrm", self.cmd_linkrm))
        app.add_handler(CommandHandler("kb", self.cmd_kb))
        app.add_handler(CommandHandler("kbweb", self.cmd_kbweb))
        app.add_handler(CommandHandler("kbrm", self.cmd_kbrm))
        app.add_handler(CommandHandler("documento", self.cmd_documento))
        app.add_handler(CommandHandler("exportar", self.cmd_exportar))
        app.add_handler(CommandHandler("transcrever", self.cmd_transcrever))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("silenciar", self.cmd_silenciar))
        app.add_handler(CommandHandler("dados", self.cmd_dados))
        app.add_handler(CommandHandler("limpar", self.cmd_limpar))
        app.add_handler(CommandHandler("limparchat", self.cmd_limparchat))
        app.add_handler(CommandHandler("resumir", self.cmd_resumir))
        app.add_handler(CommandHandler("foco", self.cmd_foco))
        app.add_handler(CommandHandler("agenda", self.cmd_agenda))
        app.add_handler(CommandHandler("evento", self.cmd_evento))
        app.add_handler(CommandHandler("email", self.cmd_email))
        app.add_handler(CommandHandler("emails", self.cmd_emails))
        app.add_handler(CommandHandler("pessoa", self.cmd_pessoa))
        app.add_handler(CommandHandler("pessoas", self.cmd_pessoas))
        # Document upload (PDF) -> knowledge base
        app.add_handler(MessageHandler(filters.Document.ALL, self.on_document))
        # Photo -> multimodal (Gemini vision)
        app.add_handler(MessageHandler(filters.PHOTO, self.on_photo))
        # Audio file (not a voice note) -> transcription
        app.add_handler(MessageHandler(filters.AUDIO, self.on_audio))
        # Voice + free text (must be last)
        app.add_handler(MessageHandler(filters.VOICE, self.on_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        app.add_error_handler(self._on_error)
        log.info("E.V. starting (polling)...")
        app.run_polling()


def run() -> None:
    TelegramInterface(Config.load()).run()
