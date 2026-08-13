"""Saved places / points of interest."""

from __future__ import annotations


class PlacesMixin:
    def add_place(self, user_id: str, name: str, lat: float, lng: float) -> int:
        cur = self._conn.execute(
            "INSERT INTO places (user_id, name, lat, lng, created) VALUES (?, ?, ?, ?, ?)",
            (user_id, (name or "ponto").strip()[:80], float(lat), float(lng), self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_places(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, lat, lng FROM places WHERE user_id = ? ORDER BY id",
            (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_place(self, user_id: str, place_id: int) -> None:
        self._conn.execute("DELETE FROM places WHERE user_id = ? AND id = ?",
                           (user_id, place_id))
        self._conn.commit()

    def update_place(self, u, i, name):
        return self._update("places", u, i, {"name": name})
