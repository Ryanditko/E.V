"""Storage control — inspect/clear the user's own data, table by table."""

from __future__ import annotations


class StorageMixin:
    # key -> friendly label. Every table here is scoped by user_id (habit_logs
    # cascades from habits). usage_log/settings are NOT user data and excluded.
    DATA_TABLES = (
        ("messages", "conversa"),
        ("facts", "memórias"),
        ("reminders", "lembretes"),
        ("tasks", "tarefas"),
        ("links", "links"),
        ("knowledge", "base de conhecimento"),
        ("expenses", "gastos"),
        ("recurring_expenses", "assinaturas"),
        ("budgets", "orçamentos"),
        ("habits", "hábitos"),
        ("journal", "diário"),
        ("watches", "monitores web"),
        ("flashcards", "flashcards"),
    )
    _DATA_TABLE_NAMES = frozenset(k for k, _ in DATA_TABLES)

    def count_rows(self, table: str, user_id: str) -> int:
        if table not in self._DATA_TABLE_NAMES:
            raise ValueError(f"unknown table {table!r}")
        return int(
            self._conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
        )

    def clear_table(self, table: str, user_id: str) -> int:
        """Delete all of a user's rows in one data table. Returns rows deleted.
        (Table name is validated against a whitelist — no SQL injection.)"""
        if table not in self._DATA_TABLE_NAMES:
            raise ValueError(f"unknown table {table!r}")
        if table == "habits":  # cascade: drop this user's habit logs first
            self._conn.execute(
                "DELETE FROM habit_logs WHERE habit_id IN "
                "(SELECT id FROM habits WHERE user_id = ?)",
                (user_id,),
            )
        cur = self._conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        self._conn.commit()
        return cur.rowcount

    def storage_summary(self, user_id: str) -> list[dict]:
        """[{key, label, count}] for every user-data table."""
        return [
            {"key": k, "label": lbl, "count": self.count_rows(k, user_id)}
            for k, lbl in self.DATA_TABLES
        ]

    def clear_all_user_data(self, user_id: str) -> int:
        """Wipe ALL of the user's data (every table above). Returns total rows."""
        total = sum(self.clear_table(k, user_id) for k, _ in self.DATA_TABLES)
        try:
            self._conn.execute("VACUUM")  # reclaim disk after a big delete
        except Exception:
            pass
        return total
