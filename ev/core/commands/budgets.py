"""Budgets per category."""

from __future__ import annotations


class BudgetsMixin:
    def orcamento(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if len(tokens) < 2:
            return "Uso: /orcamento <categoria> <valor>\nEx: /orcamento comida 800"
        category = tokens[0].lstrip("#").lower()
        try:
            amount = float(tokens[1].replace(",", "."))
        except ValueError:
            return "Valor inválido. Ex: /orcamento comida 800"
        self._memory.set_budget(user_id, category, amount)
        return f"💰 Orçamento de '{category}' definido: R$ {amount:.2f}/mês."

    def orcamentos(self, user_id: str) -> str:
        budgets = self._memory.list_budgets(user_id)
        if not budgets:
            return "Nenhum orçamento. Crie com /orcamento <categoria> <valor>."
        _, since, _ = self._month_bounds(0)
        lines = ["💰 Orçamentos do mês:"]
        for b in budgets:
            spent = self._memory.category_total_since(user_id, b["category"], since)
            pct = spent / b["amount"] * 100 if b["amount"] else 0
            dot = "🔴" if pct >= 100 else "🟡" if pct >= 80 else "🟢"
            lines.append(
                f"{dot} {b['category']}: R$ {spent:.2f} / R$ {b['amount']:.2f} ({pct:.0f}%)"
            )
        lines.append("\nApagar: /orcamentorm <categoria>")
        return "\n".join(lines)

    def orcamentorm(self, user_id: str, argstr: str) -> str:
        cat = argstr.strip().lstrip("#").lower()
        if not cat:
            return "Uso: /orcamentorm <categoria>."
        ok = self._memory.delete_budget(user_id, cat)
        return f"Orçamento de '{cat}' removido." if ok else f"Não achei orçamento pra '{cat}'."
