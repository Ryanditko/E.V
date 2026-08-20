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
from ...core.commands import Commands, command_list, english_name
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
        # Command handlers. Each command is registered under its Portuguese
        # (canonical) name AND its English alias (via english_name), so both
        # /lembrete and /remind reach the same handler — non-breaking.
        app.add_handler(CommandHandler("start", self.on_start))
        # Chat (LLM)
        chat_cmds = [
            ("menu", self.cmd_menu),
            ("ev", self.cmd_ev),
            ("plano", self.cmd_plano),
            ("pendencias", self.cmd_pendencias),
            ("backup", self.cmd_backup),
            ("padroes", self.cmd_padroes),
            ("automacoes", self.cmd_automacoes),
            ("automacaorm", self.cmd_automacaorm),
        ]
        # Deterministic commands (no LLM)
        det_cmds = [
            ("ajuda", self.cmd_ajuda),
            ("lembrete", self.cmd_lembrete),
            ("rotina", self.cmd_rotina),
            ("cancelar", self.cmd_cancelar),
            ("lembretes", self.cmd_lembretes),
            ("tarefa", self.cmd_tarefa),
            ("tarefas", self.cmd_tarefas),
            ("concluir", self.cmd_concluir),
            ("buscar", self.cmd_buscar),
            ("procurar", self.cmd_procurar),
            ("clima", self.cmd_clima),
            ("noticias", self.cmd_noticias),
            ("calendario", self.cmd_calendario),
            ("gasto", self.cmd_gasto),
            ("gastos", self.cmd_gastos),
            ("habito", self.cmd_habito),
            ("feito", self.cmd_feito),
            ("habitos", self.cmd_habitos),
            ("diario", self.cmd_diario),
            ("esquecer", self.cmd_esquecer),
            ("gastorm", self.cmd_gastorm),
            ("habitorm", self.cmd_habitorm),
            ("diariorm", self.cmd_diariorm),
            ("semana", self.cmd_semana),
            ("vigiar", self.cmd_vigiar),
            ("vigias", self.cmd_vigias),
            ("vigiarm", self.cmd_vigiarm),
            ("assinatura", self.cmd_assinatura),
            ("assinaturas", self.cmd_assinaturas),
            ("assinaturarm", self.cmd_assinaturarm),
            ("orcamento", self.cmd_orcamento),
            ("orcamentos", self.cmd_orcamentos),
            ("orcamentorm", self.cmd_orcamentorm),
            ("relatorio", self.cmd_relatorio),
            ("quiz", self.cmd_quiz),
            ("insights", self.cmd_insights),
            ("modelo", self.cmd_modelo),
            ("provedor", self.cmd_provedor),
            ("idioma", self.cmd_idioma),
            ("lembrar", self.cmd_lembrar),
            ("memorias", self.cmd_memorias),
            ("link", self.cmd_link),
            ("links", self.cmd_links),
            ("linkrm", self.cmd_linkrm),
            ("kb", self.cmd_kb),
            ("kbweb", self.cmd_kbweb),
            ("kbrm", self.cmd_kbrm),
            ("documento", self.cmd_documento),
            ("exportar", self.cmd_exportar),
            ("transcrever", self.cmd_transcrever),
            ("status", self.cmd_status),
            ("silenciar", self.cmd_silenciar),
            ("dados", self.cmd_dados),
            ("limpar", self.cmd_limpar),
            ("limparchat", self.cmd_limparchat),
            ("resumir", self.cmd_resumir),
            ("foco", self.cmd_foco),
            ("agenda", self.cmd_agenda),
            ("evento", self.cmd_evento),
            ("email", self.cmd_email),
            ("emails", self.cmd_emails),
            ("pessoa", self.cmd_pessoa),
            ("pessoas", self.cmd_pessoas),
        ]

        def _register(pairs):
            for pt, cb in pairs:
                names = [pt]
                en = english_name(pt)
                if en != pt:
                    names.append(en)
                app.add_handler(CommandHandler(names, cb))

        _register(chat_cmds)
        app.add_handler(CallbackQueryHandler(self.on_callback))
        _register(det_cmds)
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
