"""Learned patterns (continuous learning) and user-defined automations."""

from __future__ import annotations

import json
import sqlite3


class PatternsMixin:
    def learned_seen(self, user_id: str, key: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM learned WHERE user_id = ? AND key = ?", (user_id, key)
        ).fetchone()
        return row is not None

    def add_learned(self, user_id: str, key: str, text: str) -> bool:
        """Record a learned pattern (once per key). Returns True if it was new."""
        try:
            self._conn.execute(
                "INSERT INTO learned (user_id, key, text, created) VALUES (?, ?, ?, ?)",
                (user_id, key, text, self._now()),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # already known

    def list_learned(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT key, text, created FROM learned WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- automations ("quando X, faça Y") ----------------------------------

    def add_automation(self, user_id: str, name: str, trig: str, trig_cfg: dict,
                       act: str, act_cfg: dict, state: dict | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO automations "
            "(user_id, name, trig, trig_cfg, act, act_cfg, enabled, state, created) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (user_id, name, trig, json.dumps(trig_cfg), act, json.dumps(act_cfg),
             json.dumps(state or {}), self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def _auto_row(self, r) -> dict:
        d = dict(r)
        for k in ("trig_cfg", "act_cfg", "state"):
            try:
                d[k] = json.loads(d.get(k) or "{}")
            except (ValueError, TypeError):
                d[k] = {}
        d["enabled"] = bool(d.get("enabled"))
        return d

    def list_automations(self, user_id: str, only_enabled: bool = False) -> list[dict]:
        q = ("SELECT id, name, trig, trig_cfg, act, act_cfg, enabled, state, created "
             "FROM automations WHERE user_id = ?")
        if only_enabled:
            q += " AND enabled = 1"
        rows = self._conn.execute(q + " ORDER BY id", (user_id,)).fetchall()
        return [self._auto_row(r) for r in rows]

    def delete_automation(self, user_id: str, auto_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM automations WHERE id = ? AND user_id = ?", (auto_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    def set_automation_enabled(self, user_id: str, auto_id: int, on: bool) -> bool:
        cur = self._conn.execute(
            "UPDATE automations SET enabled = ? WHERE id = ? AND user_id = ?",
            (1 if on else 0, auto_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    def set_automation_state(self, auto_id: int, state: dict) -> None:
        self._conn.execute("UPDATE automations SET state = ? WHERE id = ?",
                           (json.dumps(state), auto_id))
        self._conn.commit()
