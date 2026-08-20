"""Reminders and calendar view (recurring reminders + Google Calendar)."""

from __future__ import annotations

from datetime import datetime, timedelta

from ...providers import tools as tools_mod
from ..i18n import t as _t
from ..timeparse import add_months, parse_when


class RemindersCalendarMixin:
    def lembrete(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        argstr = argstr.strip()
        if not argstr:
            return _t(lang, "rem.usage")
        when, text = parse_when(argstr, self._now())
        if when is None:
            return _t(lang, "rem.bad_time")
        if not text.strip():
            return _t(lang, "rem.missing_text")
        rid = self._memory.add_reminder(user_id, text.strip(), when.isoformat())
        return _t(lang, "rem.created", rid=rid,
                  when=when.strftime('%d/%m %H:%M'), text=text.strip())

    def rotina(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        tokens = argstr.strip().split()
        if len(tokens) < 3:
            return _t(lang, "rem.routine_usage")
        kw = tokens[0].lower()
        now = self._now()
        if kw in ("diario", "diária", "diaria", "diariamente"):
            recur, label = "daily", _t(lang, "rem.label_daily")
        elif kw in ("semanal", "semana", "semanalmente"):
            recur, label = "weekly", _t(lang, "rem.label_weekly")
        elif kw in ("mensal", "mensalmente", "mes", "mês", "monthly"):
            recur = "monthly"
        else:
            return _t(lang, "rem.recur_invalid")

        if recur == "monthly":
            # /rotina mensal <dia> <HH:MM> <texto>
            if len(tokens) < 4 or not tokens[1].isdigit():
                return _t(lang, "rem.monthly_usage")
            day = int(tokens[1])
            if not 1 <= day <= 31:
                return _t(lang, "rem.invalid_day")
            time_tok, text = tokens[2], " ".join(tokens[3:]).strip()
        else:
            time_tok, text = tokens[1], " ".join(tokens[2:]).strip()

        try:
            hm = datetime.strptime(time_tok, "%H:%M")
        except ValueError:
            return _t(lang, "rem.invalid_time")
        if not text:
            return _t(lang, "rem.routine_missing_text")

        if recur == "monthly":
            first = self._monthly_first(now, day, hm.hour, hm.minute)
            label = _t(lang, "rem.label_monthly_day", day=day)
        else:
            step = timedelta(days=1) if recur == "daily" else timedelta(days=7)
            first = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
            if first <= now:
                first += step

        rid = self._memory.add_reminder(user_id, text, first.isoformat(), recur)
        return _t(lang, "rem.routine_created", rid=rid, label=label, time=time_tok, text=text)

    @staticmethod
    def _clamp_day(dt: datetime, day: int) -> datetime:
        """Set dt's day to `day`, clamped to the last valid day of dt's month."""
        if dt.month == 12:
            last = 31
        else:
            last = (dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)).day
        return dt.replace(day=min(day, last))

    @staticmethod
    def _monthly_first(now: datetime, day: int, hour: int, minute: int) -> datetime:
        """First future occurrence of a monthly reminder on `day` at hour:minute."""
        base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        cand = RemindersCalendarMixin._clamp_day(base.replace(day=1), day)
        if cand <= now:
            cand = RemindersCalendarMixin._clamp_day(add_months(base.replace(day=1), 1), day)
        return cand

    def calendario(self, user_id: str) -> str:
        """Agenda view: reminders grouped by day (+ Google Calendar if connected)."""
        lang = self._memory.assistant_lang()
        dated = []
        for r in self._memory.open_reminders(user_id):
            if r["when_iso"]:
                try:
                    dated.append((datetime.fromisoformat(r["when_iso"]), r))
                except Exception:
                    pass
        dated.sort(key=lambda x: x[0])
        lines = [_t(lang, "rem.cal_title")]
        if not dated:
            lines.append(_t(lang, "rem.cal_empty"))
        else:
            current = None
            for dt, r in dated:
                day = f"{dt.strftime('%d/%m')} ({_t(lang, f'cal.wd.{dt.weekday()}')})"
                if day != current:
                    current = day
                    lines.append(f"\n📌 {day}")
                recur = " 🔁" if (r.get("recur")) else ""
                lines.append(f"  {dt.strftime('%H:%M')} — {r['text']}{recur}")
        if self._config.google_authorized():
            lines.append("\n" + _t(lang, "rem.google_cal"))
            lines.append(
                tools_mod.calendar_upcoming(self._config, self._config.default_account, 5, lang=lang)
            )
        return "\n".join(lines)

    def cancelar(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        it, err = self._pick(self._memory.open_reminders(user_id), argstr, "text",
                             _t(lang, "rem.pick_reminder"), lang)
        if err:
            return err
        self._memory.cancel_reminder(user_id, it["id"])
        return _t(lang, "rem.canceled", text=it["text"])

    def lembreteeditar(self, user_id: str, argstr: str) -> str:
        """Edit a reminder by id or name: '<nome/id> | <novo texto> [| <novo tempo>]'."""
        lang = self._memory.assistant_lang()
        alvo, _, resto = argstr.partition("|")
        it, err = self._pick(self._memory.open_reminders(user_id), alvo, "text",
                             _t(lang, "rem.pick_reminder"), lang)
        if err:
            return err
        novo, _, quando = resto.partition("|")
        novo = novo.strip()
        when_iso = None
        quando = quando.strip()
        if quando:
            dt = parse_when(quando, self._now())
            if dt:
                when_iso = dt.isoformat()
        if not novo and not when_iso:
            return _t(lang, "rem.edit_usage")
        self._memory.update_reminder(user_id, it["id"], text=(novo or None), when_iso=when_iso)
        extra = _t(lang, "rem.updated_extra",
                   when=when_iso.replace('T', ' ')[:16]) if when_iso else ""
        return _t(lang, "rem.updated", text=(novo or it["text"]), extra=extra)

    def lembretes(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        items = self._memory.open_reminders(user_id)
        if not items:
            return _t(lang, "rem.list_empty")
        marks = {"daily": _t(lang, "rem.mark_daily"),
                 "weekly": _t(lang, "rem.mark_weekly"),
                 "monthly": _t(lang, "rem.mark_monthly")}
        lines = [_t(lang, "rem.list_title")]
        for r in items:
            when = ""
            if r["when_iso"]:
                try:
                    when = " (" + datetime.fromisoformat(r["when_iso"]).strftime("%d/%m %H:%M") + ")"
                except Exception:
                    when = ""
            recur = marks.get(r.get("recur") or "", "")
            lines.append(f"#{r['id']} {r['text']}{when}{recur}")
        lines.append(_t(lang, "rem.list_footer"))
        return "\n".join(lines)
