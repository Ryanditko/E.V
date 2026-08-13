"""Web push subscriptions and the persisted notification center."""

from __future__ import annotations

import sqlite3


class PushMixin:
    def add_push_sub(self, endpoint: str, sub_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO push_subs (endpoint, sub, created) VALUES (?, ?, ?)",
            (endpoint, sub_json, self._now()),
        )
        self._conn.commit()

    def list_push_subs(self) -> list[dict]:
        rows = self._conn.execute("SELECT endpoint, sub FROM push_subs").fetchall()
        return [dict(r) for r in rows]

    def delete_push_sub(self, endpoint: str) -> None:
        self._conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
        self._conn.commit()

    # --- notification center (persisted so they can be reviewed later) ------

    def add_notification(self, user_id: str, title: str, body: str = "",
                         url: str = "/") -> None:
        """Store a notification so it shows up in the web notification center,
        whether or not a device was actually reachable via push."""
        try:
            self._conn.execute(
                "INSERT INTO notifications (user_id, title, body, url, read, created) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (user_id, (title or "")[:200], (body or "")[:1000], url or "/", self._now()),
            )
            # keep it bounded: retain only the newest 200 per user
            self._conn.execute(
                "DELETE FROM notifications WHERE user_id = ? AND id NOT IN "
                "(SELECT id FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 200)",
                (user_id, user_id),
            )
            self._conn.commit()
        except sqlite3.Error:
            pass  # a logging failure must never break delivery

    def list_notifications(self, user_id: str, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, body, url, read, created FROM notifications "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def unread_notifications(self, user_id: str) -> int:
        r = self._conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND read = 0",
            (user_id,),
        ).fetchone()
        return r["c"] if r else 0

    def mark_notification_read(self, user_id: str, notif_id: int | None = None) -> None:
        if notif_id:
            self._conn.execute(
                "UPDATE notifications SET read = 1 WHERE user_id = ? AND id = ?",
                (user_id, notif_id),
            )
        else:  # no id -> mark all read
            self._conn.execute(
                "UPDATE notifications SET read = 1 WHERE user_id = ?", (user_id,))
        self._conn.commit()

    def delete_notification(self, user_id: str, notif_id: int) -> None:
        self._conn.execute(
            "DELETE FROM notifications WHERE user_id = ? AND id = ?", (user_id, notif_id))
        self._conn.commit()

    def clear_notifications(self, user_id: str, only_read: bool = False) -> None:
        if only_read:
            self._conn.execute(
                "DELETE FROM notifications WHERE user_id = ? AND read = 1", (user_id,))
        else:
            self._conn.execute(
                "DELETE FROM notifications WHERE user_id = ?", (user_id,))
        self._conn.commit()
