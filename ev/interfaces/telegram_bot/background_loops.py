"""Background schedulers ("_bg_tasks" started in `base.py::_post_init`): DB
backup, daily briefing, event/subscription/budget/rain/habit alerts, weekly
and monthly reports, automations, watches, check-ins, and the reminder
scheduler (including snooze/advance logic)."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ContextTypes

from ...core.i18n import t as _t
from ...core.timeparse import add_months

log = logging.getLogger("ev.telegram")


class BackgroundLoopsMixin:
    async def _backup_loop(self, app: Application) -> None:
        while True:
            try:
                path = await asyncio.to_thread(self._do_backup)
                await self._maybe_send_backup_telegram(app, path)
            except Exception:
                log.exception("Backup failed")
            await asyncio.sleep(24 * 3600)

    def _do_backup(self, keep: int = 7):
        # Prune old chat history first (bounds the DB size over time).
        try:
            self._memory.prune_messages(self._config.message_history_keep)
        except Exception:
            log.exception("Prune failed")
        bdir = self._config.db_path.parent / "backups"
        bdir.mkdir(exist_ok=True)
        dest = bdir / f"ev_memory.{datetime.now().strftime('%Y%m%d')}.db"
        self._memory.backup(dest)
        for f in sorted(bdir.glob("ev_memory.*.db"))[:-keep]:
            f.unlink()
        log.info("DB backup saved to %s", dest.name)
        return dest

    async def _maybe_send_backup_telegram(self, app: Application, path) -> None:
        """Send the encrypted backup off the VM, into the owner's Telegram chat —
        once per day. Off-site + encrypted means losing the VM never loses data."""
        cfg = self._config
        if not cfg.telegram_backup or cfg.owner_id is None or path is None:
            return
        today = datetime.now(self._tz()).date().isoformat()
        if self._last_tg_backup == today:  # already sent today
            return
        self._last_tg_backup = today
        await self._send_backup_doc(app, path)

    async def _send_backup_doc(self, app: Application, path) -> bool:
        cfg = self._config
        if cfg.owner_id is None or path is None:
            return False
        try:
            with open(path, "rb") as f:
                await app.bot.send_document(
                    chat_id=cfg.owner_id,
                    document=f,
                    filename=path.name,
                    caption="🗄️ Backup cifrado da E.V. Guarde — restaura tudo com a EV_DB_KEY.",
                )
            log.info("Backup sent to Telegram (%s).", path.name)
            return True
        except Exception:
            log.exception("Failed to send backup to Telegram")
            return False

    async def cmd_backup(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        """On-demand off-VM backup: /backup sends a fresh encrypted copy now."""
        if not self._authorized(update):
            return
        await update.message.reply_text("Gerando backup cifrado…")
        try:
            path = await asyncio.to_thread(self._do_backup)
            with open(path, "rb") as f:
                await update.message.reply_document(
                    document=f, filename=path.name,
                    caption="🗄️ Backup cifrado da E.V. Restaura com a EV_DB_KEY.")
            self._last_tg_backup = datetime.now(self._tz()).date().isoformat()
        except Exception:
            log.exception("On-demand backup failed")
            await update.message.reply_text(
                "Falha ao gerar/enviar o backup. Vou tentar de novo no ciclo diário.")

    async def _briefing_loop(self, app: Application) -> None:
        while True:
            try:
                await self._maybe_run_recurring(app)  # bookkeeping — runs even when muted
                if not self._is_quiet():  # /silenciar mutes proactive pings
                    await self._maybe_send_briefing(app)
                    await self._maybe_send_checkin(app)
                    await self._maybe_send_event_alerts(app)
                    await self._maybe_send_weekly(app)
                    await self._maybe_send_rain(app)
                    await self._maybe_habit_nudge(app)
                    await self._maybe_nudge(app)
                    await self._maybe_insight(app)
                    await self._maybe_run_automations(app)
                    await self._maybe_monthly_report(app)
                    await self._maybe_subscription_due(app)
                    await self._maybe_budget_alert(app)
            except Exception:
                log.exception("Briefing loop error")
            await asyncio.sleep(60)

    async def _maybe_send_weekly(self, app: Application) -> None:
        cfg = self._config
        if cfg.weekly_day < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if (
            now.weekday() == cfg.weekly_day
            and now.hour == cfg.weekly_hour
            and self._last_weekly != today
        ):
            self._last_weekly = today
            text = self._commands.semana(str(cfg.owner_id))
            insights = await self._brain.ask(
                "Você é a E.V. Dê 2-3 insights curtos e humanos sobre a semana do "
                "usuário (padrões, elogios, alertas gentis). Breve, em português.",
                self._week_data_blob(str(cfg.owner_id)),
            )
            if insights:
                text += "\n\n🧠 Insights:\n" + insights
            await self._bot_send(app.bot, cfg.owner_id, text, self._quick_kb())
            log.info("Sent weekly review.")

    @staticmethod
    def _alert_lead_minutes(start_iso: str, now, lead: int):
        """Minutes until `start_iso` if it falls within (0, lead]; else None.
        Tolerates tz-naive starts (assumes UTC)."""
        from datetime import datetime, timezone
        try:
            start = datetime.fromisoformat(start_iso)
        except (ValueError, TypeError):
            return None
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        mins = (start - now).total_seconds() / 60
        if 0 <= mins <= lead:
            return int(round(mins))
        return None

    async def _maybe_send_event_alerts(self, app: Application) -> None:
        cfg = self._config
        lead = getattr(cfg, "event_alert_minutes", 30)
        if lead <= 0 or cfg.owner_id is None or not cfg.google_authorized():
            return
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        try:
            from ...providers import tools
            events = await asyncio.to_thread(
                tools.calendar_list_range, cfg, cfg.default_account,
                now.isoformat(), (now + timedelta(minutes=lead)).isoformat(),
                250, self._memory.assistant_lang())
        except Exception:
            log.warning("event alert fetch failed", exc_info=True)
            return
        for e in events:
            eid = e.get("id")
            if not eid or eid in self._alerted_events or e.get("all_day"):
                continue
            mins = self._alert_lead_minutes(e.get("start") or "", now, lead)
            if mins is None:
                continue
            self._alerted_events.add(eid)
            when = "agora" if mins <= 1 else f"em {mins} min"
            msg = f'📅 "{e.get("summary", "(sem título)")}" começa {when}.'
            await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
            try:  # persist to the web notification center + push to devices
                from ...providers import push
                await asyncio.to_thread(push.send_push, cfg, self._memory,
                                        "📅 Evento chegando", msg, "/", str(cfg.owner_id))
            except Exception:
                pass
        if len(self._alerted_events) > 500:  # keep the dedupe set bounded
            self._alerted_events.clear()

    async def _proactive_send(self, app: Application, title: str, msg: str) -> None:
        """Deliver a proactive alert to Telegram + web push + notification center."""
        cfg = self._config
        if cfg.owner_id is None:
            return
        await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
        try:  # send_push also persists to the web notification center
            from ...providers import push
            await asyncio.to_thread(push.send_push, cfg, self._memory,
                                    title, msg, "/", str(cfg.owner_id))
        except Exception:
            pass

    async def _maybe_subscription_due(self, app: Application) -> None:
        cfg = self._config
        if cfg.owner_id is None:
            return
        today = datetime.now(self._tz()).date().isoformat()
        if self._last_subdue == today:  # one heads-up sweep per day
            return
        self._last_subdue = today
        for s in self._commands.subscriptions_due(str(cfg.owner_id)):
            when = "amanhã" if s["days_until"] == 1 else f"em {s['days_until']} dias"
            msg = f"💳 Sua assinatura {s['description']} (R$ {s['amount']:.2f}) vence {when}."
            await self._proactive_send(app, "💳 Assinatura chegando", msg)

    async def _maybe_budget_alert(self, app: Application) -> None:
        cfg = self._config
        if cfg.owner_id is None:
            return
        month = datetime.now(self._tz()).strftime("%Y-%m")
        for a in self._commands.budget_alerts(str(cfg.owner_id)):
            key = f"{month}:{a['category']}:{a['level']}"
            if key in self._alerted_budgets:  # once per category/level per month
                continue
            self._alerted_budgets.add(key)
            if a["level"] == "over":
                msg = (f"🔴 Orçamento estourado — {a['category']}: "
                       f"R$ {a['spent']:.2f} de R$ {a['amount']:.2f} ({a['pct']:.0f}%).")
            else:
                msg = (f"🟡 Atenção ao orçamento — {a['category']} já em {a['pct']:.0f}% "
                       f"(R$ {a['spent']:.2f} / R$ {a['amount']:.2f}).")
            await self._proactive_send(app, "💰 Orçamento", msg)
        if len(self._alerted_budgets) > 500:
            self._alerted_budgets.clear()

    def _log_notif(self, title: str, body: str = "") -> None:
        """Record a proactive alert in the web notification center too."""
        if self._config.owner_id is None:
            return
        try:
            self._memory.add_notification(str(self._config.owner_id), title, body, "/")
        except Exception:
            log.warning("notification log failed", exc_info=True)

    async def _maybe_send_rain(self, app: Application) -> None:
        cfg = self._config
        if cfg.rain_hour < 0 or cfg.owner_id is None or not cfg.city:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour == cfg.rain_hour and self._last_rain != today:
            self._last_rain = today
            from ...providers import tools
            lang = self._memory.assistant_lang()
            msg = await asyncio.to_thread(tools.rain_tomorrow, cfg.city, lang)
            if msg:
                await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
                self._log_notif(_t(lang, "notif.rain_title"), msg)
                log.info("Sent rain alert.")

    async def _maybe_run_recurring(self, app: Application) -> None:
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if self._last_recurring == today:
            return
        self._last_recurring = today
        month = now.strftime("%Y-%m")
        for r in self._memory.due_recurring(now.day, month):
            self._memory.add_expense(
                r["user_id"], r["amount"], r["description"], r["category"]
            )
            self._memory.mark_recurring_logged(r["id"], month)
            if str(r["user_id"]).isdigit():
                await self._bot_send(
                    app.bot, int(r["user_id"]),
                    f"🔁 Lancei sua assinatura: R$ {r['amount']:.2f} em {r['description']}.",
                    self._quick_kb(),
                )
            log.info("Logged recurring expense #%s", r["id"])

    async def _maybe_habit_nudge(self, app: Application) -> None:
        cfg = self._config
        if cfg.habit_nudge_hour < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour != cfg.habit_nudge_hour or self._last_habit_nudge == today:
            return
        self._last_habit_nudge = today
        uid = str(cfg.owner_id)
        today_s = now.date().strftime("%Y-%m-%d")
        pend = [
            h["name"] for h in self._memory.list_habits(uid)
            if today_s not in self._memory.habit_days(h["id"])
        ]
        if pend:
            msg = "👀 Ainda falta hoje: " + ", ".join(pend) + ".\nMarque com /feito <nome>."
            await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
            log.info("Sent habit nudge.")

    async def _maybe_nudge(self, app: Application) -> None:
        """Proactive open-loops nudge: overdue/due tasks + upcoming subscriptions.
        Deterministic (no LLM), fired once/day at cfg.nudge_hour, and only when
        something is actually slipping — silence when the day is clean."""
        cfg = self._config
        if getattr(cfg, "nudge_hour", -1) < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour != cfg.nudge_hour or self._last_nudge == today:
            return
        self._last_nudge = today
        msg = self._commands.nudge_text(str(cfg.owner_id))
        if not msg:
            return
        await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
        try:  # mirror into the web notification center + push to devices
            from ...providers import push
            await asyncio.to_thread(push.send_push, cfg, self._memory,
                                    "👋 E.V. te cobrando", msg, "/", str(cfg.owner_id))
        except Exception:
            pass
        log.info("Sent proactive open-loops nudge.")

    async def _maybe_insight(self, app: Application) -> None:
        """Continuous learning (participative): once/day, E.V. shares ONE freshly
        learned pattern about the user and asks a follow-up. Deterministic mining
        (no LLM); each pattern is persisted so it's shared only once."""
        cfg = self._config
        if getattr(cfg, "learn_hour", -1) < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour != cfg.learn_hour or self._last_insight == today:
            return
        self._last_insight = today
        uid = str(cfg.owner_id)
        patterns = self._commands.learned_patterns(uid)
        fresh = next((p for p in patterns if not self._memory.learned_seen(uid, p["key"])), None)
        if not fresh:
            return
        self._memory.add_learned(uid, fresh["key"], fresh["text"])
        msg = "🧠 " + fresh["text"] + "\n\n" + fresh.get("question", "")
        await self._bot_send(app.bot, cfg.owner_id, msg.strip(), self._quick_kb())
        try:
            from ...providers import push
            await asyncio.to_thread(push.send_push, cfg, self._memory,
                                    "🧠 E.V. aprendeu algo sobre você", fresh["text"],
                                    "/", uid)
        except Exception:
            pass
        log.info("Shared a learned pattern (%s).", fresh["key"])

    async def cmd_padroes(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        """On demand: what E.V. has learned about the user."""
        if not self._authorized(update):
            return
        await self._cmd_out(update, self._commands.learned_text(
            str(update.effective_user.id)))

    async def _maybe_run_automations(self, app: Application) -> None:
        """Evaluate the user's automations ('quando X, faça Y') and run those that
        fire. Deterministic triggers (no LLM) → cheap and reliable."""
        cfg = self._config
        if cfg.owner_id is None:
            return
        from ...core import automations as au
        now = datetime.now(self._tz())
        owner = str(cfg.owner_id)
        for a in self._memory.list_automations(owner, only_enabled=True):
            try:
                state = a["state"]
                fired, extra = False, None
                if a["trig"] == "time":
                    if au.time_due(a["trig_cfg"], now, state.get("last")):
                        fired = True
                        state["last"] = now.date().isoformat()
                elif a["trig"] == "expense_over":
                    new = self._memory.expenses_after_id(owner, int(state.get("last_id", 0)))
                    if new:
                        state["last_id"] = new[-1]["id"]
                        extra = next((e for e in new if au.expense_matches(a["trig_cfg"], e)), None)
                        fired = extra is not None
                elif a["trig"] == "task_overdue":
                    loops = self._commands.open_loops(owner)
                    if loops["overdue"] and state.get("last") != now.date().isoformat():
                        fired, extra = True, loops["overdue"]
                        state["last"] = now.date().isoformat()
                if fired:
                    await self._run_automation_action(app, a, extra)
                self._memory.set_automation_state(a["id"], state)
            except Exception:
                log.exception("automation %s failed", a.get("id"))

    async def _run_automation_action(self, app: Application, a: dict, extra) -> None:
        cfg = self._config
        owner = str(cfg.owner_id)
        act, ac = a["act"], a["act_cfg"]
        if act == "notify":
            msg = "🤖 " + (ac.get("message") or a["name"])
            if a["trig"] == "expense_over" and isinstance(extra, dict):
                msg += f"\n(R$ {float(extra.get('amount', 0)):.2f} em {extra.get('description', '')})"
        elif act == "command":
            name = (ac.get("command") or "").lstrip("/").split()[0] if ac.get("command") else ""
            out = self._commands.run(owner, name, "") if name in self._commands.runnable() else None
            msg = "🤖 " + a["name"] + (("\n\n" + out) if out else "")
        elif act == "reschedule":
            from datetime import timedelta
            today = datetime.now(self._tz()).date().isoformat()
            tomorrow = (datetime.now(self._tz()).date() + timedelta(days=1)).isoformat()
            n = 0
            for t in self._memory.open_tasks(owner):
                due = t.get("due")
                if due and due[:10] < today:
                    self._memory.update_task(owner, t["id"], due=tomorrow)
                    n += 1
            msg = f"🤖 {a['name']}: remarquei {n} tarefa(s) atrasada(s) pra amanhã."
        elif act == "play":
            msg = await asyncio.to_thread(self._auto_play, a, ac)
        else:
            return
        await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
        try:
            from ...providers import push
            await asyncio.to_thread(push.send_push, cfg, self._memory,
                                    "🤖 Automação", msg[:200], "/", owner)
        except Exception:
            pass
        log.info("Ran automation #%s (%s → %s).", a.get("id"), a["trig"], act)

    def _auto_play(self, a: dict, ac: dict) -> str:
        """Play a playlist/track on Spotify for a 'play' automation (sync)."""
        from ...providers import spotify as sp
        tok = sp.access_token(self._memory, self._config)
        if not tok:
            return f"🤖 {a['name']} — mas o Spotify não está conectado."
        if ac.get("playlist"):
            uri = sp.find_playlist(tok, ac["playlist"])
            body = {"context_uri": uri} if uri else None
        else:
            uri = sp.first_track_uri(tok, ac.get("query", ""))
            body = {"uris": [uri]} if uri else None
        if not body:
            return f"🤖 {a['name']} — não achei o que tocar."
        try:
            r = sp.api("PUT", "/me/player/play", tok, json=body)
        except Exception:
            return f"🤖 {a['name']} — falha ao tocar."
        if r.status_code == 404:
            return f"🤖 {a['name']} — sem dispositivo ativo (abre o Spotify)."
        return f"🤖 {a['name']}"

    async def cmd_automacoes(self, update: Update, _c: ContextTypes.DEFAULT_TYPE) -> None:
        """List the user's automations."""
        if not self._authorized(update):
            return
        await self._cmd_out(update, self._commands.automacoes(str(update.effective_user.id)))

    async def cmd_automacaorm(self, update: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
        """Delete an automation by id: /automacaorm 3."""
        if not self._authorized(update):
            return
        await self._cmd_out(update, self._commands.automacao_rm(
            str(update.effective_user.id), self._args(c).strip()))

    async def _maybe_monthly_report(self, app: Application) -> None:
        cfg = self._config
        if cfg.monthly_report_day < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        month = now.strftime("%Y-%m")
        if (
            now.day != cfg.monthly_report_day
            or now.hour != cfg.monthly_report_hour
            or self._last_monthly == month
        ):
            return
        self._last_monthly = month
        uid = str(cfg.owner_id)
        # Fires at the start of a month → summarize the month that just ended.
        report = self._commands.relatorio(uid, offset=-1)
        insight = await self._brain.ask(
            "Você é a E.V. Comente em 1-2 frases este relatório do mês (padrões, "
            "dicas gentis). Breve e humano, em português.",
            report,
        )
        text = report + (("\n\n🧠 " + insight) if insight else "")
        await self._bot_send(app.bot, cfg.owner_id, text, self._quick_kb())
        log.info("Sent monthly report.")

    async def _watch_loop(self, app: Application) -> None:
        import hashlib
        from ...providers import tools

        while True:
            try:
                for w in self._memory.all_watches():
                    if not str(w["user_id"]).isdigit():
                        continue
                    try:
                        text = await asyncio.to_thread(tools.fetch_text, w["url"])
                    except Exception:
                        continue
                    if w["keyword"]:
                        present = w["keyword"].lower() in text.lower()
                        if present and w["state"] != "found":
                            await self._bot_send(
                                app.bot, int(w["user_id"]),
                                f"👁️ '{w['keyword']}' apareceu em {w['url']}",
                                self._quick_kb(),
                            )
                        self._memory.set_watch_state(w["id"], "found" if present else "absent")
                    else:
                        # Normalize away numeric noise (timestamps, view counts,
                        # ad rotations) so only real content changes trigger.
                        norm = re.sub(r"\d+", "", text)
                        norm = re.sub(r"\s+", " ", norm).lower()
                        digest = hashlib.sha256(norm.encode("utf-8", "ignore")).hexdigest()
                        if w["state"] and w["state"] != digest:
                            await self._bot_send(
                                app.bot, int(w["user_id"]),
                                f"👁️ A página mudou: {w['url']}",
                                self._quick_kb(),
                            )
                        self._memory.set_watch_state(w["id"], digest)
            except Exception:
                log.exception("Watch loop error")
            await asyncio.sleep(max(60, self._config.watch_poll_minutes * 60))

    async def _maybe_send_checkin(self, app: Application) -> None:
        cfg = self._config
        if cfg.checkin_hour < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour == cfg.checkin_hour and self._last_checkin != today:
            self._last_checkin = today
            msg = (
                "Oi! Como foi seu dia? Se quiser, registra no diário com "
                "/diario <texto>. E não esquece dos seus hábitos — /habitos."
            )
            await self._bot_send(app.bot, cfg.owner_id, msg, self._quick_kb())
            self._log_notif("👋 Check-in do dia", msg)
            log.info("Sent daily check-in.")

    async def _maybe_send_briefing(self, app: Application) -> None:
        cfg = self._config
        if cfg.briefing_hour < 0 or cfg.owner_id is None:
            return
        now = datetime.now(self._tz())
        today = now.date().isoformat()
        if now.hour == cfg.briefing_hour and self._last_briefing != today:
            self._last_briefing = today
            text = self._commands.daily_briefing(str(cfg.owner_id))
            await self._bot_send(app.bot, cfg.owner_id, text, self._kb_main())
            log.info("Sent daily briefing to owner.")

    async def _loctask_loop(self, app: Application) -> None:
        """Telegram fallback for local-PC task approvals: the web console is
        the primary place to approve, this just makes sure a pending request
        never gets missed if the user isn't looking at the console."""
        while True:
            try:
                if self._config.owner_id is not None:
                    for t in self._memory.unnotified_local_tasks():
                        b = InlineKeyboardButton
                        kb = InlineKeyboardMarkup([[
                            b("✅ Aprovar", callback_data=f"loctask:aprovar:{t['id']}"),
                            b("✖️ Recusar", callback_data=f"loctask:recusar:{t['id']}"),
                        ]])
                        await self._bot_send(
                            app.bot, self._config.owner_id,
                            f"🖥️ A E.V. quer executar no seu computador:\n"
                            f"[{t['kind']}] {t['label']}\n\n"
                            "Isso só roda depois que você aprovar.",
                            kb,
                        )
                        self._memory.mark_local_task_notified(t["id"])
            except Exception:
                log.exception("Local task loop error")
            await asyncio.sleep(20)

    async def _locconfirm_loop(self, app: Application) -> None:
        """Telegram fallback for the SECOND, in-flight confirmation a risky
        browser task (WhatsApp/Instagram) requests right before it sends or
        posts anything — polled faster since the local agent is paused and
        waiting on this decision, not just queued."""
        while True:
            try:
                if self._config.owner_id is not None:
                    for c in self._memory.unnotified_local_confirms():
                        b = InlineKeyboardButton
                        kb = InlineKeyboardMarkup([[
                            b("✅ Confirmar", callback_data=f"locconfirm:aprovar:{c['id']}"),
                            b("✖️ Recusar", callback_data=f"locconfirm:recusar:{c['id']}"),
                        ]])
                        await self._bot_send(
                            app.bot, self._config.owner_id,
                            f"⚠️ Ação de alto risco pausada no seu computador:\n"
                            f"{c['label']}\n\n"
                            "A E.V. só vai continuar (ex: enviar/postar) se você confirmar.",
                            kb,
                        )
                        self._memory.mark_local_confirm_notified(c["id"])
            except Exception:
                log.exception("Local confirm loop error")
            await asyncio.sleep(8)

    async def _reminder_loop(self, app: Application) -> None:
        while True:
            try:
                await self._deliver_due_reminders(app)
                # Roll recurring tasks forward to their next occurrence.
                self._memory.roll_due_tasks(datetime.now(self._tz()))
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
                    sid = self._stash(self._pending_rem, r["text"])
                    await self._bot_send(
                        app.bot, int(r["user_id"]),
                        f"⏰ Lembrete: {r['text']}", self._reminder_kb(sid),
                    )
                    # also push to the web app (works even when it's closed)
                    try:
                        from ...providers import push
                        await asyncio.to_thread(
                            push.send_push, self._config, self._memory,
                            "⏰ Lembrete", r["text"], "/", str(r["user_id"]))
                    except Exception:
                        pass
                    self._advance_reminder(r, due, now)
                    log.info("Delivered reminder #%s", r["id"])
                except Exception:
                    log.exception("Failed to deliver reminder #%s", r["id"])

    def _reminder_kb(self, sid: str) -> InlineKeyboardMarkup:
        b = InlineKeyboardButton
        return InlineKeyboardMarkup([
            [b("✅ Feito", callback_data=f"remdone:{sid}")],
            [b("⏰ +10min", callback_data=f"remsnooze:10:{sid}"),
             b("⏰ +1h", callback_data=f"remsnooze:60:{sid}"),
             b("🌙 Amanhã", callback_data=f"remsnooze:tom:{sid}")],
        ])

    async def _snooze_reminder(self, q, uid: str, action: str) -> None:
        what, _, sid = action.partition(":")
        text = self._pending_rem.get(sid)
        if text is None:
            await q.answer("Esse lembrete expirou. Cria um novo com /lembrete.", show_alert=True)
            return
        now = datetime.now(self._tz())
        if what == "tom":
            nxt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            label = nxt.strftime("%d/%m às %H:%M")
        else:
            mins = int(what)
            nxt = now + timedelta(minutes=mins)
            label = f"em {mins}min"
        self._memory.add_reminder(uid, text, nxt.isoformat())
        self._pending_rem.pop(sid, None)
        await q.answer("Adiado ⏰")
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await q.message.reply_text(
            f"⏰ Ok, te lembro de novo {label}: {text}", reply_markup=self._quick_kb()
        )

    def _advance_reminder(self, r: dict, due: datetime, now: datetime) -> None:
        """Recurring -> schedule the next future occurrence; one-off -> mark done."""
        recur = r.get("recur") or ""
        if recur == "monthly":
            nxt = due
            while nxt <= now:  # catch up missed months (day clamped per month)
                nxt = add_months(nxt, 1)
            self._memory.reschedule_reminder(r["id"], nxt.isoformat())
            return
        delta = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(recur)
        if not delta:
            self._memory.mark_reminder_done(r["id"])
            return
        nxt = due
        while nxt <= now:  # catch up past missed occurrences to the future
            nxt += delta
        self._memory.reschedule_reminder(r["id"], nxt.isoformat())
