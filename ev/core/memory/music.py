"""Saved Spotify items."""

from __future__ import annotations


class MusicMixin:
    def add_music(self, user_id: str, label: str, kind: str, ref: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO music (user_id, label, kind, ref, created) VALUES (?, ?, ?, ?, ?)",
            (user_id, label, kind, ref, self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_music(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, label, kind, ref, created FROM music WHERE user_id = ? ORDER BY id",
            (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_music(self, user_id: str, mid: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM music WHERE id = ? AND user_id = ?", (mid, user_id))
        self._conn.commit()
        return cur.rowcount > 0
