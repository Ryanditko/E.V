"""Expenses, budgets, and recurring expenses (subscriptions)."""

from __future__ import annotations


class ExpensesMixin:
    def add_expense(
        self, user_id: str, amount: float, description: str, category: str = "geral"
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO expenses (user_id, amount, description, category, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, description, category, self._now()),
        )
        self._conn.commit()
        self.log_activity(user_id, "expense.new", f"{description} (R$ {amount:.0f})", category)
        return int(cur.lastrowid)

    def expenses_since(self, user_id: str, since_iso: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, amount, description, category, created FROM expenses "
            "WHERE user_id = ? AND created >= ? ORDER BY id",
            (user_id, since_iso),
        ).fetchall()
        return [dict(r) for r in rows]

    def expenses_between(self, user_id: str, start_iso: str, end_iso: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT amount, description, category FROM expenses "
            "WHERE user_id = ? AND created >= ? AND created < ? ORDER BY id",
            (user_id, start_iso, end_iso),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_expense(self, user_id: str, expense_id: int) -> bool:
        row = self._conn.execute(
            "SELECT description, category FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        cur = self._conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        )
        self._conn.commit()
        if cur.rowcount and row:
            self.log_activity(user_id, "expense.del", row["description"], row["category"])
        return cur.rowcount > 0

    def category_total_since(self, user_id: str, category: str, since_iso: str) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS t FROM expenses "
            "WHERE user_id = ? AND category = ? AND created >= ?",
            (user_id, category, since_iso),
        ).fetchone()
        return float(row["t"])

    def expenses_after_id(self, user_id: str, after_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, amount, description, category, created FROM expenses "
            "WHERE user_id = ? AND id > ? ORDER BY id", (user_id, after_id)).fetchall()
        return [dict(r) for r in rows]

    def max_expense_id(self, user_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS m FROM expenses WHERE user_id = ?",
            (user_id,)).fetchone()
        return int(row["m"]) if row else 0

    def update_expense(self, u, i, amount=None, description=None, category=None):
        return self._update("expenses", u, i, {"amount": amount, "description": description, "category": category})

    # --- budgets --------------------------------------------------------

    def set_budget(self, user_id: str, category: str, amount: float) -> None:
        self._conn.execute(
            "DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, category)
        )
        self._conn.execute(
            "INSERT INTO budgets (user_id, category, amount, created) VALUES (?, ?, ?, ?)",
            (user_id, category, amount, self._now()),
        )
        self._conn.commit()

    def get_budget(self, user_id: str, category: str) -> float | None:
        row = self._conn.execute(
            "SELECT amount FROM budgets WHERE user_id = ? AND category = ?",
            (user_id, category),
        ).fetchone()
        return float(row["amount"]) if row else None

    def list_budgets(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT category, amount FROM budgets WHERE user_id = ? ORDER BY category",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_budget(self, user_id: str, category: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM budgets WHERE user_id = ? AND category = ?", (user_id, category)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # --- recurring expenses (subscriptions) --------------------------------

    def add_recurring(
        self, user_id: str, amount: float, description: str, category: str, day: int
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO recurring_expenses "
            "(user_id, amount, description, category, day, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, amount, description, category, day, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_recurring(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, amount, description, category, day FROM recurring_expenses "
            "WHERE user_id = ? ORDER BY day, id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_recurring(self, user_id: str, rec_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM recurring_expenses WHERE id = ? AND user_id = ?",
            (rec_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def due_recurring(self, day: int, month_str: str) -> list[dict]:
        """Recurring expenses whose day is today and not yet logged this month."""
        rows = self._conn.execute(
            "SELECT id, user_id, amount, description, category FROM recurring_expenses "
            "WHERE day = ? AND (last_month IS NULL OR last_month != ?)",
            (day, month_str),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_recurring_logged(self, rec_id: int, month_str: str) -> None:
        self._conn.execute(
            "UPDATE recurring_expenses SET last_month = ? WHERE id = ?",
            (month_str, rec_id),
        )
        self._conn.commit()

    def update_recurring(self, u, i, amount=None, description=None, category=None, day=None):
        return self._update("recurring_expenses", u, i, {"amount": amount, "description": description, "category": category, "day": day})
