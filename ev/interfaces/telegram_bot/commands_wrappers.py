"""Deterministic slash-command wrappers (delegate to `Commands`), plus the
data/privacy controls (/dados, /limpar, /limparchat), provider selection
(/provedor), diagnostics (/status), do-not-disturb (/silenciar), link
summarization (/resumir), and the AI-powered quiz/insights/model commands."""

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...core import health
from ...core.memory import Memory
from ...providers import tools as tools_mod


class CommandsWrappersMixin:
    _DATA_LABELS = dict(Memory.DATA_TABLES)

    def _data_menu(self, uid: str) -> tuple[str, InlineKeyboardMarkup]:
        summary = self._memory.storage_summary(uid)
        total = sum(s["count"] for s in summary)
        lines = ["🗄️ <b>Seus dados guardados</b>", ""]
        for s in summary:
            lines.append(f"• {html.escape(s['label'])}: <b>{s['count']}</b>")
        lines.append(f"\nTotal: {total} itens.")
        lines.append("\nToque pra apagar uma categoria (pede confirmação). "
                     "Apagar aqui é em massa; pra apagar 1 item use os comandos "
                     "(/esquecer, /gastorm, /cancelar, etc.).")
        b = InlineKeyboardButton
        rows = [
            [b(f"🗑️ {s['label']} ({s['count']})", callback_data=f"data:clr:{s['key']}")]
            for s in summary if s["count"] > 0
        ]
        rows.append([b("🧹 Limpar TUDO", callback_data="data:clr:ALL")])
        rows.append([b("⬅️ Voltar", callback_data="nav:main")])
        return "\n".join(lines), InlineKeyboardMarkup(rows)

    _WIPE_PHRASE = "APAGAR TUDO"

    def _data_confirm(self, uid: str, key: str) -> tuple[str, InlineKeyboardMarkup]:
        """Single-tap confirm for a single category (not the full wipe)."""
        b = InlineKeyboardButton
        n = self._memory.count_rows(key, uid)
        label = self._DATA_LABELS.get(key, key)
        text = (f"Apagar <b>{n}</b> de <b>{html.escape(label)}</b>? "
                "Não dá pra desfazer.")
        yes = b(f"🗑️ Sim, apagar {n}", callback_data=f"data:yes:{key}")
        return text, InlineKeyboardMarkup([[yes], [b("✖️ Cancelar", callback_data="data:menu")]])

    async def cmd_dados(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text, kb = self._data_menu(str(update.effective_user.id))
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    async def cmd_limpar(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        uid = str(update.effective_user.id)
        text, kb = self._data_confirm(uid, "messages")
        await update.message.reply_text(
            "🧽 Limpar a conversa (mantém memórias, lembretes e o resto).\n\n" + text,
            parse_mode="HTML", reply_markup=kb,
        )

    @staticmethod
    def _parse_count(arg: str, default: int = 30, cap: int = 100) -> int | None:
        """Parse an integer count (1..cap). '' -> default; invalid -> None."""
        arg = (arg or "").strip()
        if not arg:
            return default
        if arg.isdigit():
            return max(1, min(cap, int(arg)))
        return None

    _CLEARCHAT_ALL_KW = ("tudo", "todas", "all", "max", "máximo", "maximo")

    async def _delete_range(self, bot, chat_id: int, latest: int, limit: int,
                            stop_after_fails: int | None = None) -> int:
        """Delete messages walking down from `latest`. Stops after `limit`
        attempts, or after `stop_after_fails` consecutive failures (used by
        'tudo' to stop once it hits the un-deletable/older-than-48h zone)."""
        deleted = fails = attempts = 0
        mid = latest
        while attempts < limit and mid > 0:
            try:
                await bot.delete_message(chat_id, mid)
                deleted += 1
                fails = 0
            except Exception:
                fails += 1
                if stop_after_fails and fails >= stop_after_fails:
                    break
            mid -= 1
            attempts += 1
        return deleted

    def _clearchat_note(self, deleted: int, capped: bool) -> str:
        msg = f"🧽 Apaguei {deleted} mensagem(ns) do chat."
        if capped:
            msg += " O Telegram só deixa apagar as dos últimos ~2 dias."
        msg += ("\n\n(Some só com as bolhas; memória/lembretes seguem intactos. "
                "Pra apagar o que a E.V. lembra: /limpar ou /dados.)")
        return msg

    async def cmd_limparchat(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        """Delete the last N (or all possible) visible messages from the chat."""
        if not self._authorized(update):
            return
        arg = self._args(c).strip().lower()
        if arg in self._CLEARCHAT_ALL_KW:
            b = InlineKeyboardButton
            await update.message.reply_text(
                "Apagar TODAS as bolhas possíveis do chat (limite do Telegram: "
                "últimos ~2 dias)? Sua memória e seus dados NÃO são afetados.",
                reply_markup=InlineKeyboardMarkup([
                    [b("🧽 Sim, apagar o máximo", callback_data="clearchat:all")],
                    [b("✖️ Cancelar", callback_data="nav:main")],
                ]),
            )
            return
        n = self._parse_count(arg)
        if n is None:
            await update.message.reply_text(
                "Uso: /limparchat <número> ou /limparchat tudo.\n"
                "Ex: /limparchat 10 (últimas 10 bolhas, máx. 100) · "
                "/limparchat tudo (o máximo possível)."
            )
            return
        chat_id = update.effective_chat.id
        deleted = await self._delete_range(c.bot, chat_id, update.message.message_id, n)
        await c.bot.send_message(
            chat_id, self._clearchat_note(deleted, capped=deleted < n),
            reply_markup=self._quick_kb(),
        )

    async def _handle_data(self, q, uid: str, action: str) -> None:
        op, _, key = action.partition(":")
        if action == "menu" or op == "menu":
            self._pending.pop(uid, None)  # cancels any armed wipe
            text, kb = self._data_menu(uid)
            await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            return
        if op == "clr":
            if key == "ALL":
                # Dangerous -> two-factor: must ALSO type the exact phrase.
                total = sum(s["count"] for s in self._memory.storage_summary(uid))
                self._pending[uid] = "wipe_confirm"
                b = InlineKeyboardButton
                await q.edit_message_text(
                    f"⚠️ <b>Apagar TUDO?</b> ({total} itens de todas as categorias — "
                    "memórias, lembretes, tarefas, gastos, base, conversa...). "
                    "<b>Não dá pra desfazer.</b>\n\n"
                    f"Pra confirmar, <b>digite</b> exatamente:\n<code>{self._WIPE_PHRASE}</code>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        [[b("✖️ Cancelar", callback_data="data:menu")]]
                    ),
                )
                return
            text, kb = self._data_confirm(uid, key)
            await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            return
        if op == "yes":  # single-category confirm (full wipe uses the typed phrase)
            label = self._DATA_LABELS.get(key, key)
            n = await asyncio.to_thread(self._memory.clear_table, key, uid)
            await q.answer("Apagado.")
            text, kb = self._data_menu(uid)
            await q.edit_message_text(
                f"🗑️ Apaguei {n} de {html.escape(label)}.\n\n" + text,
                parse_mode="HTML", reply_markup=kb,
            )

    _PROVIDERS = ("auto", "gemini", "groq", "openrouter", "ollama")

    async def cmd_provedor(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        arg = self._args(c).strip().lower()
        if not arg:
            cur = self._memory.get_setting("force_provider") or "auto"
            await update.message.reply_text(
                f"🔀 Provedor atual: <b>{cur}</b>\n\n"
                "Por padrão é <b>auto</b> (cascata: Gemini → Groq → OpenRouter → Ollama).\n"
                "Forçar um só, pra testar: <code>/provedor groq</code> "
                "(ou gemini, openrouter, ollama).\n"
                "Voltar ao automático: <code>/provedor auto</code>",
                parse_mode="HTML",
            )
            return
        if arg not in self._PROVIDERS:
            await update.message.reply_text(
                "Opções: auto, gemini, groq, openrouter, ollama."
            )
            return
        self._memory.set_setting("force_provider", "" if arg == "auto" else arg)
        if arg == "auto":
            await update.message.reply_text(
                "🔄 Voltei pro automático (Gemini → Groq → OpenRouter → Ollama)."
            )
        else:
            await update.message.reply_text(
                f"📌 Agora respondo SÓ pelo <b>{arg}</b> (modo teste, sem fallback). "
                "Volte ao normal com /provedor auto.",
                parse_mode="HTML",
            )

    def _uptime_str(self) -> str:
        secs = int((datetime.now(timezone.utc) - self._started_at).total_seconds())
        d, secs = divmod(secs, 86400)
        h, secs = divmod(secs, 3600)
        m = secs // 60
        parts = [f"{d}d" if d else "", f"{h}h" if h else "", f"{m}min"]
        return " ".join(p for p in parts if p) or "agora"

    async def cmd_status(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        arg = self._args(c).strip().lower()
        if arg in ("chaves", "teste", "testar", "full", "ping"):
            await self._status_live(update.message)
            return
        rep = await asyncio.to_thread(health.system_report, self._config, self._memory)
        keys = health.keys_status(self._config)
        alive = sum(1 for t in self._bg_tasks if not t.done())
        y, n = "🟢", "🔴"
        lines = ["🩺 <b>Status da E.V.</b>", ""]
        lines.append(f"• Online há: <b>{self._uptime_str()}</b>")
        lines.append(f"• Agendadores ativos: {alive}/{len(self._bg_tasks)} {'🟢' if alive else '🔴'}")
        db = y if rep.get("db_query_ok") else n
        lines.append(f"• Banco de dados: {db} ({rep.get('db_size_mb', 0)} MB)")
        if "disk_used_pct" in rep:
            d = rep["disk_used_pct"]
            lines.append(f"• Disco: {d}% usado · {rep.get('disk_free_gb','?')} GB livres "
                         f"{'🟢' if d < 85 else '🟡' if d < 95 else '🔴'}")
        if "mem_used_pct" in rep:
            mm = rep["mem_used_pct"]
            lines.append(f"• Memória: {mm}% ({rep.get('mem_used_mb','?')}/{rep.get('mem_total_mb','?')} MB) "
                         f"{'🟢' if mm < 85 else '🟡' if mm < 95 else '🔴'}")
        if "load1" in rep:
            lines.append(f"• Carga (1min): {rep['load1']}")
        q = self._quiet_status_line()
        if q:
            lines.append(f"• {q}")
        lines.append("\n🔑 <b>Chaves / integrações</b> (configuradas):")
        for k in keys:
            mark = y if k["ok"] else ("⚪" if k["note"] in ("opcional", "desligado") else n)
            note = f" — <i>{html.escape(k['note'])}</i>" if k["note"] else ""
            lines.append(f"• {mark} {html.escape(k['name'])}{note}")
        lines.append("\n<i>Isso mostra o que está configurado. Para testar as chaves "
                     "ao vivo (faz uma chamada real), toque abaixo.</i>")
        b = InlineKeyboardButton
        kb = InlineKeyboardMarkup([[b("🔌 Testar chaves ao vivo", callback_data="status:live")]])
        await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)

    async def _status_live(self, message) -> None:
        await message.reply_text("🔌 Testando os provedores ao vivo (pode levar alguns segundos)...")
        results = await self._brain.health_check()
        lines = ["🔌 <b>Teste ao vivo dos provedores</b>", ""]
        for r in results:
            mark = "🟢" if r["ok"] else "🔴"
            note = f" — <i>{html.escape(r['note'])}</i>" if r.get("note") else ""
            lines.append(f"• {mark} {html.escape(r['name'])}{note}")
        if not results:
            lines.append("Nenhum provedor configurado para testar.")
        await self._send(message, "\n".join(lines), self._quick_kb())

    def _is_quiet(self) -> bool:
        until = self._memory.get_setting("quiet_until")
        if not until:
            return False
        try:
            return datetime.now(timezone.utc) < datetime.fromisoformat(until)
        except Exception:
            return False

    def _quiet_status_line(self) -> str | None:
        until = self._memory.get_setting("quiet_until")
        if not until:
            return None
        try:
            dt = datetime.fromisoformat(until)
        except Exception:
            return None
        if datetime.now(timezone.utc) >= dt:
            return None
        local = dt.astimezone(self._tz()) if self._tz() else dt
        return f"🔕 Não perturbe até {local.strftime('%d/%m %H:%M')}"

    async def cmd_silenciar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        arg = self._args(c).strip().lower()
        if not arg:
            line = self._quiet_status_line()
            await update.message.reply_text(
                (line + "\nPara ligar avisos: /silenciar off") if line else
                "🔔 Avisos automáticos ativos.\nSilenciar: /silenciar 2h (ou 30m, 1d). "
                "Desligar: /silenciar off"
            )
            return
        if arg in ("off", "0", "fim", "desligar", "ligar"):
            self._memory.set_setting("quiet_until", "")
            await update.message.reply_text("🔔 Avisos automáticos religados.")
            return
        secs = self._parse_duration(arg)
        if not secs:
            await update.message.reply_text("Não entendi. Use /silenciar 2h, 30m ou 1d.")
            return
        until = datetime.now(timezone.utc) + timedelta(seconds=secs)
        self._memory.set_setting("quiet_until", until.isoformat())
        local = until.astimezone(self._tz()) if self._tz() else until
        await update.message.reply_text(
            f"🔕 Ok, não te aviso automaticamente até {local.strftime('%d/%m %H:%M')}. "
            "(Lembretes que você marcou continuam chegando.)"
        )

    @staticmethod
    def _parse_duration(s: str) -> int | None:
        m = re.match(r"^(\d+)\s*(m|min|h|hora|horas|d|dia|dias)$", s)
        if not m:
            return None
        n, unit = int(m.group(1)), m.group(2)
        if unit.startswith("m"):
            return n * 60
        if unit.startswith("h"):
            return n * 3600
        return n * 86400

    async def cmd_resumir(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        await self._summarize_url(update.message, self._args(c).strip())

    async def _summarize_url(self, message, url: str) -> None:
        if not url.lower().startswith("http"):
            await self._send(message, "Uso: /resumir <url>. Ex: /resumir https://...", self._quick_kb())
            return
        await message.reply_text("🌐 Lendo a página e resumindo...")
        try:
            text = await asyncio.to_thread(tools_mod.fetch_text, url)
        except Exception as exc:
            await self._send(message, f"Não consegui abrir essa página ({exc}).", self._quick_kb())
            return
        if not text or len(text.strip()) < 80:
            await self._send(message, "Não achei texto útil nessa página.", self._quick_kb())
            return
        summary = await self._brain.ask(
            "Você é a E.V. Resuma o artigo em português: um parágrafo curto de contexto "
            "e depois 3 a 6 bullets com os pontos principais. Seja fiel ao texto.",
            f"Conteúdo de {url}:\n\n{text[:12000]}",
        )
        if not summary:
            await self._send(message, "Não consegui resumir agora, tenta de novo?", self._quick_kb())
            return
        did = self._stash_doc(f"Resumo — {url[:60]}", summary)
        b = InlineKeyboardButton
        kb = InlineKeyboardMarkup([[b("📚 Salvar na base", callback_data=f"docsave:{did}")]])
        parts = self._split(f"📰 Resumo\n\n{summary}")
        for i, part in enumerate(parts):
            await message.reply_text(part, reply_markup=kb if i == len(parts) - 1 else None)

    async def cmd_ajuda(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.help())

    async def cmd_ev(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        """Explicitly talk to the AI — handy in groups: /ev <mensagem>."""
        if not self._authorized(update):
            return
        q = self._args(c).strip()
        if not q:
            await update.message.reply_text(
                "Uso: /ev <mensagem>. Ex: /ev resume os pontos principais disso."
            )
            return
        await self._reply(
            update,
            await self._brain.respond(
                str(update.effective_user.id),
                conv_id=str(update.effective_chat.id), text=q,
            ),
        )

    async def cmd_plano(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        """Agentic day plan: 'resolve minha manhã'."""
        if not self._authorized(update):
            return
        await self._reply(
            update, await self._brain.plan_day(str(update.effective_user.id)))

    async def cmd_pendencias(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        """Proactive open loops on demand: what's overdue / due / charging soon."""
        if not self._authorized(update):
            return
        msg = self._commands.nudge_text(str(update.effective_user.id))
        await self._cmd_out(update, msg or "Tudo em dia — nada atrasado. 👌")

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

    async def cmd_procurar(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.procurar(uid, self._args(c)))

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

    _PROVIDER_LABELS = {
        "gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter",
        "ollama": "Ollama (local)", "?": "desconhecido",
    }

    _APPROX_CAPS = {"gemini": 20, "groq": 1000, "openrouter": 1000}

    async def cmd_modelo(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        arg = self._args(c).strip()
        if arg:
            low = arg.lower()
            if low in ("reset", "padrão", "padrao", "default"):
                self._memory.set_setting("model", "")
                await update.message.reply_text(
                    "Modelo principal voltou ao padrão (gemini-flash-latest)."
                )
                return
            if low in ("gemini", "gemini-", "geminis"):
                await update.message.reply_text(
                    "'gemini' sozinho não é um modelo válido — precisa da versão, "
                    "ex: gemini-flash-latest ou gemini-2.5-flash.\n\n"
                    "Quer só FORÇAR o provedor Gemini pra testar? Use /provedor gemini.\n"
                    "Pra voltar ao padrão: /modelo reset"
                )
                return
            if not low.startswith("gemini"):
                await update.message.reply_text(
                    "O /modelo troca só o modelo PRINCIPAL, que é do Gemini — "
                    "use um nome que comece com 'gemini' (ex: gemini-flash-latest).\n\n"
                    "Pra testar Groq/OpenRouter/Ollama, use /provedor <nome>.\n"
                    "Pra voltar ao padrão: /modelo reset"
                )
                return
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
        forced = self._memory.get_setting("force_provider")
        if forced:
            lines.append(f"\n📌 Forçado em: <b>{self._PROVIDER_LABELS.get(forced, forced)}</b> (teste) · liberar: /provedor auto")
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

    async def cmd_agenda(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.agenda(self._args(c)))

    async def cmd_evento(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.evento(self._args(c)))

    async def cmd_email(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.email(self._args(c)))

    async def cmd_emails(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            await self._cmd_out(update, self._commands.emails(self._args(c)))

    async def cmd_pessoa(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.pessoa(uid, self._args(c)))

    async def cmd_pessoas(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        if self._authorized(update):
            uid = str(update.effective_user.id)
            await self._cmd_out(update, self._commands.pessoas(uid))
