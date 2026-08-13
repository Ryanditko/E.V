"""Reminders and calendar view (recurring reminders + Google Calendar)."""

from __future__ import annotations

from datetime import datetime, timedelta

from ...providers import tools as tools_mod
from ..timeparse import add_months, parse_when


class RemindersCalendarMixin:
    def lembrete(self, user_id: str, argstr: str) -> str:
        argstr = argstr.strip()
        if not argstr:
            return "Uso: /lembrete <tempo> <texto>\nEx: /lembrete 10m tomar água | /lembrete amanhã 09:00 reunião"
        when, text = parse_when(argstr, self._now())
        if when is None:
            return (
                "Não entendi o horário. Use algo como: 10m, 2h, 1d, "
                "'hoje 18:00', 'amanhã 09:00' ou '25/12 14:30'."
            )
        if not text.strip():
            return "Faltou o texto do lembrete. Ex: /lembrete 10m tomar água"
        rid = self._memory.add_reminder(user_id, text.strip(), when.isoformat())
        return f"Lembrete #{rid} criado para {when.strftime('%d/%m %H:%M')}: {text.strip()}"

    _USO_ROTINA = (
        "Uso: /rotina <diario|semanal|mensal> [dia] <HH:MM> <texto>\n"
        "Ex: /rotina diario 08:00 tomar remédio\n"
        "Ex: /rotina semanal 09:00 revisar metas\n"
        "Ex: /rotina mensal 5 10:00 pagar aluguel  (todo dia 5)"
    )

    def rotina(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if len(tokens) < 3:
            return self._USO_ROTINA
        kw = tokens[0].lower()
        now = self._now()
        if kw in ("diario", "diária", "diaria", "diariamente"):
            recur, label = "daily", "todo dia"
        elif kw in ("semanal", "semana", "semanalmente"):
            recur, label = "weekly", "toda semana"
        elif kw in ("mensal", "mensalmente", "mes", "mês", "monthly"):
            recur = "monthly"
        else:
            return "Recorrência inválida. Use 'diario', 'semanal' ou 'mensal'."

        if recur == "monthly":
            # /rotina mensal <dia> <HH:MM> <texto>
            if len(tokens) < 4 or not tokens[1].isdigit():
                return "Uso mensal: /rotina mensal <dia> <HH:MM> <texto>\nEx: /rotina mensal 5 10:00 pagar aluguel"
            day = int(tokens[1])
            if not 1 <= day <= 31:
                return "Dia do mês inválido (use 1 a 31)."
            time_tok, text = tokens[2], " ".join(tokens[3:]).strip()
        else:
            time_tok, text = tokens[1], " ".join(tokens[2:]).strip()

        try:
            hm = datetime.strptime(time_tok, "%H:%M")
        except ValueError:
            return "Horário inválido. Use HH:MM. Ex: 08:00"
        if not text:
            return "Faltou o texto da rotina."

        if recur == "monthly":
            first = self._monthly_first(now, day, hm.hour, hm.minute)
            label = f"todo dia {day}"
        else:
            step = timedelta(days=1) if recur == "daily" else timedelta(days=7)
            first = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
            if first <= now:
                first += step

        rid = self._memory.add_reminder(user_id, text, first.isoformat(), recur)
        return f"Rotina #{rid} criada ({label} às {time_tok}): {text}"

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

    _WEEKDAYS_PT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

    def calendario(self, user_id: str) -> str:
        """Agenda view: reminders grouped by day (+ Google Calendar if connected)."""
        dated = []
        for r in self._memory.open_reminders(user_id):
            if r["when_iso"]:
                try:
                    dated.append((datetime.fromisoformat(r["when_iso"]), r))
                except Exception:
                    pass
        dated.sort(key=lambda x: x[0])
        lines = ["📅 Sua agenda"]
        if not dated:
            lines.append("Nada agendado. Crie com /lembrete ou /rotina.")
        else:
            current = None
            for dt, r in dated:
                day = f"{dt.strftime('%d/%m')} ({self._WEEKDAYS_PT[dt.weekday()]})"
                if day != current:
                    current = day
                    lines.append(f"\n📌 {day}")
                recur = " 🔁" if (r.get("recur")) else ""
                lines.append(f"  {dt.strftime('%H:%M')} — {r['text']}{recur}")
        if self._config.google_authorized():
            lines.append("\n📆 Google Agenda:")
            lines.append(
                tools_mod.calendar_upcoming(self._config, self._config.default_account, 5)
            )
        return "\n".join(lines)

    def cancelar(self, user_id: str, argstr: str) -> str:
        it, err = self._pick(self._memory.open_reminders(user_id), argstr, "text", "o lembrete")
        if err:
            return err
        self._memory.cancel_reminder(user_id, it["id"])
        return f"Lembrete \"{it['text']}\" cancelado."

    def lembreteeditar(self, user_id: str, argstr: str) -> str:
        """Edit a reminder by id or name: '<nome/id> | <novo texto> [| <novo tempo>]'."""
        alvo, _, resto = argstr.partition("|")
        it, err = self._pick(self._memory.open_reminders(user_id), alvo, "text", "o lembrete")
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
            return "Uso: lembreteeditar <nome ou id> | <novo texto> [| <novo tempo>]"
        self._memory.update_reminder(user_id, it["id"], text=(novo or None), when_iso=when_iso)
        extra = f" (para {when_iso.replace('T', ' ')[:16]})" if when_iso else ""
        return f"Lembrete atualizado: \"{novo or it['text']}\"{extra}"

    def lembretes(self, user_id: str) -> str:
        items = self._memory.open_reminders(user_id)
        if not items:
            return "Você não tem lembretes em aberto."
        marks = {"daily": " [todo dia]", "weekly": " [toda semana]", "monthly": " [todo mês]"}
        lines = ["⏰ Seus lembretes:"]
        for r in items:
            when = ""
            if r["when_iso"]:
                try:
                    when = " (" + datetime.fromisoformat(r["when_iso"]).strftime("%d/%m %H:%M") + ")"
                except Exception:
                    when = ""
            recur = marks.get(r.get("recur") or "", "")
            lines.append(f"#{r['id']} {r['text']}{when}{recur}")
        lines.append("\nCancelar: /cancelar <id>")
        return "\n".join(lines)
