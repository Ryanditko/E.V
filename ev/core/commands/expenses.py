"""Expenses: add, list, delete, edit, monthly report."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..i18n import plural as _plural
from ..i18n import t as _t


class ExpensesMixin:
    def gasto(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        tokens = argstr.strip().split()
        if not tokens:
            return _t(lang, "exp.usage")
        try:
            amount = float(tokens[0].replace(",", "."))
        except ValueError:
            return _t(lang, "exp.invalid_amount")
        rest = tokens[1:]
        category = "geral"
        tags = [t for t in rest if t.startswith("#") and len(t) > 1]
        if tags:
            category = tags[0][1:].lower()
            rest = [t for t in rest if not (t.startswith("#") and len(t) > 1)]
        desc = " ".join(rest).strip() or _t(lang, "exp.no_desc")
        self._memory.add_expense(user_id, amount, desc, category)
        msg = _t(lang, "exp.registered", amount=f"{amount:.2f}", desc=desc, category=category)
        # Budget alert (if a limit is set for this category).
        budget = self._memory.get_budget(user_id, category)
        if budget:
            _, since, _ = self._month_bounds(0)
            spent = self._memory.category_total_since(user_id, category, since)
            pct = spent / budget * 100 if budget else 0
            if pct >= 100:
                alert = _t(lang, "exp.budget_over", category=category,
                           spent=f"{spent:.2f}", budget=f"{budget:.2f}")
                msg += _t(lang, "exp.budget_over_line", alert=alert)
                self._memory.add_notification(user_id, _t(lang, "exp.notif_over_title"), alert)
            elif pct >= 80:
                alert = _t(lang, "exp.budget_warn", pct=f"{pct:.0f}", category=category,
                           spent=f"{spent:.2f}", budget=f"{budget:.2f}")
                msg += _t(lang, "exp.budget_warn_line", alert=alert)
                self._memory.add_notification(user_id, _t(lang, "exp.notif_warn_title"), alert)
        return msg

    def gastos(self, user_id: str, argstr: str = "") -> str:
        lang = self._memory.assistant_lang()
        _, since, _ = self._month_bounds(0)
        items = self._memory.expenses_since(user_id, since)
        if not items:
            return _t(lang, "exp.list_empty")
        total = sum(i["amount"] for i in items)
        by: dict[str, float] = {}
        for i in items:
            by[i["category"]] = by.get(i["category"], 0) + i["amount"]
        lines = [_t(lang, "exp.list_title", total=f"{total:.2f}",
                    count=_plural(lang, "count.entries", len(items)))]
        for cat, v in sorted(by.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: R$ {v:.2f}")
        lines.append(_t(lang, "exp.recent_header"))
        for i in items[-10:]:
            lines.append(f"#{i['id']} R$ {i['amount']:.2f} {i['description']} ({i['category']})")
        lines.append(_t(lang, "exp.list_footer"))
        return "\n".join(lines)

    def gastorm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        since = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        it, err = self._pick(self._memory.expenses_since(user_id, since),
                             argstr, "description", _t(lang, "exp.pick"), lang)
        if err:
            return err
        self._memory.delete_expense(user_id, it["id"])
        return _t(lang, "exp.deleted", desc=it["description"], amount=f"{it['amount']:.2f}")

    def gastoeditar(self, user_id: str, argstr: str) -> str:
        """Edit an expense by id or name: '<nome/id> | <valor> [descrição] [#cat]'."""
        lang = self._memory.assistant_lang()
        alvo, _, resto = argstr.partition("|")
        since = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        it, err = self._pick(self._memory.expenses_since(user_id, since),
                             alvo, "description", _t(lang, "exp.pick"), lang)
        if err:
            return err
        toks = resto.split()
        if not toks:
            return _t(lang, "exp.edit_usage")
        cat = next((t[1:] for t in toks if t.startswith("#") and len(t) > 1), None)
        toks = [t for t in toks if not t.startswith("#")]
        amount = None
        if toks:
            first = toks[0].replace(",", ".")
            try:
                amount = float(first)
                toks = toks[1:]
            except ValueError:
                pass
        desc = " ".join(toks).strip() or None
        if amount is None and desc is None and cat is None:
            return _t(lang, "exp.edit_nothing")
        self._memory.update_expense(user_id, it["id"], amount=amount,
                                    description=desc, category=cat)
        parts = []
        if amount is not None:
            parts.append(f"R$ {amount:.2f}")
        if desc:
            parts.append(desc)
        if cat:
            parts.append(f"#{cat}")
        return _t(lang, "exp.updated", desc=it["description"], parts=" · ".join(parts))

    def relatorio(self, user_id: str, offset: int = 0) -> str:
        """Financial report for a calendar month, by category vs budget.
        offset 0 = current month (on-demand default), -1 = previous month."""
        lang = self._memory.assistant_lang()
        label, start_iso, end_iso = self._month_bounds(offset)
        items = self._memory.expenses_between(user_id, start_iso, end_iso)
        if not items:
            return _t(lang, "exp.report_empty", label=label)
        total = sum(i["amount"] for i in items)
        by: dict[str, float] = {}
        for i in items:
            by[i["category"]] = by.get(i["category"], 0) + i["amount"]
        lines = [_t(lang, "exp.report_title", label=label),
                 _t(lang, "exp.report_total", total=f"{total:.2f}",
                    count=_plural(lang, "count.entries", len(items))), ""]
        for cat, v in sorted(by.items(), key=lambda x: -x[1]):
            budget = self._memory.get_budget(user_id, cat)
            vs = _t(lang, "exp.report_budget", budget=f"{budget:.0f}",
                    pct=f"{v / budget * 100:.0f}") if budget else ""
            lines.append(f"- {cat}: R$ {v:.2f}{vs}")
        return "\n".join(lines)
