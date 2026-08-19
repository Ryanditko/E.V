"""Tasks (to-do list)."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..timeparse import add_months


class TasksMixin:
    @staticmethod
    def _next_due(due_iso: str, recur: str, now: datetime | None = None) -> str:
        """Advance a due datetime to the next future occurrence of `recur`."""
        try:
            due = datetime.fromisoformat(due_iso)
        except Exception:
            return due_iso
        now = now or datetime.now()
        if due.tzinfo and now.tzinfo is None:
            now = now.replace(tzinfo=due.tzinfo)
        elif now.tzinfo and due.tzinfo is None:
            due = due.replace(tzinfo=now.tzinfo)
        if due > now:
            return due_iso  # already in the future — leave untouched
        if recur == "monthly":
            nxt = due
            while nxt <= now:
                nxt = add_months(nxt, 1)
            return nxt.isoformat()
        step = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(recur)
        if not step:
            return due_iso
        nxt = due
        while nxt <= now:
            nxt += step
        return nxt.isoformat()

    def add_task(self, user_id: str, text: str, category: str = "geral",
                 recur: str | None = None, due: str | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO tasks (user_id, text, category, recur, due, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, text, category, recur or None, due or None, self._now()),
        )
        self._conn.commit()
        self.log_activity(user_id, "task.new", text, category)
        return int(cur.lastrowid)

    def open_tasks(self, user_id: str, category: str | None = None) -> list[dict]:
        if category:
            rows = self._conn.execute(
                "SELECT id, text, category, recur, due FROM tasks "
                "WHERE user_id = ? AND done = 0 AND category = ? ORDER BY id",
                (user_id, category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, text, category, recur, due FROM tasks "
                "WHERE user_id = ? AND done = 0 ORDER BY category, id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def roll_due_tasks(self, now: datetime | None = None) -> int:
        """Roll every open recurring task whose due date has passed forward to its
        next occurrence (single rolling instance — never piles up). Returns how
        many were advanced. Safe to call often (idempotent within a period)."""
        now = now or datetime.now()
        rows = self._conn.execute(
            "SELECT id, recur, due FROM tasks "
            "WHERE done = 0 AND recur IS NOT NULL AND due IS NOT NULL"
        ).fetchall()
        advanced = 0
        for r in rows:
            if (r["recur"] or "") not in ("daily", "weekly", "monthly"):
                continue
            nxt = self._next_due(r["due"], r["recur"], now)
            if nxt != r["due"]:
                self._conn.execute("UPDATE tasks SET due = ? WHERE id = ?", (nxt, r["id"]))
                advanced += 1
        if advanced:
            self._conn.commit()
        return advanced

    def complete_task(self, user_id: str, task_id: int) -> bool:
        row = self._conn.execute(
            "SELECT text, category, recur, due FROM tasks "
            "WHERE id = ? AND user_id = ? AND done = 0",
            (task_id, user_id),
        ).fetchone()
        if not row:
            return False
        recur = (row["recur"] or "")
        # Recurring with a due date: roll the same task forward (single instance).
        if recur in ("daily", "weekly", "monthly") and row["due"]:
            self._conn.execute(
                "UPDATE tasks SET due = ? WHERE id = ?",
                (self._next_due(row["due"], recur), task_id),
            )
            self._conn.commit()
            self.log_activity(user_id, "task.done", row["text"], row["category"])
            return True
        # Recurring without a due date: regenerate a fresh open copy so it returns.
        if recur in ("daily", "weekly", "monthly"):
            self._conn.execute(
                "UPDATE tasks SET done = 1, done_at = ? WHERE id = ?",
                (self._now(), task_id),
            )
            self._conn.execute(
                "INSERT INTO tasks (user_id, text, category, recur, created) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, row["text"], row["category"], recur, self._now()),
            )
            self._conn.commit()
            self.log_activity(user_id, "task.done", row["text"], row["category"])
            return True
        # Plain one-off task.
        self._conn.execute(
            "UPDATE tasks SET done = 1, done_at = ? WHERE id = ?",
            (self._now(), task_id),
        )
        self._conn.commit()
        self.log_activity(user_id, "task.done", row["text"], row["category"])
        return True

    def delete_task(self, user_id: str, task_id: int) -> bool:
        row = self._conn.execute(
            "SELECT text, category FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        ).fetchone()
        cur = self._conn.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        self._conn.commit()
        if cur.rowcount and row:
            self.log_activity(user_id, "task.del", row["text"], row["category"])
        return cur.rowcount > 0

    def update_task(self, user_id: str, task_id: int, text: str | None = None,
                    category: str | None = None, recur: str | None = None,
                    due: str | None = None) -> bool:
        sets, params = [], []
        if text is not None:
            sets.append("text = ?"); params.append(text)
        if category is not None:
            sets.append("category = ?"); params.append(category)
        if recur is not None:
            sets.append("recur = ?"); params.append(recur or None)
        if due is not None:
            sets.append("due = ?"); params.append(due or None)
        if not sets:
            return False
        params += [task_id, user_id]
        cur = self._conn.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ? AND user_id = ?", params
        )
        self._conn.commit()
        return cur.rowcount > 0

    def tasks_per_day(self, user_id: str, frm_iso: str, to_iso: str) -> dict:
        """Tasks created vs completed per day in [frm_iso, to_iso).
        Returns {"created": {day: n}, "completed": {day: n}}."""
        out = {"created": {}, "completed": {}}
        try:
            for r in self._conn.execute(
                "SELECT substr(created, 1, 10) AS d, COUNT(*) AS n FROM tasks "
                "WHERE user_id = ? AND created >= ? AND created < ? GROUP BY d",
                (user_id, frm_iso, to_iso),
            ).fetchall():
                out["created"][r["d"]] = int(r["n"])
            for r in self._conn.execute(
                "SELECT substr(done_at, 1, 10) AS d, COUNT(*) AS n FROM tasks "
                "WHERE user_id = ? AND done = 1 AND done_at IS NOT NULL "
                "AND done_at >= ? AND done_at < ? GROUP BY d",
                (user_id, frm_iso, to_iso),
            ).fetchall():
                out["completed"][r["d"]] = int(r["n"])
        except Exception:
            pass
        return out

    def tasks_completed_since(self, user_id: str, since_iso: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM tasks "
            "WHERE user_id = ? AND done = 1 AND done_at >= ?",
            (user_id, since_iso),
        ).fetchone()
        return int(row["n"])
