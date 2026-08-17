"""Dashboard overview, daily briefing, proactive nudges, and deterministic
pattern mining ("continuous learning") — all read-only summaries over the
user's own data."""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from ...providers import tools as tools_mod


class OverviewMixin:
    def daily_briefing(self, user_id: str) -> str:
        parts = ["Bom dia! Aqui vai seu resumo de hoje:"]

        tasks = self._memory.open_tasks(user_id)
        if tasks:
            parts.append("\nTarefas em aberto:")
            parts += [f"- {t['text']}" for t in tasks]

        reminders = self._memory.open_reminders(user_id)
        if reminders:
            parts.append("\nLembretes:")
            for r in reminders:
                when = ""
                if r["when_iso"]:
                    try:
                        when = " (" + datetime.fromisoformat(r["when_iso"]).strftime("%d/%m %H:%M") + ")"
                    except Exception:
                        pass
                parts.append(f"- {r['text']}{when}")

        if self._config.google_authorized():
            parts.append("\nAgenda:")
            parts.append(
                tools_mod.calendar_upcoming(
                    self._config, self._config.default_account, max_results=5
                )
            )

        if self._config.imap_ready():
            unread = tools_mod.inbox_summary(self._config, "", "", max_results=5)
            low = unread.lower()
            if ("nenhum" not in low and "não consegui" not in low
                    and "não configurada" not in low):
                parts.append("\nE-mails não lidos:")
                parts.append(unread)

        try:
            tz = ZoneInfo(self._config.timezone) if ZoneInfo else None
            mmdd = datetime.now(tz).strftime("%m-%d")
        except Exception:
            mmdd = datetime.now(timezone.utc).strftime("%m-%d")
        bdays = self._memory.birthdays_on(user_id, mmdd)
        if bdays:
            parts.append("\nAniversários hoje:")
            parts += [f"- {p['name']} 🎂" for p in bdays]

        if len(parts) == 1:
            parts.append("Nada na lista. Dia livre — aproveita!")

        if self._config.city:
            parts.append("\nClima:")
            parts.append(tools_mod.weather(self._config.city))
        if self._config.news_topic:
            parts.append("\nNotícias:")
            parts.append(
                tools_mod.news(
                    self._config.news_topic,
                    max_results=3,
                    tavily_key=getattr(self._config, "tavily_api_key", ""),
                )
            )
            tab = tools_mod.tabnews(3)
            if tab:
                parts.append("\nTabNews (tech):")
                parts.append(tab)
        return "\n".join(parts)

    def overview(self, user_id: str) -> dict:
        """One-shot summary of everything in E.V. for the home dashboard (DB only,
        no network — fast). Counts + short previews per domain."""
        try:
            tz = ZoneInfo(self._config.timezone) if ZoneInfo else None
            now = datetime.now(tz)
        except Exception:
            now = datetime.now(timezone.utc)
        from datetime import timedelta
        today = now.strftime("%Y-%m-%d")
        tasks = self._memory.open_tasks(user_id)
        rems = self._memory.open_reminders(user_id)
        label, start, _end = self._month_bounds(0)
        exps = self._memory.expenses_since(user_id, start)
        bycat: dict = {}
        for e in exps:
            bycat[e["category"]] = bycat.get(e["category"], 0) + (e["amount"] or 0)
        top = max(bycat.items(), key=lambda x: x[1])[0] if bycat else None
        # last-7-days expense series (for the sparkline)
        _wd = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
        days7 = [(now.date() - timedelta(days=i)) for i in range(6, -1, -1)]
        ex7 = self._memory.expenses_since(user_id, days7[0].isoformat())
        byday = {d.isoformat(): 0.0 for d in days7}
        for e in ex7:
            k = (e.get("created") or "")[:10]
            if k in byday:
                byday[k] += (e["amount"] or 0)
        exp_day = [{"label": _wd[d.weekday()], "value": round(byday[d.isoformat()], 2)}
                   for d in days7]
        habits = self._memory.list_habits(user_id)
        hdone = {h["id"]: (today in self._memory.habit_days(h["id"])) for h in habits}
        pending = [h["name"] for h in habits if not hdone[h["id"]]]
        goals = self._memory.list_goals(user_id)
        return {
            "greeting": self.spoken_status(user_id),
            "tasks": {"count": len(tasks),
                      "items": [{"id": t["id"], "text": t["text"]} for t in tasks[:5]]},
            "reminders": {"count": len(rems),
                          "items": [{"id": r["id"], "text": r["text"],
                                     "when": r.get("when_iso") or r.get("when") or "",
                                     "recur": r.get("recur") or ""}
                                    for r in rems[:4]]},
            "expenses": {"total": round(sum(e["amount"] or 0 for e in exps), 2),
                         "top": top, "label": label, "day": exp_day},
            "habits": {"pending": pending[:5], "done": len(habits) - len(pending),
                       "total": len(habits),
                       "items": [{"id": h["id"], "name": h["name"], "done": hdone[h["id"]]}
                                 for h in habits[:8]]},
            "goals": [{"name": g["name"],
                       "pct": (round(g["saved"] / g["target"] * 100) if g["target"] else 0)}
                      for g in goals[:3]],
            "health": self._memory.health_day(user_id, today),
            "counts": {
                "memories": len(self._memory.list_facts(user_id)),
                "kb": len(self._memory.list_sources(user_id)),
                "links": len(self._memory.list_links(user_id)),
                "journal": len(self._memory.recent_journal(user_id, 999)),
                "places": len(self._memory.list_places(user_id)),
                "subs": len(self._memory.list_recurring(user_id)),
                "automations": len(self._memory.list_automations(user_id)),
            },
        }

    def modo(self, user_id: str, argstr: str = "") -> str:
        """Liga/desliga o modo foco. argstr: on/off (vazio = alterna)."""
        arg = (argstr or "").strip().lower()
        cur = self._memory.get_setting("serious_mode") == "1"
        if arg in ("on", "ligar", "ativar", "serio", "sério"):
            on = True
        elif arg in ("off", "desligar", "desativar", "normal"):
            on = False
        else:
            on = not cur
        self._memory.set_setting("serious_mode", "1" if on else "0")
        return ("🔴 Modo foco ativado. Foco total."
                if on else "Modo foco desativado. De volta ao normal.")

    def budget_alerts(self, user_id: str, warn_pct: int = 80) -> list:
        """Budgets at/over threshold this month. level='over' (>=100%) or
        'warn' (>=warn_pct). Empty if all healthy or no budgets."""
        _, since, _ = self._month_bounds(0)
        out = []
        for b in self._memory.list_budgets(user_id):
            amount = b.get("amount") or 0
            if amount <= 0:
                continue
            spent = self._memory.category_total_since(user_id, b["category"], since)
            pct = spent / amount * 100
            if pct >= 100:
                lvl = "over"
            elif pct >= warn_pct:
                lvl = "warn"
            else:
                continue
            out.append({"category": b["category"], "spent": round(spent, 2),
                        "amount": amount, "pct": round(pct), "level": lvl})
        return out

    def spoken_status(self, user_id: str) -> str:
        """Short, TTS-friendly boot briefing (deterministic, no LLM): time-of-day
        greeting + today's open loops + birthdays. Written to be HEARD."""
        try:
            tz = ZoneInfo(self._config.timezone) if ZoneInfo else None
            now = datetime.now(tz)
        except Exception:
            now = datetime.now(timezone.utc)
        saud = "Bom dia" if now.hour < 12 else ("Boa tarde" if now.hour < 18 else "Boa noite")
        parts = [f"{saud}, Ryan."]
        nt = len(self._memory.open_tasks(user_id))
        nr = len(self._memory.open_reminders(user_id))
        if nt or nr:
            bits = []
            if nt:
                bits.append(f"{nt} tarefa" + ("s" if nt != 1 else ""))
            if nr:
                bits.append(f"{nr} lembrete" + ("s" if nr != 1 else ""))
            parts.append("Hoje você tem " + " e ".join(bits) + ".")
        else:
            parts.append("Sua agenda está tranquila.")
        try:
            mmdd = now.strftime("%m-%d")
            bdays = self._memory.birthdays_on(user_id, mmdd)
            if bdays:
                parts.append("Hoje é aniversário de " + ", ".join(p["name"] for p in bdays) + ".")
        except Exception:
            pass
        parts.append("Sistemas online. Tudo pronto pra você.")
        return " ".join(parts)

    def open_loops(self, user_id: str, now=None) -> dict:
        """Deterministic 'things slipping' detector for the proactive nudge:
        overdue tasks, tasks due today, and subscriptions charging soon.
        Cheap (no LLM) and safe to call often."""
        now = now or datetime.now(timezone.utc)
        today = now.date()
        overdue: list[str] = []
        due_today: list[str] = []
        for t in self._memory.open_tasks(user_id):
            raw = t.get("due")
            if not raw:
                continue
            try:
                d = datetime.fromisoformat(raw)
            except (ValueError, TypeError):
                continue
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            if d.date() < today:
                overdue.append(t["text"])
            elif d.date() == today:
                due_today.append(t["text"])
        subs: list[str] = []
        for r in self._memory.list_recurring(user_id):
            day = r.get("day")
            if not day:
                continue
            days_until = (int(day) - today.day) % 31  # heads-up within 2 days
            if 0 <= days_until <= 2:
                subs.append(f"{r['description']} (R$ {r['amount']:.2f}, dia {day})")
        return {"overdue": overdue, "due_today": due_today, "subs": subs}

    def nudge_text(self, user_id: str, now=None) -> str:
        """Human-readable proactive nudge, or '' when nothing is slipping."""
        loops = self.open_loops(user_id, now)
        if not (loops["overdue"] or loops["due_today"] or loops["subs"]):
            return ""
        parts = ["👋 Ryan, deixa eu te cobrar algumas coisas:"]
        if loops["overdue"]:
            parts.append("\n⏰ Tarefas atrasadas:")
            parts += [f"- {t}" for t in loops["overdue"][:10]]
        if loops["due_today"]:
            parts.append("\n📌 Vence hoje:")
            parts += [f"- {t}" for t in loops["due_today"][:10]]
        if loops["subs"]:
            parts.append("\n💳 Assinatura debitando em breve:")
            parts += [f"- {s}" for s in loops["subs"][:10]]
        parts.append("\nConcluir: /concluir <nome>. Quer que eu te ajude com alguma?")
        return "\n".join(parts)

    # --- continuous learning (deterministic pattern mining) ----------------

    _WD_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

    def learned_patterns(self, user_id: str, now=None) -> list[dict]:
        """Deterministically mine the user's own data for patterns worth surfacing.
        No LLM (cheap, testable). Each item: {key, text, question}. Empty until
        there's enough history — E.V. only speaks when a signal is real."""
        from datetime import timedelta
        now = now or self._now()
        today = now.date()
        out: list[dict] = []

        # 1) Habit weekday-skip: an established habit that keeps failing on one weekday.
        window = [today - timedelta(days=i) for i in range(1, 29)]  # last 4 weeks
        for h in self._memory.list_habits(user_id):
            days = self._memory.habit_days(h["id"])
            if len(days) < 8:  # not yet an established habit
                continue
            per_tot: dict[int, int] = {}
            per_done: dict[int, int] = {}
            for d in window:
                wd = d.weekday()
                per_tot[wd] = per_tot.get(wd, 0) + 1
                if d.isoformat() in days:
                    per_done[wd] = per_done.get(wd, 0) + 1
            overall = sum(1 for d in window if d.isoformat() in days) / len(window)
            worst, worst_rate = None, 1.0
            for wd, tot in per_tot.items():
                if tot < 3:
                    continue
                rate = per_done.get(wd, 0) / tot
                if rate < worst_rate:
                    worst, worst_rate = wd, rate
            if worst is not None and worst_rate <= 0.34 and overall >= 0.4:
                name = self._WD_PT[worst]
                suffix = "s-feiras" if worst < 5 else "s"
                out.append({
                    "key": f"habit-skip:{h['id']}:{worst}",
                    "text": f"Notei um padrão: você quase sempre pula '{h['name']}' "
                            f"às {name}{suffix}.",
                    "question": "Quer que eu te dê um empurrãozinho nesse dia?",
                })

        # 2) Spending: already spent more on a category than ALL of last month.
        label, cur_start, _cur_end = self._month_bounds(0)
        _, prev_start, prev_end = self._month_bounds(-1)

        def _by_cat(rows):
            agg: dict[str, float] = {}
            for e in rows:
                agg[e["category"]] = agg.get(e["category"], 0.0) + (e["amount"] or 0)
            return agg

        cur = _by_cat(self._memory.expenses_since(user_id, cur_start))
        prev = _by_cat(self._memory.expenses_between(user_id, prev_start, prev_end))
        for cat, tot in cur.items():
            if tot >= 50 and prev.get(cat, 0) > 0 and tot > prev[cat]:
                out.append({
                    "key": f"spend-over:{label}:{cat}",
                    "text": f"Você já gastou R$ {tot:.0f} em '{cat}' este mês — mais "
                            f"que os R$ {prev[cat]:.0f} do mês passado inteiro.",
                    "question": "Quer definir um orçamento pra essa categoria?",
                })
        return out

    def learned_text(self, user_id: str) -> str:
        """On-demand view of what E.V. has learned about the user."""
        items = self._memory.list_learned(user_id, 15)
        if items:
            return "🧠 O que já aprendi sobre você:\n" + "\n".join(
                "- " + i["text"] for i in items)
        fresh = self.learned_patterns(user_id)
        if fresh:
            return "🧠 Comecei a notar:\n" + "\n".join(
                "- " + p["text"] for p in fresh[:8])
        return "Ainda estou te conhecendo — em alguns dias começo a notar seus padrões. 🌱"
