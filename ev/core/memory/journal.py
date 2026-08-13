"""Journal entries."""

from __future__ import annotations


class JournalMixin:
    def add_journal(self, user_id: str, text: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO journal (user_id, text, created) VALUES (?, ?, ?)",
            (user_id, text, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def recent_journal(self, user_id: str, limit: int = 5) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, created FROM journal WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def delete_journal(self, user_id: str, entry_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM journal WHERE id = ? AND user_id = ?", (entry_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_journal(self, u, i, text):
        return self._update("journal", u, i, {"text": text})
