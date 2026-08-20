"""Recurring expenses (subscriptions): create/list/delete + due-soon lookup."""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from ..i18n import t as _t


class SubscriptionsMixin:
    def assinatura(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        tokens = argstr.strip().split()
        if len(tokens) < 2:
            return _t(lang, "sub.usage")
        try:
            amount = float(tokens[0].replace(",", "."))
        except ValueError:
            return _t(lang, "sub.invalid_amount")
        rest = tokens[1:]
        category = "assinatura"
        tags = [t for t in rest if t.startswith("#") and len(t) > 1]
        if tags:
            category = tags[0][1:].lower()
            rest = [t for t in rest if not (t.startswith("#") and len(t) > 1)]
        day = self._now().day
        if rest and rest[-1].isdigit() and 1 <= int(rest[-1]) <= 28:
            day = int(rest[-1])
            rest = rest[:-1]
        desc = " ".join(rest).strip() or _t(lang, "sub.default_desc")
        rid = self._memory.add_recurring(user_id, amount, desc, category, day)
        return _t(lang, "sub.created", rid=rid, amount=f"{amount:.2f}", desc=desc, day=day)

    def assinaturas(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        items = self._memory.list_recurring(user_id)
        if not items:
            return _t(lang, "sub.none")
        lines = [_t(lang, "sub.title")]
        for r in items:
            lines.append(_t(lang, "sub.item", id=r["id"], amount=f"{r['amount']:.2f}",
                            desc=r["description"], day=r["day"], category=r["category"]))
        lines.append(_t(lang, "sub.footer"))
        return "\n".join(lines)

    def assinaturarm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        arg = argstr.strip()
        if not arg.isdigit():
            return _t(lang, "sub.rm_usage")
        ok = self._memory.delete_recurring(user_id, int(arg))
        return _t(lang, "sub.removed", arg=arg) if ok else _t(lang, "sub.not_found", arg=arg)

    def subscriptions_due(self, user_id: str, days_ahead: int = 2) -> list:
        """Recurring charges (assinaturas) whose due-day falls within the next
        `days_ahead` days — a heads-up BEFORE the charge lands. Empty if none."""
        try:
            tz = ZoneInfo(self._config.timezone) if ZoneInfo else None
            now = datetime.now(tz)
        except Exception:
            now = datetime.now(timezone.utc)
        today = now.day
        import calendar as _cal
        last_day = _cal.monthrange(now.year, now.month)[1]
        out = []
        for r in self._memory.list_recurring(user_id):
            d = r.get("day") or 0
            if not d:
                continue
            # days until the charge, clamping a day set past month-end to the last day
            due = min(d, last_day)
            delta = due - today
            if 0 < delta <= days_ahead:
                out.append({"id": r["id"], "description": r["description"],
                            "amount": r["amount"], "day": due, "days_until": delta})
        return out
