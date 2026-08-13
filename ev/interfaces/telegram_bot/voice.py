"""Voice notes and audio files: transcription and /transcrever."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ...providers import documents as documents_mod


class VoiceMixin:
    async def on_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        # In groups, only handle a voice note that replies to one of her messages.
        if update.effective_chat.type != "private" and not self._is_reply_to_bot(update):
            return
        user_id = str(update.effective_user.id)
        conv_id = str(update.effective_chat.id)
        voice = update.message.voice
        tg_file = await ctx.bot.get_file(voice.file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        # If /transcrever armed the transcription mode, transcribe instead of chatting.
        if self._pending.pop(user_id, None) == "transcribe":
            await self._transcribe_and_deliver(
                update, audio_bytes, voice.mime_type or "audio/ogg"
            )
            return
        await self._reply(
            update,
            await self._brain.respond(
                user_id, conv_id=conv_id,
                audio=audio_bytes, audio_mime=voice.mime_type or "audio/ogg",
            ),
        )

    async def on_audio(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """An audio FILE (not a voice note) — treat as something to transcribe."""
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)
        self._pending.pop(user_id, None)
        audio = update.message.audio
        tg_file = await ctx.bot.get_file(audio.file_id)
        audio_bytes = bytes(await tg_file.download_as_bytearray())
        await self._transcribe_and_deliver(
            update, audio_bytes, audio.mime_type or "audio/mpeg"
        )

    async def _transcribe_and_deliver(self, update: Update, audio: bytes, mime: str) -> None:
        await update.message.reply_text("🎧 Transcrevendo o áudio...")
        text = await self._brain.transcribe(audio, mime)
        if not text:
            await self._cmd_out(
                update, "Não consegui transcrever agora (o serviço de áudio pode estar no limite). Tenta de novo?"
            )
            return
        data, filename = documents_mod.build("txt", "Transcrição", text)
        await self._deliver_document(update.message, {
            "bytes": data, "filename": filename, "title": "Transcrição",
            "content": text, "saved_kb": False,
        })

    async def cmd_transcrever(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        uid = str(update.effective_user.id)
        self._pending[uid] = "transcribe"
        await update.message.reply_text(
            "🎙️ Manda o áudio (mensagem de voz ou arquivo) que eu transcrevo e te "
            "devolvo em texto. Ou é só mandar um arquivo de áudio direto."
        )
