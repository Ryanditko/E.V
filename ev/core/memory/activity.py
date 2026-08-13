"""Activity log — CRUD tracking shared by Telegram + web."""

from __future__ import annotations

import sqlite3


class ActivityMixin:
    def log_activity(self, user_id: str, action: str, label: str,
                     category: str | None = None) -> None:
        try:
            self._conn.execute(
                "INSERT INTO activity (user_id, action, label, category, created) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, action, (label or "")[:200], category, self._now()),
            )
            self._conn.commit()
        except sqlite3.Error:
            pass  # tracking must never break the actual operation

    def list_activity(self, user_id: str, category: str | None = None,
                      limit: int = 300) -> list[dict]:
        if category:
            rows = self._conn.execute(
                "SELECT action, label, category, created FROM activity "
                "WHERE user_id = ? AND category = ? ORDER BY id DESC LIMIT ?",
                (user_id, category, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT action, label, category, created FROM activity "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def activity_categories(self, user_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT category FROM activity "
            "WHERE user_id = ? AND category IS NOT NULL AND category != '' "
            "ORDER BY category",
            (user_id,),
        ).fetchall()
        return [r["category"] for r in rows]
