"""Access control and chat routing: /start, group @mention/reply detection, and
the main text handler (routes to the LLM brain or to pending menu input)."""

from __future__ import annotations

import asyncio
import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

log = logging.getLogger("ev.telegram")


class RoutingMixin:
    def _authorized(self, update: Update) -> bool:
        if self._config.owner_id is None:
            return True  # no owner configured: answer everyone
        user = update.effective_user
        return user is not None and user.id == self._config.owner_id

    @staticmethod
    def _args(ctx: ContextTypes.DEFAULT_TYPE) -> str:
        return " ".join(ctx.args) if ctx.args else ""

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
        await update.message.reply_text(f"E.V. online, Ryan. (seu ID: {uid})")
        await update.message.reply_text(
            self._MAIN_TEXT, reply_markup=self._kb_main(), parse_mode="HTML"
        )

    def _is_reply_to_bot(self, update: Update) -> bool:
        m = update.message
        r = m.reply_to_message if m else None
        return bool(
            r and r.from_user
            and (r.from_user.username or "").lower() == self._bot_username
        )

    @staticmethod
    def _extract_group_query(
        text: str, bot_username: str, reply_from_username: str | None
    ) -> str | None:
        """Pure trigger logic: returns the cleaned query if the message calls the
        bot (reply to it, or @mention), else None. bot_username is lowercase."""
        text = (text or "").strip()
        if (bot_username and reply_from_username
                and reply_from_username.lower() == bot_username):
            return text or None
        if bot_username and f"@{bot_username}" in text.lower():
            cleaned = re.sub(
                rf"@{re.escape(bot_username)}", "", text, flags=re.I
            ).strip()
            return cleaned or None
        return None

    def _group_query(self, update: Update) -> str | None:
        """In a group, E.V. answers only when called: a reply to one of her
        messages, or an @mention. Returns the cleaned query, or None to ignore."""
        m = update.message
        r = m.reply_to_message if m else None
        reply_user = r.from_user.username if (r and r.from_user) else None
        return self._extract_group_query(
            m.text if m else "", self._bot_username, reply_user
        )

    async def on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        user_id = str(update.effective_user.id)
        chat = update.effective_chat

        # In groups: only respond when explicitly called (mention / reply / /ev).
        # Each chat keeps its own conversation thread (conv_id = chat id).
        if chat.type != "private":
            query = self._group_query(update)
            if query is None:
                return
            await self._reply(
                update,
                await self._brain.respond(user_id, conv_id=str(chat.id), text=query),
            )
            return

        # If a menu button asked for input, consume this message as that input
        # (no LLM) instead of treating it as a chat message.
        pending = self._pending.pop(user_id, None)
        if pending:
            if pending == "kb:doc":  # menu-driven document creation (sends a file)
                await self._make_and_send_document(update, update.message.text)
                return
            if pending == "transcribe":  # waiting for audio, not text
                self._pending[user_id] = "transcribe"  # keep waiting
                await update.message.reply_text(
                    "Manda o áudio (mensagem de voz ou arquivo) que eu transcrevo. 🎙️"
                )
                return
            if pending == "wipe_confirm":  # second factor for the full wipe
                if update.message.text.strip().upper() == self._WIPE_PHRASE:
                    n = await asyncio.to_thread(self._memory.clear_all_user_data, user_id)
                    await update.message.reply_text(
                        f"🧹 Pronto. Apaguei {n} itens — recomeçamos do zero.",
                        reply_markup=self._kb_main(),
                    )
                else:
                    await update.message.reply_text(
                        "❌ Cancelado — não apaguei nada. (Pra confirmar era preciso "
                        f"digitar exatamente: {self._WIPE_PHRASE})",
                        reply_markup=self._kb_main(),
                    )
                return
            result = self._handle_pending(user_id, pending, update.message.text)
            await update.message.reply_text(result, reply_markup=self._kb_main())
            return

        await self._reply(
            update,
            await self._brain.respond(
                user_id, conv_id=str(chat.id), text=update.message.text
            ),
        )
