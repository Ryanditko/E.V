"""Habits with daily logs."""

from __future__ import annotations


class HabitsMixin:
    def add_habit(self, user_id: str, name: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO habits (user_id, name, created) VALUES (?, ?, ?)",
            (user_id, name, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_habits(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name FROM habits WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_habit(self, user_id: str, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, name FROM habits WHERE user_id = ? AND LOWER(name) = LOWER(?)",
            (user_id, name),
        ).fetchone()
        return dict(row) if row else None

    def log_habit(self, habit_id: int, day: str) -> bool:
        """Mark a habit done on `day` (YYYY-MM-DD). Returns False if already logged."""
        exists = self._conn.execute(
            "SELECT 1 FROM habit_logs WHERE habit_id = ? AND day = ?", (habit_id, day)
        ).fetchone()
        if exists:
            return False
        self._conn.execute(
            "INSERT INTO habit_logs (habit_id, day) VALUES (?, ?)", (habit_id, day)
        )
        self._conn.commit()
        h = self._conn.execute(
            "SELECT user_id, name FROM habits WHERE id = ?", (habit_id,)
        ).fetchone()
        if h:
            self.log_activity(h["user_id"], "habit.done", h["name"])
        return True

    def delete_habit(self, user_id: str, habit_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM habits WHERE id = ? AND user_id = ?", (habit_id, user_id)
        )
        self._conn.execute("DELETE FROM habit_logs WHERE habit_id = ?", (habit_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def habit_days(self, habit_id: int) -> set[str]:
        rows = self._conn.execute(
            "SELECT day FROM habit_logs WHERE habit_id = ?", (habit_id,)
        ).fetchall()
        return {r["day"] for r in rows}

    def update_habit(self, u, i, name):
        return self._update("habits", u, i, {"name": name})

    def rename_habit(self, u, i, name):
        return self._update("habits", u, i, {"name": name})
