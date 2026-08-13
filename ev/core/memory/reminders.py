"""Reminders."""

from __future__ import annotations


class RemindersMixin:
    def add_reminder(
        self, user_id: str, text: str, when_iso: str | None, recur: str | None = None
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO reminders (user_id, text, when_iso, recur, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, text, when_iso, recur, self._now()),
        )
        self._conn.commit()
        self.log_activity(user_id, "reminder.new", text)
        return int(cur.lastrowid)

    def open_reminders(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, when_iso, recur FROM reminders "
            "WHERE user_id = ? AND done = 0 ORDER BY id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def pending_reminders(self) -> list[dict]:
        """All open reminders that have a scheduled time (across all users).

        The scheduler parses `when_iso` and compares by real datetime — robust to
        different timezone offsets, unlike a lexical string comparison.
        """
        rows = self._conn.execute(
            "SELECT id, user_id, text, when_iso, recur FROM reminders "
            "WHERE done = 0 AND when_iso IS NOT NULL ORDER BY when_iso"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_reminder_done(self, reminder_id: int) -> None:
        row = self._conn.execute(
            "SELECT user_id, text FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        self._conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ?", (reminder_id,)
        )
        self._conn.commit()
        if row:
            self.log_activity(row["user_id"], "reminder.done", row["text"])

    def reschedule_reminder(self, reminder_id: int, new_when_iso: str) -> None:
        """Move a (recurring) reminder to its next occurrence, keeping it open."""
        self._conn.execute(
            "UPDATE reminders SET when_iso = ? WHERE id = ?",
            (new_when_iso, reminder_id),
        )
        self._conn.commit()

    def cancel_reminder(self, user_id: str, reminder_id: int) -> bool:
        row = self._conn.execute(
            "SELECT text FROM reminders WHERE id = ? AND user_id = ? AND done = 0",
            (reminder_id, user_id),
        ).fetchone()
        cur = self._conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ? AND user_id = ? AND done = 0",
            (reminder_id, user_id),
        )
        self._conn.commit()
        if cur.rowcount and row:
            self.log_activity(user_id, "reminder.cancel", row["text"])
        return cur.rowcount > 0

    def update_reminder(self, u, i, text=None, when_iso=None, recur=None):
        return self._update("reminders", u, i, {"text": text, "when_iso": when_iso, "recur": recur})
