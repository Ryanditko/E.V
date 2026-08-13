"""Usage tracking, key/value settings, and custom dashboard pages."""

from __future__ import annotations

import json


class SettingsMixin:
    def bump_usage(self, provider: str, day: str) -> None:
        self._conn.execute(
            "INSERT INTO usage_log (day, provider, n) VALUES (?, ?, 1) "
            "ON CONFLICT(day, provider) DO UPDATE SET n = n + 1",
            (day, provider),
        )
        self._conn.commit()

    def usage_for_day(self, day: str) -> dict:
        rows = self._conn.execute(
            "SELECT provider, n FROM usage_log WHERE day = ?", (day,)
        ).fetchall()
        return {r["provider"]: r["n"] for r in rows}

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )
        self._conn.commit()

    # --- custom pages (declarative dashboards) -----------------------------

    def add_page(self, user_id: str, name: str, widgets: list) -> int:
        cur = self._conn.execute(
            "INSERT INTO pages (user_id, name, widgets, created) VALUES (?, ?, ?, ?)",
            (user_id, name, json.dumps(widgets or []), self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_pages(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, widgets, created FROM pages WHERE user_id = ? ORDER BY id",
            (user_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["widgets"] = json.loads(d.get("widgets") or "[]")
            except (ValueError, TypeError):
                d["widgets"] = []
            out.append(d)
        return out

    def update_page(self, user_id: str, page_id: int, name=None, widgets=None) -> bool:
        sets, params = [], []
        if name is not None:
            sets.append("name = ?"); params.append(name)
        if widgets is not None:
            sets.append("widgets = ?"); params.append(json.dumps(widgets))
        if not sets:
            return False
        params += [page_id, user_id]
        cur = self._conn.execute(
            f"UPDATE pages SET {', '.join(sets)} WHERE id = ? AND user_id = ?", params)
        self._conn.commit()
        return cur.rowcount > 0

    def delete_page(self, user_id: str, page_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM pages WHERE id = ? AND user_id = ?", (page_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0
