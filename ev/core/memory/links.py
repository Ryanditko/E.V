"""Named, categorized links."""

from __future__ import annotations


class LinksMixin:
    def add_link(self, user_id: str, category: str, name: str, url: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO links (user_id, category, name, url, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, category, name, url, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_links(self, user_id: str, category: str | None = None) -> list[dict]:
        if category:
            rows = self._conn.execute(
                "SELECT id, category, name, url FROM links "
                "WHERE user_id = ? AND category = ? ORDER BY id",
                (user_id, category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, category, name, url FROM links "
                "WHERE user_id = ? ORDER BY category, id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_link(self, user_id: str, link_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM links WHERE id = ? AND user_id = ?", (link_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_link(self, u, i, category=None, name=None, url=None):
        return self._update("links", u, i, {"category": category, "name": name, "url": url})
