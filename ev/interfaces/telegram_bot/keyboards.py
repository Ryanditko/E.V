"""Navigation keyboards for the interactive menu (/menu), and the main menu
text/handler."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


class KeyboardsMixin:
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
                [b("📤 Exportar dados", callback_data="export:menu"),
                 b("🗄️ Meus dados", callback_data="data:menu")],
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
                [b("📝 Criar documento", callback_data="kb:doc")],
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
