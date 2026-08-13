"""Media, documents and AI-driven actions: photos, uploaded files, generated
documents (export/create), the receipt/OCR/knowledge-base callback handlers,
and the generic chat-output helpers (send/split/quick-action-bar) plus the
`_reply` composer used by the routing/voice handlers to deliver an answer
(text, generated files, AI-requested interface actions, and optional TTS)."""

from __future__ import annotations

import asyncio
import html
import io
import logging
from types import SimpleNamespace

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...core import knowledge
from ...providers import documents as documents_mod, voice as voice_mod

log = logging.getLogger("ev.telegram")


class MediaMixin:
    async def on_photo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        # In groups, only handle a photo that replies to one of her messages.
        if update.effective_chat.type != "private" and not self._is_reply_to_bot(update):
            return
        user_id = str(update.effective_user.id)
        photo = update.message.photo[-1]  # largest resolution
        tg_file = await ctx.bot.get_file(photo.file_id)
        img = bytes(await tg_file.download_as_bytearray())
        answer = await self._brain.respond(
            user_id, conv_id=str(update.effective_chat.id),
            text=update.message.caption, image=img, image_mime="image/jpeg",
        )
        fid = self._stash(self._pending_images, (img, "image/jpeg"))
        self._trim(self._pending_images, 8)  # image bytes are heavy; keep few
        await self._reply(update, answer, self._photo_kb(fid))

    def _photo_kb(self, fid: str) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup([
            [b("📄 Extrair texto (OCR)", callback_data=f"ocr:{fid}")],
            [b("💰 Lançar gasto", callback_data=f"receipt:{fid}")],
            [b("🏠 Menu", callback_data="nav:main"),
             b("➕ Tarefa", callback_data="task:add"),
             b("⏰ Lembrete", callback_data="rem:add")],
        ])

    _DOC_USAGE = (
        "Uso: /documento <formato> <título> | <conteúdo>\n"
        "Ex: /documento pdf Lista de compras | arroz, feijão, café\n"
        "Formatos: txt, md, pdf, docx (ou 'word'). O formato é opcional (padrão pdf).\n"
        "Dica: você também pode só me pedir no chat, ex: \"me manda isso em PDF\"."
    )

    @staticmethod
    def _parse_doc_request(raw: str):
        """Parse '<formato> <título> | <conteúdo>'. Returns (fmt, title, content, error)."""
        raw = (raw or "").strip()
        if "|" not in raw:
            return None, None, None, MediaMixin._DOC_USAGE
        left, content = raw.split("|", 1)
        left, content = left.strip(), content.strip()
        if not content:
            return None, None, None, MediaMixin._DOC_USAGE
        tokens = left.split()
        fmt = "pdf"
        if tokens and documents_mod.normalize_format(tokens[0]):
            fmt, title = tokens[0], " ".join(tokens[1:]).strip()
        else:
            title = left
        return fmt, (title or "Documento"), content, None

    async def _make_and_send_document(self, update: Update, raw: str) -> None:
        fmt, title, content, err = self._parse_doc_request(raw)
        if err:
            await self._cmd_out(update, err)
            return
        try:
            data, filename = await asyncio.to_thread(
                documents_mod.build, fmt, title, content
            )
        except ValueError as exc:
            await self._cmd_out(update, str(exc))
            return
        await self._deliver_document(update.message, {
            "bytes": data, "filename": filename, "title": title,
            "content": content, "saved_kb": False,
        })

    async def cmd_documento(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._make_and_send_document(update, self._args(c))

    def _kb_export(self) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup([
            [b("📊 Gastos (CSV)", callback_data="export:csv")],
            [b("🗂️ Meus dados (PDF)", callback_data="export:pdf")],
            [b("⬅️ Voltar", callback_data="nav:main")],
        ])

    async def cmd_exportar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        uid = str(update.effective_user.id)
        arg = self._args(c).strip().lower()
        if arg in ("gastos", "gasto", "csv", "financeiro"):
            await self._export_csv(update.message, uid)
        elif arg in ("dados", "tudo", "pdf"):
            await self._export_pdf(update.message, uid)
        else:
            await update.message.reply_text(
                "O que você quer exportar?", reply_markup=self._kb_export()
            )

    async def _export_csv(self, message, uid: str) -> None:
        res = await asyncio.to_thread(self._commands.export_expenses_csv, uid)
        if isinstance(res, str):  # error/empty message
            await self._send(message, res, self._quick_kb())
            return
        data, filename = res
        buf = io.BytesIO(data)
        buf.name = filename
        await message.reply_document(
            document=buf, filename=filename,
            caption="📊 Seus gastos em CSV (abre no Excel / Google Sheets).",
            reply_markup=self._quick_kb(),
        )

    async def _export_pdf(self, message, uid: str) -> None:
        title, content = await asyncio.to_thread(self._commands.data_digest, uid)
        data, filename = documents_mod.build("pdf", title, content)
        await self._deliver_document(message, {
            "bytes": data, "filename": filename, "title": title,
            "content": content, "saved_kb": False,
        })

    async def on_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        doc = update.message.document
        filename = doc.file_name or "documento"
        if not filename.lower().endswith(knowledge.READABLE_EXTS):
            await self._cmd_out(
                update, "Consigo ler PDF, Word (.docx) e texto (.txt, .md). Manda um desses."
            )
            return
        await update.message.reply_text("📥 Recebi o arquivo, estou lendo...")
        tg_file = await ctx.bot.get_file(doc.file_id)
        data = bytes(await tg_file.download_as_bytearray())
        text = await asyncio.to_thread(knowledge.extract_text, data, filename)
        if not text.strip():
            await self._cmd_out(
                update, "Não achei texto extraível nesse arquivo (talvez seja escaneado/imagem)."
            )
            return
        fid = self._stash(self._pending_files, (filename, text))
        b = InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [b("📝 Resumir", callback_data=f"fileact:sum:{fid}"),
             b("📚 Indexar na base", callback_data=f"fileact:kb:{fid}")],
        ])
        await update.message.reply_text(
            f"📄 <b>{html.escape(filename)}</b> — {len(text)} caracteres.\n"
            "O que você quer que eu faça?",
            parse_mode="HTML", reply_markup=kb,
        )

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

    @staticmethod
    def _trim(store: dict, keep: int = 50) -> None:
        if len(store) > keep:
            for k in list(store)[:-keep]:
                store.pop(k, None)

    def _stash(self, store: dict, value) -> str:
        self._doc_seq += 1
        sid = str(self._doc_seq)
        store[sid] = value
        self._trim(store)
        return sid

    def _stash_doc(self, title: str, content: str) -> str:
        return self._stash(self._pending_docs, (title, content))

    async def _deliver_document(self, message, artifact: dict) -> None:
        """Send a generated file; offer a 'save to knowledge base' button unless
        it was already saved."""
        buf = io.BytesIO(artifact["bytes"])
        buf.name = artifact["filename"]
        kb = None
        if artifact.get("saved_kb"):
            caption = f"📄 {artifact['filename']} · também salvei na base de conhecimento."
        else:
            did = self._stash_doc(artifact["title"], artifact.get("content", ""))
            caption = f"📄 {artifact['filename']}"
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📚 Salvar na base", callback_data=f"docsave:{did}")]]
            )
        await message.reply_document(document=buf, filename=artifact["filename"],
                                     caption=caption, reply_markup=kb)

    async def _flush_documents(self, message) -> None:
        for artifact in self._brain.pop_documents():
            try:
                await self._deliver_document(message, artifact)
            except Exception:
                log.exception("Failed to deliver generated document")

    _AI_INTERFACE_CMDS = {
        "foco": "cmd_foco", "silenciar": "cmd_silenciar", "exportar": "cmd_exportar",
        "status": "cmd_status", "resumir": "cmd_resumir", "limparchat": "cmd_limparchat",
        "dados": "cmd_dados", "limpar": "cmd_limpar", "quiz": "cmd_quiz",
        "insights": "cmd_insights", "modelo": "cmd_modelo", "ajuda": "cmd_ajuda",
        "padroes": "cmd_padroes",
        "documento": "cmd_documento", "transcrever": "cmd_transcrever", "menu": "cmd_menu",
        "provedor": "cmd_provedor",
    }

    async def _run_actions(self, update: Update) -> None:
        """Run interface-level commands the AI requested this turn."""
        for act in self._brain.pop_actions():
            name = self._AI_INTERFACE_CMDS.get(act.get("command", ""))
            if not name:
                continue
            try:
                # Synthesize a context so we can reuse the real command handler.
                ctx = SimpleNamespace(
                    args=(act.get("args") or "").split(), bot=update.get_bot()
                )
                await getattr(self, name)(update, ctx)
            except Exception:
                log.exception("Failed to run AI-requested command %s", act)

    async def _handle_fileact(self, q, uid: str, action: str) -> None:
        """Buttons under a received file: 'sum:<id>' summarize, 'kb:<id>' index."""
        what, _, fid = action.partition(":")
        entry = self._pending_files.get(fid)
        if entry is None:
            await q.answer("Esse arquivo expirou. Envia de novo, por favor.", show_alert=True)
            return
        filename, text = entry
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        if what == "kb":
            await q.answer("Indexando na base...")
            self._pending_files.pop(fid, None)
            try:
                stored, truncated = await asyncio.to_thread(
                    knowledge.ingest_text, text, filename, self._config, self._memory, uid
                )
                extra = " (arquivo grande — indexei o começo)" if truncated else ""
                msg = (
                    f"📚 '{filename}' indexado: {stored} trechos{extra}. Pode me perguntar sobre ele!"
                    if stored else "Não consegui extrair trechos úteis desse arquivo."
                )
            except Exception:
                log.exception("Failed to index received file")
                msg = "Não consegui indexar agora. Tenta de novo?"
            await q.message.reply_text(msg, reply_markup=self._quick_kb())
            return
        # summarize
        await q.answer("Resumindo...")
        await q.message.reply_text("📝 Lendo e resumindo o documento...")
        summary = await self._brain.ask(
            "Você é a E.V. Resuma o documento do usuário em português: pontos "
            "principais em bullets curtos e, se houver, ações/prazos. Seja fiel ao texto.",
            f"Documento '{filename}':\n\n{text[:12000]}",
        )
        await self._send(
            q.message, summary or "Não consegui resumir agora, tenta de novo?",
            self._quick_kb(),
        )

    async def _handle_receipt(self, q, uid: str, fid: str) -> None:
        entry = self._pending_images.get(fid)
        if entry is None:
            await q.answer("Essa imagem expirou. Envia de novo, por favor.", show_alert=True)
            return
        image, mime = entry
        await q.answer("Lendo o comprovante...")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        exp = await self._brain.extract_receipt(image, mime)
        if not exp:
            await q.message.reply_text(
                "Não consegui identificar um valor nesse comprovante. "
                "Você pode lançar na mão: /gasto 50 mercado #casa",
                reply_markup=self._quick_kb(),
            )
            return
        self._pending_images.pop(fid, None)
        eid = self._stash(self._pending_expense, exp)
        self._trim(self._pending_expense, 20)
        b = InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [b(f"✅ Confirmar R$ {exp['amount']:.2f}", callback_data=f"expok:{eid}")],
            [b("❌ Cancelar", callback_data=f"expno:{eid}")],
        ])
        await q.message.reply_text(
            f"Identifiquei este gasto:\n\n"
            f"💰 R$ {exp['amount']:.2f}\n"
            f"📝 {exp['description']}\n"
            f"🏷️ #{exp['category']}\n\nConfirma o lançamento?",
            reply_markup=kb,
        )

    async def _handle_loctask(self, q, uid: str, action: str) -> None:
        decision, _, tid_s = action.partition(":")
        try:
            tid = int(tid_s)
        except ValueError:
            return
        status = "approved" if decision == "aprovar" else "rejected"
        ok = self._memory.set_local_task_status(uid, tid, status)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        if not ok:
            await q.answer("Esse pedido já foi decidido.", show_alert=True)
            return
        await q.answer("Aprovado ✅" if status == "approved" else "Recusado")
        await q.message.reply_text(
            "Aprovado — vai rodar no seu computador assim que o executor local sincronizar."
            if status == "approved" else "Recusado.",
        )

    async def _handle_locconfirm(self, q, uid: str, action: str) -> None:
        """Second-tier confirmation: a browser task already approved once is
        paused mid-execution on a risky step (e.g. WhatsApp/Instagram send)
        and waiting on this separate decision before it's allowed to click."""
        decision, _, cid_s = action.partition(":")
        try:
            cid = int(cid_s)
        except ValueError:
            return
        status = "approved" if decision == "aprovar" else "rejected"
        ok = self._memory.set_local_confirm_status(uid, cid, status)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        if not ok:
            await q.answer("Essa confirmação já foi decidida.", show_alert=True)
            return
        await q.answer("Confirmado ✅" if status == "approved" else "Recusado")
        await q.message.reply_text(
            "Confirmado — o executor local vai prosseguir com essa ação agora."
            if status == "approved" else "Recusado — o executor local vai cancelar essa ação.",
        )

    async def _confirm_expense(self, q, uid: str, eid: str) -> None:
        exp = self._pending_expense.pop(eid, None)
        if exp is None:
            await q.answer("Esse lançamento expirou. Manda a foto de novo.", show_alert=True)
            return
        await q.answer("Lançando...")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        argstr = f"{exp['amount']:.2f} {exp['description']} #{exp['category']}"
        result = self._commands.gasto(uid, argstr)
        await q.message.reply_text(result, reply_markup=self._quick_kb())

    async def _handle_ocr(self, q, uid: str, fid: str) -> None:
        entry = self._pending_images.get(fid)
        if entry is None:
            await q.answer("Essa imagem expirou. Envia de novo, por favor.", show_alert=True)
            return
        image, mime = entry
        await q.answer("Extraindo texto...")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.message.reply_text("📄 Extraindo o texto da imagem...")
        text = await self._brain.ocr_image(image, mime)
        if not text or text.strip() == "(sem texto)":
            await q.message.reply_text(
                "Não achei texto legível nessa imagem.", reply_markup=self._quick_kb()
            )
            return
        self._pending_images.pop(fid, None)
        data, filename = documents_mod.build("txt", "Texto extraído", text)
        await self._deliver_document(q.message, {
            "bytes": data, "filename": filename, "title": "Texto extraído",
            "content": text, "saved_kb": False,
        })

    async def _save_doc_to_kb(self, q, uid: str, did: str) -> None:
        """Handle the 'save to knowledge base' button under a generated file."""
        title, content = self._pending_docs.pop(did, (None, None))
        if content is None:
            await q.answer("Esse documento expirou. Gere de novo, se quiser salvar.", show_alert=True)
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return
        await q.answer("Salvando na base...")
        try:
            stored, _ = await asyncio.to_thread(
                knowledge.ingest_text, content, title, self._config, self._memory, uid
            )
            msg = f"📚 '{title}' salvo na base de conhecimento ({stored} trechos)."
        except Exception:
            log.exception("Failed to save generated document to KB")
            msg = "Não consegui salvar na base agora. Tenta de novo?"
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.message.reply_text(msg, reply_markup=self._quick_kb())

    async def _reply(self, update: Update, answer: str, kb: InlineKeyboardMarkup | None = None) -> None:
        await self._send(update.message, answer, kb or self._quick_kb())
        await self._flush_documents(update.message)
        await self._run_actions(update)
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
