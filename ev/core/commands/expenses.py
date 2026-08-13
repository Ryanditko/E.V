"""Expenses: add, list, delete, edit, monthly report."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class ExpensesMixin:
    def gasto(self, user_id: str, argstr: str) -> str:
        tokens = argstr.strip().split()
        if not tokens:
            return "Uso: /gasto <valor> <descrição> [#categoria]\nEx: /gasto 50 mercado #casa"
        try:
            amount = float(tokens[0].replace(",", "."))
        except ValueError:
            return "Valor inválido. Ex: /gasto 50 mercado"
        rest = tokens[1:]
        category = "geral"
        tags = [t for t in rest if t.startswith("#") and len(t) > 1]
        if tags:
            category = tags[0][1:].lower()
            rest = [t for t in rest if not (t.startswith("#") and len(t) > 1)]
        desc = " ".join(rest).strip() or "(sem descrição)"
        self._memory.add_expense(user_id, amount, desc, category)
        msg = f"Gasto registrado: R$ {amount:.2f} em {desc} ({category})"
        # Budget alert (if a limit is set for this category).
        budget = self._memory.get_budget(user_id, category)
        if budget:
            _, since, _ = self._month_bounds(0)
            spent = self._memory.category_total_since(user_id, category, since)
            pct = spent / budget * 100 if budget else 0
            if pct >= 100:
                alert = f"Estourou o orçamento de {category}: R$ {spent:.2f} / R$ {budget:.2f}."
                msg += f"\n🔴 {alert}"
                self._memory.add_notification(user_id, "🔴 Orçamento estourado", alert)
            elif pct >= 80:
                alert = f"{pct:.0f}% do orçamento de {category} (R$ {spent:.2f} / R$ {budget:.2f})."
                msg += f"\n🟡 Atenção: {alert}"
                self._memory.add_notification(user_id, "🟡 Orçamento em atenção", alert)
        return msg

    def gastos(self, user_id: str, argstr: str = "") -> str:
        _, since, _ = self._month_bounds(0)
        items = self._memory.expenses_since(user_id, since)
        if not items:
            return "Nenhum gasto registrado neste mês."
        total = sum(i["amount"] for i in items)
        by: dict[str, float] = {}
        for i in items:
            by[i["category"]] = by.get(i["category"], 0) + i["amount"]
        lines = [f"💰 Gastos do mês: R$ {total:.2f} ({len(items)} lançamentos)"]
        for cat, v in sorted(by.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: R$ {v:.2f}")
        lines.append("\nLançamentos recentes:")
        for i in items[-10:]:
            lines.append(f"#{i['id']} R$ {i['amount']:.2f} {i['description']} ({i['category']})")
        lines.append("\nApagar: /gastorm <id>")
        return "\n".join(lines)

    def gastorm(self, user_id: str, argstr: str) -> str:
        since = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        it, err = self._pick(self._memory.expenses_since(user_id, since),
                             argstr, "description", "o gasto")
        if err:
            return err
        self._memory.delete_expense(user_id, it["id"])
        return f"Gasto \"{it['description']}\" (R$ {it['amount']:.2f}) apagado."

    def gastoeditar(self, user_id: str, argstr: str) -> str:
        """Edit an expense by id or name: '<nome/id> | <valor> [descrição] [#cat]'."""
        alvo, _, resto = argstr.partition("|")
        since = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        it, err = self._pick(self._memory.expenses_since(user_id, since),
                             alvo, "description", "o gasto")
        if err:
            return err
        toks = resto.split()
        if not toks:
            return "Uso: gastoeditar <nome ou id> | <novo valor> [descrição] [#cat]"
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
            return "Nada pra mudar. Ex: gastoeditar mercado | 60 pão #casa"
        self._memory.update_expense(user_id, it["id"], amount=amount,
                                    description=desc, category=cat)
        parts = []
        if amount is not None:
            parts.append(f"R$ {amount:.2f}")
        if desc:
            parts.append(desc)
        if cat:
            parts.append(f"#{cat}")
        return f"Gasto \"{it['description']}\" atualizado: " + " · ".join(parts)

    def relatorio(self, user_id: str, offset: int = 0) -> str:
        """Financial report for a calendar month, by category vs budget.
        offset 0 = current month (on-demand default), -1 = previous month."""
        label, start_iso, end_iso = self._month_bounds(offset)
        items = self._memory.expenses_between(user_id, start_iso, end_iso)
        if not items:
            return f"📈 Relatório de {label}: nenhum gasto registrado."
        total = sum(i["amount"] for i in items)
        by: dict[str, float] = {}
        for i in items:
            by[i["category"]] = by.get(i["category"], 0) + i["amount"]
        lines = [f"📈 Relatório de {label}", f"Total: R$ {total:.2f} ({len(items)} lançamentos)", ""]
        for cat, v in sorted(by.items(), key=lambda x: -x[1]):
            budget = self._memory.get_budget(user_id, cat)
            vs = f" · orçamento R$ {budget:.0f} ({v / budget * 100:.0f}%)" if budget else ""
            lines.append(f"- {cat}: R$ {v:.2f}{vs}")
        return "\n".join(lines)
