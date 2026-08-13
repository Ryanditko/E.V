"""Local PC execution: allowlisted scripts, the approval-gated task queue, and
in-flight risky-action confirms, plus user-defined connector integrations."""

from __future__ import annotations

import json


class LocalAgentMixin:
    # --- local scripts (allowlist for the local execution agent) -----------

    def add_local_script(self, user_id: str, name: str, command: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO local_scripts (user_id, name, command, created) "
            "VALUES (?, ?, ?, ?)",
            (user_id, name, command, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_local_scripts(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, command, created FROM local_scripts "
            "WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_local_script(self, user_id: str, script_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM local_scripts WHERE id = ? AND user_id = ?",
            (script_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    # --- local tasks (PC execution queue — always requires approval) -------

    #: platforms where sending/posting on the user's behalf carries real
    #: account-ban/ToS risk — browser tasks touching them are flagged 'high'
    #: and additionally gated by a second confirmation before any risky click.
    _HIGH_RISK_MARKERS = ("whatsapp", "wa.me", "instagram", "instagr.am")

    @classmethod
    def classify_local_task_risk(cls, kind: str, command: str) -> str:
        if kind != "browser":
            return "normal"
        c = (command or "").lower()
        return "high" if any(m in c for m in cls._HIGH_RISK_MARKERS) else "normal"

    def _local_task_row(self, r) -> dict:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except (ValueError, TypeError):
            d["payload"] = {}
        try:
            d["result"] = json.loads(d["result"]) if d.get("result") else None
        except (ValueError, TypeError):
            d["result"] = None
        return d

    def add_local_task(self, user_id: str, kind: str, label: str, payload: dict,
                        risk: str | None = None) -> int:
        risk = risk or self.classify_local_task_risk(kind, (payload or {}).get("command", ""))
        cur = self._conn.execute(
            "INSERT INTO local_tasks (user_id, kind, label, payload, status, risk, created) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (user_id, kind, label, json.dumps(payload or {}), risk, self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_local_tasks(self, user_id: str, status: str | None = None,
                          limit: int = 50) -> list[dict]:
        q = ("SELECT id, kind, label, payload, status, risk, result, created, decided, "
             "finished FROM local_tasks WHERE user_id = ?")
        args: list = [user_id]
        if status:
            q += " AND status = ?"
            args.append(status)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = self._conn.execute(q, tuple(args)).fetchall()
        return [self._local_task_row(r) for r in rows]

    def get_local_task(self, user_id: str, task_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, kind, label, payload, status, risk, result, created, decided, "
            "finished FROM local_tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id)).fetchone()
        return self._local_task_row(row) if row else None

    def unnotified_local_tasks(self) -> list[dict]:
        """Pending local tasks (any user) that still need a Telegram nudge."""
        rows = self._conn.execute(
            "SELECT id, user_id, kind, label, payload, status, risk, created "
            "FROM local_tasks WHERE status = 'pending' AND notified = 0"
        ).fetchall()
        return [self._local_task_row(r) for r in rows]

    def mark_local_task_notified(self, task_id: int) -> None:
        self._conn.execute(
            "UPDATE local_tasks SET notified = 1 WHERE id = ?", (task_id,))
        self._conn.commit()

    def set_local_task_status(self, user_id: str, task_id: int, status: str) -> bool:
        cur = self._conn.execute(
            "UPDATE local_tasks SET status = ?, decided = ? "
            "WHERE id = ? AND user_id = ? AND status = 'pending'",
            (status, self._now(), task_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    def claim_local_task(self, user_id: str) -> dict | None:
        """Atomically hands the oldest approved task to the local agent."""
        row = self._conn.execute(
            "SELECT id FROM local_tasks WHERE user_id = ? AND status = 'approved' "
            "ORDER BY id LIMIT 1", (user_id,)).fetchone()
        if not row:
            return None
        cur = self._conn.execute(
            "UPDATE local_tasks SET status = 'running' "
            "WHERE id = ? AND status = 'approved'", (row["id"],))
        self._conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get_local_task(user_id, row["id"])

    def finish_local_task(self, user_id: str, task_id: int, ok: bool, output: dict) -> bool:
        cur = self._conn.execute(
            "UPDATE local_tasks SET status = ?, result = ?, finished = ? "
            "WHERE id = ? AND user_id = ? AND status = 'running'",
            ("done" if ok else "failed", json.dumps(output or {}), self._now(),
             task_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    # --- local task confirms (2nd approval for risky in-flight browser actions) --
    # Used when a 'high' risk browser task is about to do something irreversible
    # (send a message, post, follow, delete) — the local agent pauses execution
    # and waits for this SEPARATE approval before clicking, even though the task
    # itself was already approved once.

    def add_local_confirm(self, user_id: str, task_id: int, label: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO local_confirms (task_id, user_id, label, status, created) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (task_id, user_id, label[:200], self._now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_local_confirm(self, user_id: str, confirm_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT id, task_id, label, status, created, decided FROM local_confirms "
            "WHERE id = ? AND user_id = ?", (confirm_id, user_id)).fetchone()
        return dict(row) if row else None

    def list_local_confirms(self, user_id: str, status: str | None = None,
                             limit: int = 50) -> list[dict]:
        q = ("SELECT id, task_id, label, status, created, decided FROM local_confirms "
             "WHERE user_id = ?")
        args: list = [user_id]
        if status:
            q += " AND status = ?"
            args.append(status)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self._conn.execute(q, tuple(args)).fetchall()]

    def set_local_confirm_status(self, user_id: str, confirm_id: int, status: str) -> bool:
        cur = self._conn.execute(
            "UPDATE local_confirms SET status = ?, decided = ? "
            "WHERE id = ? AND user_id = ? AND status = 'pending'",
            (status, self._now(), confirm_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0

    def unnotified_local_confirms(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, task_id, user_id, label, status, created "
            "FROM local_confirms WHERE status = 'pending' AND notified = 0"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_local_confirm_notified(self, confirm_id: int) -> None:
        self._conn.execute(
            "UPDATE local_confirms SET notified = 1 WHERE id = ?", (confirm_id,))
        self._conn.commit()

    # --- connectors (user-defined API integrations) ------------------------

    def add_connector(self, user_id: str, name: str, url: str,
                      headers: dict, path: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO connectors (user_id, name, url, headers, path, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, url, json.dumps(headers or {}), path or "", self._now()))
        self._conn.commit()
        return int(cur.lastrowid)

    def list_connectors(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, url, headers, path, created FROM connectors "
            "WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["headers"] = json.loads(d.get("headers") or "{}")
            except (ValueError, TypeError):
                d["headers"] = {}
            out.append(d)
        return out

    def get_connector(self, user_id: str, name: str) -> dict | None:
        for c in self.list_connectors(user_id):
            if c["name"].lower() == (name or "").lower():
                return c
        return None

    def delete_connector(self, user_id: str, conn_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM connectors WHERE id = ? AND user_id = ?", (conn_id, user_id))
        self._conn.commit()
        return cur.rowcount > 0
