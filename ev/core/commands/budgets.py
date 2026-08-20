"""Budgets per category."""

from __future__ import annotations

from ..i18n import t as _t


class BudgetsMixin:
    def orcamento(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        tokens = argstr.strip().split()
        if len(tokens) < 2:
            return _t(lang, "bud.usage")
        category = tokens[0].lstrip("#").lower()
        try:
            amount = float(tokens[1].replace(",", "."))
        except ValueError:
            return _t(lang, "bud.invalid_amount")
        self._memory.set_budget(user_id, category, amount)
        return _t(lang, "bud.set", category=category, amount=f"{amount:.2f}")

    def orcamentos(self, user_id: str) -> str:
        lang = self._memory.assistant_lang()
        budgets = self._memory.list_budgets(user_id)
        if not budgets:
            return _t(lang, "bud.none")
        _, since, _ = self._month_bounds(0)
        lines = [_t(lang, "bud.title")]
        for b in budgets:
            spent = self._memory.category_total_since(user_id, b["category"], since)
            pct = spent / b["amount"] * 100 if b["amount"] else 0
            dot = "🔴" if pct >= 100 else "🟡" if pct >= 80 else "🟢"
            lines.append(
                f"{dot} {b['category']}: R$ {spent:.2f} / R$ {b['amount']:.2f} ({pct:.0f}%)"
            )
        lines.append(_t(lang, "bud.footer"))
        return "\n".join(lines)

    def orcamentorm(self, user_id: str, argstr: str) -> str:
        lang = self._memory.assistant_lang()
        cat = argstr.strip().lstrip("#").lower()
        if not cat:
            return _t(lang, "bud.rm_usage")
        ok = self._memory.delete_budget(user_id, cat)
        return _t(lang, "bud.removed", cat=cat) if ok else _t(lang, "bud.not_found", cat=cat)
