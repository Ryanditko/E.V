"""Interface de Telegram do E.V.

Recebe mensagens de texto e de voz, passa pro cérebro e responde. Se
EV_VOICE_REPLY estiver ligado, responde também com áudio (edge-tts).

Trava o acesso ao dono (EV_OWNER_ID) quando configurado — importante, porque
qualquer pessoa que ache o bot poderia conversar com ele.
"""

from __future__ import annotations

import io
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..brain import Brain
from ..config import Config
from ..memory import Memory
from .. import voice as voice_mod

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

    # --- controle de acesso -------------------------------------------------

    def _authorized(self, update: Update) -> bool:
        if self._config.owner_id is None:
            return True  # sem dono configurado: responde a todos
        user = update.effective_user
        return user is not None and user.id == self._config.owner_id

    # --- handlers -----------------------------------------------------------

    async def on_start(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        uid = user.id if user else "?"
        log.info("Comando /start de user_id=%s", uid)
        if not self._authorized(update):
            await update.message.reply_text(
                f"Não te reconheço. Seu ID é {uid}. "
                "Se você é o dono, coloque-o em EV_OWNER_ID no .env."
            )
            return
        await update.message.reply_text(
            "E.V. online. Manda texto ou áudio que eu te respondo. "
            f"(seu ID: {uid})"
        )

    async def on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)
        await self._reply(update, await self._brain.respond(
            user_id, text=update.message.text
        ))

    async def on_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)
        voice = update.message.voice
        tg_file = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        await self._reply(update, await self._brain.respond(
            user_id, audio=audio_bytes, audio_mime=voice.mime_type or "audio/ogg"
        ))

    # --- resposta -----------------------------------------------------------

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
        except Exception:  # voz é um extra — nunca deixa quebrar a resposta
            log.exception("Falha ao gerar áudio (respondi só em texto)")

    # --- runner -------------------------------------------------------------

    def run(self) -> None:
        app = Application.builder().token(self._config.telegram_token).build()
        app.add_handler(CommandHandler("start", self.on_start))
        app.add_handler(MessageHandler(filters.VOICE, self.on_voice))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text)
        )
        log.info("E.V. iniciando (polling)...")
        app.run_polling()


def run() -> None:
    TelegramInterface(Config.load()).run()
