"""Financial goals (cofrinho)."""

from __future__ import annotations


class GoalsMixin:
    def add_goal(self, user_id: str, name: str, target: float) -> int:
        cur = self._conn.execute(
            "INSERT INTO goals (user_id, name, target, saved, created) VALUES (?, ?, ?, 0, ?)",
            (user_id, name, target, self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_goals(self, user_id: str) -> list[dict]:
        return [dict(r) for r in self._conn.execute(
            "SELECT id, name, target, saved, created FROM goals WHERE user_id = ? ORDER BY id",
            (user_id,)).fetchall()]

    def add_to_goal(self, user_id: str, goal_id: int, amount: float) -> bool:
        cur = self._conn.execute(
            "UPDATE goals SET saved = MAX(0, saved + ?) WHERE id = ? AND user_id = ?",
            (amount, goal_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    def delete_goal(self, user_id: str, goal_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM goals WHERE id = ? AND user_id = ?",
                                 (goal_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0
