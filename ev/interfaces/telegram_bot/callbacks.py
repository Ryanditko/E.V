"""The interactive menu's callback-query dispatcher: routes inline-button taps
by section/action to the right handler (delegating to other mixins via
`self`), plus the menu-specific list/prompt/pending-input helpers."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


class CallbacksMixin:
    async def on_callback(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        await q.answer()
        if self._config.owner_id is not None and (
            not q.from_user or q.from_user.id != self._config.owner_id
        ):
            return
        uid = str(q.from_user.id)
        section, _, action = q.data.partition(":")

        if section == "loctask":
            await self._handle_loctask(q, uid, action)
            return
        if section == "locconfirm":
            await self._handle_locconfirm(q, uid, action)
            return
        if section == "docsave":
            await self._save_doc_to_kb(q, uid, action)
            return
        if section == "remdone":
            self._pending_rem.pop(action, None)
            await q.answer("Feito! ✅")
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return
        if section == "remsnooze":
            await self._snooze_reminder(q, uid, action)
            return
        if section == "status" and action == "live":
            await q.answer("Testando...")
            await self._status_live(q.message)
            return
        if section == "data":
            await self._handle_data(q, uid, action)
            return
        if section == "pomo":
            await self._handle_pomo(q, action)
            return
        if section == "clearchat" and action == "all":
            await q.answer("Apagando o máximo...")
            bot = q.get_bot()
            chat_id = q.message.chat_id
            deleted = await self._delete_range(
                bot, chat_id, q.message.message_id, limit=2000, stop_after_fails=40
            )
            await bot.send_message(
                chat_id, self._clearchat_note(deleted, capped=True),
                reply_markup=self._quick_kb(),
            )
            return
        if section == "fileact":
            await self._handle_fileact(q, uid, action)
            return
        if section == "ocr":
            await self._handle_ocr(q, uid, action)
            return
        if section == "receipt":
            await self._handle_receipt(q, uid, action)
            return
        if section == "expok":
            await self._confirm_expense(q, uid, action)
            return
        if section == "expno":
            self._pending_expense.pop(action, None)
            await q.answer("Cancelado.")
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return
        if section == "export":
            if action == "menu":
                await q.edit_message_text(
                    "📤 O que você quer exportar?", reply_markup=self._kb_export()
                )
                return
            await q.answer("Gerando...")
            if action == "csv":
                await self._export_csv(q.message, uid)
            else:
                await self._export_pdf(q.message, uid)
            return

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
        if section == "kb" and action == "doc":
            return (
                "📝 Formato: <formato> <título> | <conteúdo>\n"
                "Ex: pdf Lista de compras | arroz, feijão, café\n"
                "Formatos: txt, md, pdf, docx. O formato é opcional (padrão pdf)."
            )
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
