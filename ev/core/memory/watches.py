"""Web watches (URL/keyword monitors)."""

from __future__ import annotations


class WatchesMixin:
    def add_watch(self, user_id: str, url: str, keyword: str | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO watches (user_id, url, keyword, created) VALUES (?, ?, ?, ?)",
            (user_id, url, keyword, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_watches(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, url, keyword FROM watches WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_watch(self, user_id: str, watch_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM watches WHERE id = ? AND user_id = ?", (watch_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def all_watches(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, user_id, url, keyword, state FROM watches ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def set_watch_state(self, watch_id: int, state: str) -> None:
        self._conn.execute(
            "UPDATE watches SET state = ? WHERE id = ?", (state, watch_id)
        )
        self._conn.commit()

    def update_watch(self, u, i, url=None, keyword=None):
        return self._update("watches", u, i, {"url": url, "keyword": keyword})
